from __future__ import annotations

import json
import shutil
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from moonlighter.config import Config, RunnerConfig, WorkWindow
from moonlighter.projects import (
    initialize_project,
    load_project_state,
    save_project_state,
    state_path,
)
from moonlighter.service import ServiceStatus
from moonlighter.status import render_global_status, render_project_status


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_global_status_classifies_projects_without_initializing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "projects"
    project_root.mkdir()
    active = project_root / "active"
    repo_guided = project_root / "repo-guided"
    paused = project_root / "paused"
    uninitialized = project_root / "uninitialized"
    active.mkdir()
    repo_guided.mkdir()
    paused.mkdir()
    uninitialized.mkdir()
    initialize_project(active)
    initialize_project(repo_guided)
    initialize_project(paused)
    (active / ".moon" / "brief.md").write_text("Build a thing.\n", encoding="utf-8")
    (paused / ".moon" / "brief.md").write_text("Build another thing.\n", encoding="utf-8")
    paused_state = load_project_state(state_path(paused))
    save_project_state(
        state_path(paused),
        type(paused_state)(
            schema_version=paused_state.schema_version,
            paused=True,
            disposition=paused_state.disposition,
            last_run_at=paused_state.last_run_at,
            pi_session_id=paused_state.pi_session_id,
            pi_session_file=paused_state.pi_session_file,
            last_claimed_from=paused_state.last_claimed_from,
        ),
    )
    state_dir = tmp_path / "state"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr("moonlighter.status.default_state_dir", lambda: state_dir)
    config = Config(
        project_root=project_root,
        runner=RunnerConfig(provider="openai-codex", model="gpt-5.5", thinking="medium"),
        work_windows=(WorkWindow(days="daily", start="09:00", end="17:00"),),
    )

    output = render_global_status(config, now=datetime(2026, 1, 1, 10, 0, tzinfo=ZoneInfo("UTC")))

    assert "Global pause: not paused" in output
    assert "Work window: active" in output
    assert "Service: not installed" in output
    assert "Active:\n  normal:\n    - active\n    - repo-guided (repo-guided)" in output
    assert "Needs Brief:" not in output
    assert "Paused:\n  - paused" in output
    assert "Uninitialized:\n  - uninitialized" in output
    assert not (uninitialized / ".moon").exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_project_status_reports_uninitialized_without_initializing(tmp_path: Path) -> None:
    project_root = tmp_path / "projects"
    project = project_root / "alpha"
    project.mkdir(parents=True)
    config = Config(
        project_root=project_root,
        runner=RunnerConfig(provider="openai-codex", model="gpt-5.5", thinking="medium"),
    )

    output = render_project_status(config, "alpha")

    assert "State: uninitialized" in output
    assert not (project / ".moon").exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_project_status_shows_priority(tmp_path: Path) -> None:
    project_root = tmp_path / "projects"
    project = project_root / "alpha"
    initialize_project(project)
    state = load_project_state(state_path(project))
    save_project_state(state_path(project), replace(state, priority="high"))
    config = Config(
        project_root=project_root,
        runner=RunnerConfig(provider="openai-codex", model="gpt-5.5", thinking="medium"),
    )

    output = render_project_status(config, "alpha")

    assert "Priority: high" in output


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_project_status_shows_repo_guided_projects_as_eligible(tmp_path: Path) -> None:
    project_root = tmp_path / "projects"
    project = project_root / "alpha"
    initialize_project(project)
    config = Config(
        project_root=project_root,
        runner=RunnerConfig(provider="openai-codex", model="gpt-5.5", thinking="medium"),
    )

    output = render_project_status(config, "alpha")

    assert "Disposition: active" in output
    assert "Guidance: repo-guided" in output
    assert "Brief: placeholder" in output
    assert "Autonomous work: eligible; runner will inspect repository context" in output
    assert "Needs brief:" not in output


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_project_status_shows_last_three_run_summaries(tmp_path: Path) -> None:
    project_root = tmp_path / "projects"
    project = project_root / "alpha"
    initialize_project(project)
    logs = project / ".moon" / "logs"
    for index in range(4):
        (logs / f"2026-01-0{index}.md").write_text(f"summary {index}\nmore\n", encoding="utf-8")
    config = Config(
        project_root=project_root,
        runner=RunnerConfig(provider="openai-codex", model="gpt-5.5", thinking="medium"),
    )

    output = render_project_status(config, "alpha")

    assert "Recent runs:" in output
    assert "summary 3" in output
    assert "summary 2" in output
    assert "summary 1" in output
    assert "summary 0" not in output


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_project_status_shows_feedback_request_and_brief_command(tmp_path: Path) -> None:
    project_root = tmp_path / "projects"
    project = project_root / "alpha"
    initialize_project(project)
    state = load_project_state(state_path(project))
    save_project_state(
        state_path(project),
        type(state)(
            schema_version=state.schema_version,
            paused=state.paused,
            disposition="needs_direction",
            last_run_at=state.last_run_at,
            pi_session_id=state.pi_session_id,
            pi_session_file=state.pi_session_file,
            last_claimed_from=state.last_claimed_from,
            disposition_summary="Please clarify the target UI.",
        ),
    )
    config = Config(
        project_root=project_root,
        runner=RunnerConfig(provider="openai-codex", model="gpt-5.5", thinking="medium"),
    )

    output = render_project_status(config, "alpha")

    assert "Feedback requested:" in output
    assert "Please clarify the target UI." in output
    assert "Edit guidance: moon brief alpha" in output


def test_running_moon_containers_parses_docker_ps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("moonlighter.status.shutil.which", lambda _name: "/usr/bin/docker")

    class Result:
        returncode = 0
        stdout = (
            '{"Labels":"moonlighter=true,moonlighter.project=alpha",'
            '"RunningFor":"3 minutes","Names":"moon-alpha"}\n'
        )

    monkeypatch.setattr("moonlighter.status.subprocess.run", lambda *_args, **_kwargs: Result())

    from moonlighter.status import running_moon_containers

    containers = running_moon_containers()

    assert containers == ({"project": "alpha", "running_for": "3 minutes", "name": "moon-alpha"},)


def test_global_status_shows_systemd_service_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "projects"
    project_root.mkdir()
    service_path = tmp_path / "moon.service"
    timer_path = tmp_path / "moon.timer"
    service_path.write_text("unit", encoding="utf-8")
    timer_path.write_text("unit", encoding="utf-8")
    monkeypatch.setattr("moonlighter.status.service_unit_path", lambda: service_path)
    monkeypatch.setattr("moonlighter.status.timer_unit_path", lambda: timer_path)
    monkeypatch.setattr(
        "moonlighter.status.read_service_status",
        lambda: ServiceStatus(
            service_path=service_path,
            timer_path=timer_path,
            service_installed=True,
            timer_installed=True,
            timer_enabled=True,
            timer_active=True,
            service_active=False,
            list_timers=None,
        ),
    )
    monkeypatch.setattr("moonlighter.status.default_state_dir", lambda: tmp_path / "state")
    config = Config(
        project_root=project_root,
        runner=RunnerConfig(provider="openai-codex", model="gpt-5.5", thinking="medium"),
    )

    output = render_global_status(config)

    assert "Service: timer enabled, active" in output


def test_global_status_shows_last_known_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "projects"
    project_root.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "status.json").write_text(
        json.dumps({"budget": "5h: 80%, weekly: 60%"}), encoding="utf-8"
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr("moonlighter.status.default_state_dir", lambda: state_dir)
    config = Config(
        project_root=project_root,
        runner=RunnerConfig(provider="openai-codex", model="gpt-5.5", thinking="medium"),
    )

    output = render_global_status(config)

    assert "Last-known budget: 5h: 80%, weekly: 60%" in output
