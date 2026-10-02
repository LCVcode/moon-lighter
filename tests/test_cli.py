from __future__ import annotations

from pathlib import Path

import pytest

import moonlighter
from moonlighter import main
from moonlighter.config import Config, RunnerConfig


def test_main_without_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    main([])

    captured = capsys.readouterr()
    assert "usage: moon" in captured.out
    assert "status" in captured.out
    assert "work" in captured.out
    assert "run" in captured.out
    assert "completion" in captured.out
    assert "setup" in captured.out
    assert "light                " not in captured.out
    assert (
        "{config,completion,setup,init,claim,release,activate,brief,priority,pause,resume,status,run,work}"
        in captured.out
    )


def test_completion_command_prints_shellcode(capsys: pytest.CaptureFixture[str]) -> None:
    main(["completion", "bash"])

    captured = capsys.readouterr()
    assert "moon" in captured.out
    assert "complete" in captured.out


def test_setup_completion_prints_snippet(capsys: pytest.CaptureFixture[str]) -> None:
    main(["setup", "completion", "--shell", "bash", "--print"])

    captured = capsys.readouterr()
    assert "# >>> moon completion >>>" in captured.out
    assert 'eval "$(moon completion bash)"' in captured.out


def test_setup_completion_installs_managed_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = tmp_path / ".bashrc"
    monkeypatch.setattr(moonlighter, "completion_startup_path", lambda _shell: rc)

    main(["setup", "completion", "--shell", "bash", "--yes"])
    main(["setup", "completion", "--shell", "bash", "--yes"])

    text = rc.read_text(encoding="utf-8")
    assert text.count("# >>> moon completion >>>") == 1
    captured = capsys.readouterr()
    assert "already installed" in captured.out


def test_complete_project_names_lists_configured_project_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    (root / "alpha").mkdir()
    (root / "beta").mkdir()
    (root / "notes.txt").write_text("ignore", encoding="utf-8")
    config = Config(
        project_root=root,
        runner=RunnerConfig(provider="openai-codex", model="gpt-5.5", thinking="medium"),
    )
    monkeypatch.setattr(moonlighter, "load_config_no_validation", lambda: config)

    assert moonlighter.complete_project_names("a") == ["alpha"]
