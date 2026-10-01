from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from moonlighter.projects import (
    AGENT_RESULT_FILE_NAME,
    BRIEF_PLACEHOLDER,
    LOGS_DIR_NAME,
    STATE_FILE_NAME,
    STATUS_FILE_NAME,
    ProjectError,
    agent_result_path,
    brief_path,
    discover_projects,
    initialize_project,
    load_project_state,
    moon_dir,
    parse_agent_result,
    parse_project_state,
    state_path,
    status_path,
)


def test_discover_projects_uses_direct_child_directories_only(tmp_path: Path) -> None:
    project_root = tmp_path / "projects"
    project_root.mkdir()
    (project_root / "alpha").mkdir()
    (project_root / "zeta").mkdir()
    (project_root / "alpha" / "nested").mkdir()
    (project_root / "notes.txt").write_text("ignore me", encoding="utf-8")
    moon_dir(project_root / "zeta").mkdir()

    projects = discover_projects(project_root)

    assert [project.name for project in projects] == ["alpha", "zeta"]
    assert [project.initialized for project in projects] == [False, True]


def test_discover_projects_rejects_missing_root(tmp_path: Path) -> None:
    with pytest.raises(ProjectError, match="project root does not exist"):
        discover_projects(tmp_path / "missing")


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_initialize_project_creates_standard_structure(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"

    initialize_project(project_dir)

    assert moon_dir(project_dir).is_dir()
    assert (moon_dir(project_dir) / LOGS_DIR_NAME).is_dir()
    assert brief_path(project_dir).read_text(encoding="utf-8") == BRIEF_PLACEHOLDER
    assert status_path(project_dir).name == STATUS_FILE_NAME
    assert state_path(project_dir).name == STATE_FILE_NAME
    assert agent_result_path(project_dir).name == AGENT_RESULT_FILE_NAME
    assert not agent_result_path(project_dir).exists()
    assert load_project_state(state_path(project_dir)).disposition == "active"
    assert (project_dir / ".git").exists()
    assert ".moon/" in (project_dir / ".gitignore").read_text(encoding="utf-8").splitlines()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_initialize_project_does_not_overwrite_existing_files(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    moon_dir(project_dir).mkdir(parents=True)
    brief_path(project_dir).write_text("existing brief", encoding="utf-8")
    status_path(project_dir).write_text("existing status", encoding="utf-8")
    state_path(project_dir).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "paused": True,
                "disposition": "tabled",
                "last_run_at": None,
                "pi_session_id": "session",
                "pi_session_file": None,
                "last_claimed_from": None,
            }
        ),
        encoding="utf-8",
    )
    (project_dir / ".gitignore").write_text("dist/\n", encoding="utf-8")

    initialize_project(project_dir)

    assert brief_path(project_dir).read_text(encoding="utf-8") == "existing brief"
    assert status_path(project_dir).read_text(encoding="utf-8") == "existing status"
    assert load_project_state(state_path(project_dir)).disposition == "tabled"
    assert (project_dir / ".gitignore").read_text(encoding="utf-8") == "dist/\n.moon/\n"


def test_parse_project_state_accepts_valid_state() -> None:
    state = parse_project_state(
        {
            "schema_version": 1,
            "paused": False,
            "disposition": "needs_direction",
            "last_run_at": "2026-01-01T00:00:00Z",
            "pi_session_id": None,
            "pi_session_file": "/tmp/session.json",
            "last_claimed_from": "/tmp/source",
        }
    )

    assert state.disposition == "needs_direction"
    assert state.last_run_at == "2026-01-01T00:00:00Z"
    assert state.last_claimed_from == "/tmp/source"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({}, "missing required key: schema_version"),
        (
            {
                "schema_version": 2,
                "paused": False,
                "disposition": "active",
                "last_run_at": None,
                "pi_session_id": None,
                "pi_session_file": None,
                "last_claimed_from": None,
            },
            "state.schema_version must be 1",
        ),
        (
            {
                "schema_version": 1,
                "paused": False,
                "disposition": "unknown",
                "last_run_at": None,
                "pi_session_id": None,
                "pi_session_file": None,
                "last_claimed_from": None,
            },
            "disposition must be one of",
        ),
        (
            {
                "schema_version": 1,
                "paused": "no",
                "disposition": "active",
                "last_run_at": None,
                "pi_session_id": None,
                "pi_session_file": None,
                "last_claimed_from": None,
            },
            "paused must be a boolean",
        ),
    ],
)
def test_parse_project_state_rejects_invalid_state(data: dict[str, object], message: str) -> None:
    with pytest.raises(ProjectError, match=message):
        parse_project_state(data)


@pytest.mark.parametrize("disposition", ["active", "needs_direction", "complete", "tabled"])
def test_parse_agent_result_accepts_valid_dispositions(disposition: str) -> None:
    result = parse_agent_result({"disposition": disposition, "summary": "done"})

    assert result.disposition == disposition
    assert result.summary == "done"


def test_parse_agent_result_rejects_invalid_disposition() -> None:
    with pytest.raises(ProjectError, match="disposition must be one of"):
        parse_agent_result({"disposition": "stuck"})
