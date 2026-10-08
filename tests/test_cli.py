from __future__ import annotations

from pathlib import Path

import pytest

import moonlighter
from moonlighter import main
from moonlighter.config import Config, RunnerConfig
from moonlighter.service import ServiceStatus


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
        "{config,completion,setup,service,init,claim,release,activate,brief,priority,pause,resume,status,run,work}"
        in captured.out
    )


def test_completion_command_prints_shellcode(capsys: pytest.CaptureFixture[str]) -> None:
    main(["completion", "bash"])

    captured = capsys.readouterr()
    assert "moon" in captured.out
    assert "complete" in captured.out


def test_service_print_outputs_units(capsys: pytest.CaptureFixture[str]) -> None:
    main(["service", "print", "--moon", "/tmp/moon", "--interval", "5m"])

    captured = capsys.readouterr()
    assert "# moon.service" in captured.out
    assert "ExecStart=/tmp/moon work" in captured.out
    assert "# moon.timer" in captured.out
    assert "OnUnitActiveSec=5min" in captured.out


def test_service_install_print_does_not_write_or_reload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    called = False

    def fail_install(*_args: object, **_kwargs: object) -> tuple[Path, Path]:
        nonlocal called
        called = True
        raise AssertionError("install should not be called")

    monkeypatch.setattr(moonlighter, "install_units", fail_install)

    main(["service", "install", "--print", "--moon", "/tmp/moon"])

    assert called is False
    assert "ExecStart=/tmp/moon work" in capsys.readouterr().out


def test_service_enable_disable_call_wrappers(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(moonlighter, "enable_timer", lambda: calls.append("enable"))
    monkeypatch.setattr(moonlighter, "disable_timer", lambda: calls.append("disable"))

    main(["service", "enable"])
    main(["service", "disable"])

    assert calls == ["enable", "disable"]
    output = capsys.readouterr().out
    assert "Enabled Moonlighter timer." in output
    assert "Disabled Moonlighter timer." in output


def test_service_status_prints_read_only_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        moonlighter,
        "read_service_status",
        lambda: ServiceStatus(
            service_path=tmp_path / "moon.service",
            timer_path=tmp_path / "moon.timer",
            service_installed=True,
            timer_installed=True,
            timer_enabled=True,
            timer_active=False,
            service_active=None,
            list_timers="NEXT LEFT LAST PASSED UNIT ACTIVATES\n",
        ),
    )

    main(["service", "status"])

    output = capsys.readouterr().out
    assert "Moonlighter service" in output
    assert "enabled: yes" in output
    assert "active: no" in output
    assert "systemctl --user list-timers" in output


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
