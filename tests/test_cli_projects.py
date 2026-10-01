from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import moonlighter
from moonlighter.config import Config, ConfigCheckResult, RunnerConfig
from moonlighter.projects import load_project_state, save_project_state, state_path
from moonlighter.runtime_state import global_state_path


def install_config(monkeypatch: pytest.MonkeyPatch, project_root: Path, state_dir: Path) -> None:
    monkeypatch.delenv("EDITOR", raising=False)
    config = Config(
        project_root=project_root,
        runner=RunnerConfig(provider="openai-codex", model="gpt-5.5", thinking="medium"),
    )
    result = ConfigCheckResult(config_path=Path("config.toml"), config=config, issues=())
    monkeypatch.setattr(moonlighter, "check_config", lambda _path=None: result)
    monkeypatch.setattr(moonlighter, "default_state_dir", lambda: state_dir)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_moon_init_creates_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = tmp_path / "projects"
    install_config(monkeypatch, project_root, tmp_path / "state")

    moonlighter.main(["init", "alpha"])

    project_dir = project_root / "alpha"
    assert project_dir.is_dir()
    assert state_path(project_dir).exists()
    assert load_project_state(state_path(project_dir)).disposition == "active"


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_moon_init_opens_editor_when_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "projects"
    install_config(monkeypatch, project_root, tmp_path / "state")
    editor_log = tmp_path / "editor.log"
    editor = tmp_path / "editor.sh"
    editor.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$1\" > {editor_log}\n", encoding="utf-8")
    editor.chmod(0o755)
    monkeypatch.setenv("EDITOR", str(editor))

    moonlighter.main(["init", "alpha"])

    assert editor_log.read_text(encoding="utf-8").strip() == str(
        project_root / "alpha" / ".moon" / "brief.md"
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_claim_records_source_and_release_without_dest_returns_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "projects"
    source = tmp_path / "elsewhere" / "alpha"
    source.mkdir(parents=True)
    (source / "README.md").write_text("hello", encoding="utf-8")
    install_config(monkeypatch, project_root, tmp_path / "state")

    moonlighter.main(["claim", str(source)])

    claimed = project_root / "alpha"
    assert claimed.exists()
    assert not source.exists()
    assert load_project_state(state_path(claimed)).last_claimed_from == str(source)

    moonlighter.main(["release", "alpha"])

    assert source.exists()
    assert not claimed.exists()
    assert (source / "README.md").read_text(encoding="utf-8") == "hello"
    assert state_path(source).exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_release_without_dest_errors_without_claim_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project_root = tmp_path / "projects"
    install_config(monkeypatch, project_root, tmp_path / "state")
    moonlighter.main(["init", "alpha"])

    with pytest.raises(SystemExit) as exc_info:
        moonlighter.main(["release", "alpha"])

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "no recorded claim source" in captured.err


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_release_to_existing_directory_places_project_inside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "projects"
    destination = tmp_path / "skills"
    destination.mkdir()
    install_config(monkeypatch, project_root, tmp_path / "state")
    moonlighter.main(["init", "alpha"])

    moonlighter.main(["release", "alpha", str(destination)])

    assert (destination / "alpha").is_dir()
    assert not (project_root / "alpha").exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_release_errors_when_destination_subdirectory_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project_root = tmp_path / "projects"
    destination = tmp_path / "skills"
    (destination / "alpha").mkdir(parents=True)
    install_config(monkeypatch, project_root, tmp_path / "state")
    moonlighter.main(["init", "alpha"])

    with pytest.raises(SystemExit) as exc_info:
        moonlighter.main(["release", "alpha", str(destination)])

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "destination already exists" in captured.err
    assert str(destination / "alpha") in captured.err


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_pause_resume_project_and_activate_clear_disposition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "projects"
    install_config(monkeypatch, project_root, tmp_path / "state")
    moonlighter.main(["init", "alpha"])
    project_dir = project_root / "alpha"

    moonlighter.main(["pause", "alpha"])
    assert load_project_state(state_path(project_dir)).paused is True

    state = load_project_state(state_path(project_dir))
    save_project_state(
        state_path(project_dir),
        type(state)(
            schema_version=state.schema_version,
            paused=state.paused,
            disposition="complete",
            last_run_at=state.last_run_at,
            pi_session_id=state.pi_session_id,
            pi_session_file=state.pi_session_file,
            last_claimed_from=state.last_claimed_from,
        ),
    )

    moonlighter.main(["resume", "alpha"])
    resumed = load_project_state(state_path(project_dir))
    assert resumed.paused is False
    assert resumed.disposition == "active"


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_moon_brief_requires_editor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project_root = tmp_path / "projects"
    install_config(monkeypatch, project_root, tmp_path / "state")
    moonlighter.main(["init", "alpha"])

    with pytest.raises(SystemExit) as exc_info:
        moonlighter.main(["brief", "alpha"])

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "$EDITOR is not set" in captured.err
    assert ".moon/brief.md" in captured.err


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_moon_brief_supports_editor_with_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "projects"
    install_config(monkeypatch, project_root, tmp_path / "state")
    editor_log = tmp_path / "editor.log"
    editor = tmp_path / "editor.sh"
    editor.write_text(
        f'#!/bin/sh\nprintf \'%s %s\\n\' "$1" "$2" > {editor_log}\n',
        encoding="utf-8",
    )
    editor.chmod(0o755)
    monkeypatch.setenv("EDITOR", f"{editor} --wait")
    moonlighter.main(["init", "alpha"])

    moonlighter.main(["brief", "alpha"])

    assert editor_log.read_text(encoding="utf-8").strip() == (
        f"--wait {project_root / 'alpha' / '.moon' / 'brief.md'}"
    )


def test_pause_resume_global(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_dir = tmp_path / "state"
    install_config(monkeypatch, tmp_path / "projects", state_dir)

    moonlighter.main(["pause"])
    assert json.loads(global_state_path(state_dir).read_text(encoding="utf-8"))["paused"] is True

    moonlighter.main(["resume"])
    assert json.loads(global_state_path(state_dir).read_text(encoding="utf-8"))["paused"] is False
