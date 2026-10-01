#!/usr/bin/env python3
"""Spike Pi RPC control behavior inside the local Moonlighter runner image.

This is not production Moonlighter code. It is a repeatable integration probe for
Milestone 1.
"""

from __future__ import annotations

import argparse
import json
import os
import select
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_IMAGE = "moonlighter-pi-rpc-spike:local"
DEFAULT_PROVIDER = "openai-codex"
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_THINKING = "minimal"


@dataclass
class RpcProcess:
    proc: subprocess.Popen[str]
    events: list[dict[str, Any]] = field(default_factory=list)

    def send(self, command: dict[str, Any]) -> None:
        if self.proc.stdin is None:
            raise RuntimeError("RPC process stdin is unavailable")
        self.proc.stdin.write(json.dumps(command) + "\n")
        self.proc.stdin.flush()

    def read_until(self, deadline: float, predicate: Any) -> dict[str, Any] | None:
        if self.proc.stdout is None:
            raise RuntimeError("RPC process stdout is unavailable")
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self.proc.stdout], [], [], 0.25)
            if not ready:
                continue
            line = self.proc.stdout.readline()
            if not line:
                continue
            event = json.loads(line)
            self.events.append(event)
            print(json.dumps(event, separators=(",", ":")))
            if predicate(event):
                return event
        return None

    def terminate(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)

        stderr = self.proc.stderr.read() if self.proc.stderr else ""
        if stderr.strip():
            print("STDERR:", stderr[:2000], file=sys.stderr)


def host_bearer_token(provider: str) -> str:
    result = subprocess.run(
        ["pi", "auth", "print-bearer-token", "--provider", provider, "--min-expiry", "30m"],
        check=True,
        capture_output=True,
        text=True,
    )
    token = result.stdout.strip()
    if not token:
        raise RuntimeError("pi returned an empty bearer token")
    return token


def write_minimal_auth(home: Path, provider: str) -> None:
    token = host_bearer_token(provider)
    auth_dir = home / ".pi" / "agent"
    auth_dir.mkdir(parents=True, exist_ok=True)
    # Expiry is intentionally approximate. The host-side pi command already ensured
    # sufficient minimum expiry before printing the token.
    expires = int((time.time() + 60 * 60) * 1000)
    (auth_dir / "auth.json").write_text(
        json.dumps({provider: {"type": "oauth", "access": token, "expires": expires}}),
        encoding="utf-8",
    )


def docker_command(base: Path, args: argparse.Namespace) -> list[str]:
    uid = os.getuid()
    gid = os.getgid()
    return [
        "docker",
        "run",
        "--rm",
        "-i",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,exec,nosuid,size=128m",
        "--user",
        f"{uid}:{gid}",
        "-e",
        "HOME=/home/moon-runtime",
        "-v",
        f"{base / 'home'}:/home/moon-runtime",
        "-v",
        f"{base / 'workspace'}:/workspace",
        "-v",
        f"{base / 'sessions'}:/sessions",
        args.image,
        "--mode",
        "rpc",
        "--session-dir",
        "/sessions",
        "--name",
        "moon-spike-control",
        "--no-skills",
        "--no-extensions",
        "--no-prompt-templates",
        "--no-context-files",
        "--provider",
        args.provider,
        "--model",
        args.model,
        "--thinking",
        args.thinking,
        "--approve",
        "--tools",
        "bash",
    ]


def start_rpc(base: Path, args: argparse.Namespace) -> RpcProcess:
    proc = subprocess.Popen(
        docker_command(base, args),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return RpcProcess(proc)


def test_idle_clear_queue(rpc: RpcProcess) -> bool:
    print("\n## idle_clear_queue")
    rpc.send({"id": "clear-idle", "type": "clear_queue"})
    event = rpc.read_until(
        time.monotonic() + 10,
        lambda e: e.get("id") == "clear-idle" and e.get("type") == "response",
    )
    return bool(event and event.get("success") is True)


def test_direct_bash_abort(rpc: RpcProcess) -> bool:
    print("\n## direct_bash_abort")
    rpc.send({"id": "bash-direct", "type": "bash", "command": "sleep 60"})
    started = rpc.read_until(
        time.monotonic() + 10,
        lambda e: e.get("type") == "bash_execution_update" and e.get("id") == "bash-direct",
    )
    # A silent command may not produce update before completion. Give it a moment,
    # then abort regardless.
    if started is None:
        print("No bash update before abort; sending abort_bash anyway.")
    rpc.send({"id": "abort-bash", "type": "abort_bash"})
    abort_response = rpc.read_until(
        time.monotonic() + 10,
        lambda e: e.get("id") == "abort-bash" and e.get("type") == "response",
    )
    bash_response = rpc.read_until(
        time.monotonic() + 10,
        lambda e: e.get("id") == "bash-direct" and e.get("command") == "bash",
    )
    return bool(
        abort_response
        and abort_response.get("success") is True
        and bash_response
        and bash_response.get("data", {}).get("cancelled") is True
    )


def test_agent_tool_abort(rpc: RpcProcess) -> bool:
    print("\n## agent_tool_abort")
    rpc.send(
        {
            "id": "prompt-tool-abort",
            "type": "prompt",
            "message": "Use the bash tool to run exactly `sleep 60`, then stop.",
        }
    )
    prompt_response = rpc.read_until(
        time.monotonic() + 15,
        lambda e: e.get("id") == "prompt-tool-abort" and e.get("type") == "response",
    )
    if not prompt_response or prompt_response.get("success") is not True:
        return False

    tool_started = rpc.read_until(
        time.monotonic() + 45,
        lambda e: e.get("type") == "tool_execution_start" and e.get("toolName") == "bash",
    )
    if tool_started is None:
        return False

    rpc.send({"id": "clear-active", "type": "clear_queue"})
    rpc.send({"id": "abort-active", "type": "abort"})

    saw_tool_aborted = False
    saw_settled = False
    saw_abort_response = False
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not saw_settled:
        event = rpc.read_until(deadline, lambda _e: True)
        if event is None:
            break
        if event.get("id") == "abort-active" and event.get("type") == "response":
            saw_abort_response = bool(event.get("success"))
        if event.get("type") == "tool_execution_end" and event.get("toolName") == "bash":
            result = event.get("result", {})
            saw_tool_aborted = event.get("isError") is True and "Command aborted" in json.dumps(
                result
            )
        if event.get("type") == "agent_settled":
            saw_settled = True

    # In observed Pi 0.85.1 behavior, clear_queue + abort may settle the agent
    # without the client seeing an abort response first. Treat settled + aborted
    # tool as the success condition, while recording whether a response appeared.
    print(
        json.dumps(
            {
                "saw_tool_aborted": saw_tool_aborted,
                "saw_settled": saw_settled,
                "saw_abort_response": saw_abort_response,
            },
            separators=(",", ":"),
        )
    )
    return saw_tool_aborted and saw_settled


def run_tests(args: argparse.Namespace) -> int:
    base = Path(tempfile.mkdtemp(prefix="moon-pi-rpc-control-"))
    try:
        (base / "workspace").mkdir()
        (base / "sessions").mkdir()
        (base / "home").mkdir()
        write_minimal_auth(base / "home", args.provider)

        rpc = start_rpc(base, args)
        try:
            results = {
                "idle_clear_queue": test_idle_clear_queue(rpc),
                "direct_bash_abort": test_direct_bash_abort(rpc),
                "agent_tool_abort": test_agent_tool_abort(rpc),
            }
        finally:
            rpc.terminate()

        print("\n## summary")
        print(json.dumps(results, indent=2, sort_keys=True))
        return 0 if all(results.values()) else 1
    finally:
        shutil.rmtree(base, ignore_errors=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--thinking", default=DEFAULT_THINKING)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return run_tests(parse_args(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
