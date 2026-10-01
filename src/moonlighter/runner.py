"""Dockerized Pi RPC runner orchestration."""

from __future__ import annotations

import json
import os
import select
import shutil
import subprocess
import time
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from moonlighter.config import Config, default_state_dir
from moonlighter.projects import (
    ProjectError,
    agent_result_path,
    load_agent_result,
    load_project_state,
    save_project_state,
    state_path,
)

CONTAINER_WORKSPACE = Path("/workspace")
CONTAINER_HOME = Path("/home/moon-runtime")
CONTAINER_SESSION_DIR = CONTAINER_HOME / ".pi" / "agent" / "sessions"
CONTAINER_AGENTS_SKILLS = CONTAINER_HOME / ".agents" / "skills"
CONTAINER_PI_SKILLS = CONTAINER_HOME / ".pi" / "agent" / "skills"
MOON_WORK_CHUNK_SKILL = Path("/opt/moon/skills/moon-work-chunk")
MOON_WRAP_UP_SKILL = Path("/opt/moon/skills/moon-wrap-up")
RUNNER_IMAGE_VERSION = "0.1.0-dev"


class RunnerError(RuntimeError):
    """Raised when the Dockerized runner fails."""


@dataclass(frozen=True)
class RunnerRequest:
    """Inputs for one project work chunk."""

    project_dir: Path
    config: Config
    chunk_minutes: int | None = None
    now: datetime | None = None


@dataclass(frozen=True)
class RunnerResult:
    """Result from one project work chunk."""

    success: bool
    elapsed_seconds: float
    session_id: str | None = None
    session_file: str | None = None
    disposition: str | None = None
    summary: str | None = None
    error: str | None = None
    commit_count: int = 0
    inserted_lines: int = 0
    deleted_lines: int = 0


@dataclass(frozen=True)
class GitSnapshot:
    """Git repository state before or after a runner chunk."""

    commit_count: int | None
    head: str | None


@dataclass(frozen=True)
class GitMetrics:
    """Git metrics for a runner chunk."""

    commit_count: int = 0
    inserted_lines: int = 0
    deleted_lines: int = 0


def run_project_chunk(request: RunnerRequest) -> RunnerResult:
    """Run one bounded Pi work chunk for a project in Docker."""
    start = time.monotonic()
    run_started_at = request.now or datetime.now().astimezone()
    chunk_seconds = (request.chunk_minutes or request.config.runner.chunk_minutes) * 60
    deadline = start + chunk_seconds
    deadline_epoch = int(time.time() + chunk_seconds)
    project_dir = request.project_dir.resolve(strict=False)

    load_project_state(state_path(project_dir))
    git_before = collect_git_snapshot(project_dir)
    session_storage = _project_session_storage(project_dir)
    session_storage.mkdir(parents=True, exist_ok=True)
    runtime_home = _project_runtime_home(project_dir)
    prepare_runtime_home(runtime_home, deadline_epoch=deadline_epoch)

    process = subprocess.Popen(
        build_docker_command(request, session_storage, runtime_home),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    session_id: str | None = None
    session_file: str | None = None
    error: str | None = None
    try:
        _send(process, {"id": "state-1", "type": "get_state"})
        state_response = _read_response(process, "state-1", timeout_seconds=30)
        session_id, session_file = _session_from_response(state_response)

        _send(process, {"id": "prompt-1", "type": "prompt", "message": work_chunk_prompt()})
        prompt_response = _read_response(process, "prompt-1", timeout_seconds=30)
        if not prompt_response.get("success"):
            raise RunnerError(f"Pi rejected work prompt: {prompt_response}")

        wrap_sent = False
        settled = False
        soft_wrap_at = deadline - 120
        while time.monotonic() < deadline:
            if not wrap_sent and time.monotonic() >= soft_wrap_at:
                _send(process, {"id": "wrap-1", "type": "steer", "message": wrap_up_prompt()})
                wrap_sent = True
            event = _read_json_line(process, timeout_seconds=1)
            if event is None:
                if process.poll() is not None:
                    raise RunnerError(_process_failure_message(process))
                continue
            if event.get("type") == "agent_settled":
                settled = True
                break

        if not settled:
            _send(process, {"id": "clear-1", "type": "clear_queue"})
            _read_response(process, "clear-1", timeout_seconds=10, required=False)
            _send(process, {"id": "abort-1", "type": "abort"})
            _read_response(process, "abort-1", timeout_seconds=30, required=False)

        _send(process, {"id": "state-2", "type": "get_state"})
        final_state = _read_response(process, "state-2", timeout_seconds=30, required=False)
        final_session_id, final_session_file = _session_from_response(final_state)
        session_id = final_session_id or session_id
        session_file = final_session_file or session_file
    except Exception as exc:
        error = str(exc)
    finally:
        _terminate_process(process)

    disposition: str | None = None
    summary: str | None = None
    try:
        current_state = load_project_state(state_path(project_dir))
        updated = replace(
            current_state,
            pi_session_id=session_id or current_state.pi_session_id,
            pi_session_file=session_file or current_state.pi_session_file,
            last_run_at=run_started_at.isoformat(),
        )
        result_file = agent_result_path(project_dir)
        if result_file.exists():
            agent_result = load_agent_result(result_file)
            disposition = agent_result.disposition
            summary = agent_result.summary
            updated = replace(updated, disposition=agent_result.disposition)
            result_file.unlink()
        save_project_state(state_path(project_dir), updated)
        load_project_state(state_path(project_dir))
    except ProjectError as exc:
        error = error or str(exc)

    git_after = collect_git_snapshot(project_dir)
    metrics = diff_git_snapshots(project_dir, git_before, git_after)

    return RunnerResult(
        success=error is None,
        elapsed_seconds=time.monotonic() - start,
        session_id=session_id,
        session_file=session_file,
        disposition=disposition,
        summary=summary,
        error=error,
        commit_count=metrics.commit_count,
        inserted_lines=metrics.inserted_lines,
        deleted_lines=metrics.deleted_lines,
    )


def build_docker_command(
    request: RunnerRequest, session_storage: Path | None = None, runtime_home: Path | None = None
) -> list[str]:
    """Build the Docker command for a project work chunk."""
    project_dir = request.project_dir.resolve(strict=False)
    session_dir = session_storage or _project_session_storage(project_dir)
    home_dir = runtime_home or _project_runtime_home(project_dir)
    command = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,exec,nosuid,size=512m",
        "--network",
        "bridge",
        "--label",
        "moonlighter=true",
        "--label",
        f"moonlighter.project={project_dir.name}",
        "--name",
        container_name(project_dir.name),
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--env",
        f"HOME={CONTAINER_HOME}",
        "--env",
        f"PATH={CONTAINER_HOME}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "--workdir",
        str(CONTAINER_WORKSPACE),
        "--mount",
        _mount(project_dir, CONTAINER_WORKSPACE, readonly=False),
        "--mount",
        _mount(home_dir, CONTAINER_HOME, readonly=False),
        "--mount",
        _mount(session_dir, CONTAINER_SESSION_DIR, readonly=False),
    ]

    command.extend(
        _optional_readonly_mount(Path.home() / ".agents" / "skills", CONTAINER_AGENTS_SKILLS)
    )
    command.extend(
        _optional_readonly_mount(Path.home() / ".pi" / "agent" / "skills", CONTAINER_PI_SKILLS)
    )

    pi_args = [
        request.config.runner.image,
        "--mode",
        "rpc",
        "--approve",
        "--provider",
        request.config.runner.provider,
        "--model",
        request.config.runner.model,
        "--thinking",
        request.config.runner.thinking,
        "--session-dir",
        str(CONTAINER_SESSION_DIR),
        "--name",
        f"moon {project_dir.name}",
        "--skill",
        str(MOON_WORK_CHUNK_SKILL),
        "--skill",
        str(MOON_WRAP_UP_SKILL),
    ]
    session_file = _saved_container_session_file(project_dir)
    if session_file is not None:
        pi_args.extend(["--session", session_file])
    command.extend(pi_args)

    return command


def container_name(project_name: str) -> str:
    """Return a deterministic Docker container name for a project chunk."""
    safe = "".join(char if char.isalnum() or char in "_.-" else "-" for char in project_name)
    safe = safe.strip("-_.") or "project"
    return f"moonlighter-runner-{safe}"[:128]


def work_chunk_prompt() -> str:
    """Return the initial automatic work prompt."""
    return """/skill:moon-work-chunk

Moonlighter is running one bounded autonomous work chunk in this Moon-owned workspace.
Use the moon-work-chunk protocol. This is a bounded work session, not a one-task request.
Run `moon-time-left` after each useful task/checkpoint. If it says `keep working`, identify
and execute another high-value autonomous task when one exists. Make coherent commits at
logical task boundaries with high-quality messages, run obvious relevant checks before commits
when practical, and never push. Do not edit .moon/state.json. Before stopping, update
.moon/status.md and write .moon/agent-result.json with a valid disposition and summary.
"""


def wrap_up_prompt() -> str:
    """Return the cooperative wrap-up prompt."""
    return """/skill:moon-wrap-up

Moonlighter's chunk deadline is near. Stop starting new work, finish only safe atomic operations,
update .moon/status.md, write a concise .moon/logs/ summary, and write .moon/agent-result.json.
"""


def prepare_runtime_home(runtime_home: Path, deadline_epoch: int | None = None) -> None:
    """Create a minimal writable Pi home with auth and Moon helper scripts."""
    auth_dir = runtime_home / ".pi" / "agent"
    auth_dir.mkdir(parents=True, exist_ok=True)
    (runtime_home / ".agents" / "skills").mkdir(parents=True, exist_ok=True)
    if deadline_epoch is not None:
        write_time_left_script(runtime_home, deadline_epoch)
    token = _get_codex_bearer_token()
    if token is None:
        return
    auth = {
        "openai-codex": {
            "type": "oauth",
            "access": token,
            "expires": int((time.time() + 3600) * 1000),
        }
    }
    (auth_dir / "auth.json").write_text(
        f"{json.dumps(auth, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )


def write_time_left_script(runtime_home: Path, deadline_epoch: int) -> Path:
    """Write the moon-time-left helper script into the runtime home."""
    bin_dir = runtime_home / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "moon-time-left"
    script.write_text(
        "#!/bin/sh\n"
        "now=$(date +%s)\n"
        f"deadline={deadline_epoch}\n"
        "remaining=$((deadline - now))\n"
        'if [ "$remaining" -le 30 ]; then\n'
        '  echo "finish now: stop immediately, write or verify handoff, and leave changes '
        'uncommitted if necessary"\n'
        'elif [ "$remaining" -le 120 ]; then\n'
        '  echo "wrap up: quickly finish the current task, commit changes when ready, '
        'write handoff, and terminate"\n'
        "else\n"
        '  echo "keep working: identify any high-value autonomous work and keep executing; '
        'if none remains or direction is unclear, mark the project accordingly and terminate"\n'
        "fi\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def collect_git_snapshot(project_dir: Path) -> GitSnapshot:
    """Collect lightweight git state for metrics."""
    count = _git_int(project_dir, ["rev-list", "--count", "HEAD"])
    head = _git_text(project_dir, ["rev-parse", "HEAD"])
    return GitSnapshot(commit_count=count, head=head)


def diff_git_snapshots(project_dir: Path, before: GitSnapshot, after: GitSnapshot) -> GitMetrics:
    """Compute chunk git metrics from before/after snapshots."""
    commit_count = 0
    if before.commit_count is not None and after.commit_count is not None:
        commit_count = max(0, after.commit_count - before.commit_count)
    elif before.commit_count is None and after.commit_count is not None:
        commit_count = after.commit_count

    inserted = 0
    deleted = 0
    if before.head is not None and after.head is not None and before.head != after.head:
        inserted, deleted = _git_numstat(project_dir, before.head, after.head)
    elif before.head is None and after.head is not None:
        inserted, deleted = _git_commit_numstat(project_dir, after.head)

    return GitMetrics(commit_count=commit_count, inserted_lines=inserted, deleted_lines=deleted)


def _git_text(project_dir: Path, args: list[str]) -> str | None:
    result = subprocess.run(
        ["git", *args],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    return text or None


def _git_int(project_dir: Path, args: list[str]) -> int | None:
    text = _git_text(project_dir, args)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _git_commit_numstat(project_dir: Path, commit: str) -> tuple[int, int]:
    result = subprocess.run(
        ["git", "show", "--numstat", "--format=", commit],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return (0, 0)
    return _parse_numstat(result.stdout)


def _git_numstat(project_dir: Path, before: str, after: str) -> tuple[int, int]:
    result = subprocess.run(
        ["git", "diff", "--numstat", f"{before}..{after}"],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return (0, 0)
    return _parse_numstat(result.stdout)


def _parse_numstat(text: str) -> tuple[int, int]:
    inserted = 0
    deleted = 0
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        if parts[0] != "-":
            inserted += int(parts[0])
        if parts[1] != "-":
            deleted += int(parts[1])
    return (inserted, deleted)


def _saved_container_session_file(project_dir: Path) -> str | None:
    try:
        session_file = load_project_state(state_path(project_dir)).pi_session_file
    except ProjectError:
        return None
    if session_file is None:
        return None
    if not session_file.startswith(str(CONTAINER_SESSION_DIR)):
        return None
    return session_file


def _project_session_storage(project_dir: Path) -> Path:
    return default_state_dir() / "pi-sessions" / project_dir.name


def _project_runtime_home(project_dir: Path) -> Path:
    return default_state_dir() / "runtime-home" / project_dir.name


def _mount(source: Path, target: Path, readonly: bool) -> str:
    suffix = ",readonly" if readonly else ""
    return f"type=bind,source={source},target={target}{suffix}"


def _optional_readonly_mount(source: Path, target: Path) -> list[str]:
    if not source.exists():
        return []
    return ["--mount", _mount(source, target, readonly=True)]


def _get_codex_bearer_token() -> str | None:
    pi = shutil_which("pi")
    if pi is None:
        return None
    result = subprocess.run(
        [pi, "auth", "print-bearer-token", "--provider", "openai-codex", "--min-expiry", "30m"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    token = result.stdout.strip()
    return token or None


def shutil_which(name: str) -> str | None:
    """Small wrapper to simplify tests around command lookup."""
    return shutil.which(name)


def _send(process: subprocess.Popen[str], payload: dict[str, object]) -> None:
    if process.stdin is None:
        raise RunnerError("Pi RPC stdin is unavailable")
    process.stdin.write(json.dumps(payload) + "\n")
    process.stdin.flush()


def _read_response(
    process: subprocess.Popen[str], request_id: str, timeout_seconds: float, required: bool = True
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        event = _read_json_line(process, timeout_seconds=max(0.0, deadline - time.monotonic()))
        if event is None:
            continue
        if event.get("type") == "response" and event.get("id") == request_id:
            return event
    if required:
        raise RunnerError(f"timed out waiting for Pi RPC response {request_id}")
    return {}


def _read_json_line(
    process: subprocess.Popen[str], timeout_seconds: float
) -> dict[str, Any] | None:
    if process.stdout is None:
        raise RunnerError("Pi RPC stdout is unavailable")
    ready, _, _ = select.select([process.stdout], [], [], timeout_seconds)
    if not ready:
        return None
    line = process.stdout.readline()
    if not line:
        return None
    try:
        data = json.loads(line.rstrip("\n"))
    except json.JSONDecodeError as exc:
        raise RunnerError(f"invalid Pi RPC JSON line: {line!r}") from exc
    if not isinstance(data, dict):
        raise RunnerError(f"invalid Pi RPC message: {data!r}")
    return data


def _session_from_response(response: dict[str, Any]) -> tuple[str | None, str | None]:
    data = response.get("data")
    if not isinstance(data, dict):
        return None, None
    session_id = data.get("sessionId")
    session_file = data.get("sessionFile")
    return (
        session_id if isinstance(session_id, str) else None,
        session_file if isinstance(session_file, str) else None,
    )


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _process_failure_message(process: subprocess.Popen[str]) -> str:
    stderr = ""
    if process.stderr is not None:
        stderr = process.stderr.read().strip()
    return f"Pi RPC process exited with {process.returncode}: {stderr or 'no stderr'}"
