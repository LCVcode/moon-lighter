from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from moonlighter.config import Config, RunnerConfig
from moonlighter.projects import (
    initialize_project,
    load_project_state,
    save_project_state,
    state_path,
)
from moonlighter.runner import (
    CONTAINER_HOME,
    CONTAINER_SESSION_DIR,
    MOON_WORK_CHUNK_SKILL,
    RunnerRequest,
    build_docker_command,
    collect_git_snapshot,
    diff_git_snapshots,
    prepare_runtime_home,
    work_chunk_prompt,
    write_time_left_script,
)


def test_build_docker_command_uses_ephemeral_container_and_explicit_skills(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    session_dir = tmp_path / "sessions"
    runtime_home = tmp_path / "home"
    project_dir.mkdir()
    config = Config(
        project_root=tmp_path,
        runner=RunnerConfig(provider="openai-codex", model="gpt-5.5", thinking="medium"),
    )

    command = build_docker_command(
        RunnerRequest(project_dir=project_dir, config=config), session_dir, runtime_home
    )

    assert command[:4] == ["docker", "run", "--rm", "-i"]
    assert "--read-only" in command
    assert f"HOME={CONTAINER_HOME}" in command
    assert (
        f"PATH={CONTAINER_HOME}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        in command
    )
    assert "--label" in command
    assert "moonlighter=true" in command
    assert "moonlighter.project=project" in command
    assert "--name" in command
    assert "moonlighter-runner-project" in command
    assert "--approve" in command
    assert "--mode" in command
    assert "rpc" in command
    assert "--skill" in command
    assert str(MOON_WORK_CHUNK_SKILL) in command
    assert not any(str(Path.home()) == part for part in command)
    assert any(
        f"source={project_dir.resolve(strict=False)},target=/workspace" in part for part in command
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_build_docker_command_resumes_saved_container_session(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    initialize_project(project_dir)
    state = load_project_state(state_path(project_dir))
    save_project_state(
        state_path(project_dir),
        type(state)(
            schema_version=state.schema_version,
            paused=state.paused,
            disposition=state.disposition,
            last_run_at=state.last_run_at,
            pi_session_id=state.pi_session_id,
            pi_session_file=str(CONTAINER_SESSION_DIR / "session.jsonl"),
            last_claimed_from=state.last_claimed_from,
        ),
    )
    config = Config(
        project_root=tmp_path,
        runner=RunnerConfig(provider="openai-codex", model="gpt-5.5", thinking="medium"),
    )

    command = build_docker_command(RunnerRequest(project_dir=project_dir, config=config))

    assert "--session" in command
    assert str(CONTAINER_SESSION_DIR / "session.jsonl") in command


def test_prepare_runtime_home_writes_minimal_auth_when_token_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("moonlighter.runner.shutil_which", lambda _name: "/usr/bin/pi")

    class Result:
        returncode = 0
        stdout = "token-123\n"

    monkeypatch.setattr("moonlighter.runner.subprocess.run", lambda *_args, **_kwargs: Result())

    prepare_runtime_home(tmp_path)

    auth = json.loads((tmp_path / ".pi" / "agent" / "auth.json").read_text(encoding="utf-8"))
    assert auth["openai-codex"]["type"] == "oauth"
    assert auth["openai-codex"]["access"] == "token-123"


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_git_metrics_count_commits_and_line_delta(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "moon@example.test"],
        cwd=project_dir,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Moon Test"],
        cwd=project_dir,
        check=True,
    )
    before = collect_git_snapshot(project_dir)
    (project_dir / "README.md").write_text("one\ntwo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=project_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Add README"], cwd=project_dir, check=True)
    after = collect_git_snapshot(project_dir)

    metrics = diff_git_snapshots(project_dir, before, after)

    assert metrics.commit_count == 1
    assert metrics.inserted_lines == 2
    assert metrics.deleted_lines == 0


def test_time_left_script_reports_coarse_states(tmp_path: Path) -> None:
    keep = write_time_left_script(tmp_path / "keep", deadline_epoch=4_102_444_800)
    wrap = write_time_left_script(tmp_path / "wrap", deadline_epoch=int(time.time()) + 60)
    finish = write_time_left_script(tmp_path / "finish", deadline_epoch=0)

    keep_result = subprocess.run([str(keep)], capture_output=True, text=True, check=True)
    wrap_result = subprocess.run([str(wrap)], capture_output=True, text=True, check=True)
    finish_result = subprocess.run([str(finish)], capture_output=True, text=True, check=True)

    assert keep_result.stdout.startswith("keep working:")
    assert wrap_result.stdout.startswith("wrap up:")
    assert finish_result.stdout.startswith("finish now:")
    assert "minutes" not in keep_result.stdout
    assert "seconds" not in keep_result.stdout


def test_work_chunk_prompt_mentions_agent_result_contract() -> None:
    prompt = work_chunk_prompt()

    assert "/skill:moon-work-chunk" in prompt
    assert ".moon/state.json" in prompt
    assert "disposition" in prompt
    assert "moon-time-left" in prompt


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_agent_result_consumption_helpers_shape(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    initialize_project(project_dir)
    state = load_project_state(state_path(project_dir))
    save_project_state(state_path(project_dir), state)

    assert load_project_state(state_path(project_dir)).disposition == "active"
