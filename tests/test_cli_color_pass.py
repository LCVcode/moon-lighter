from __future__ import annotations

from pathlib import Path

import pytest

import moonlighter
from moonlighter.cli_output import color_enabled, labelled, paint, paint_priority
from moonlighter.colors import CYAN, GREEN, RED, RESET, YELLOW
from moonlighter.config import Config, ConfigCheckResult, ConfigIssue, RunnerConfig
from moonlighter.projects import initialize_project
from moonlighter.service import ServiceStatus
from moonlighter.text_layout import plain
from moonlighter.tick import TickResult


@pytest.fixture
def isolated_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    root = tmp_path / "projects"
    initialize_project(root / "alpha")
    config = Config(root, RunnerConfig("openai-codex", "test", "medium"))
    result = ConfigCheckResult(tmp_path / "config.toml", config, ())
    monkeypatch.setattr(moonlighter, "load_valid_config", lambda: config)
    monkeypatch.setattr(moonlighter, "check_config", lambda *_args: result)
    monkeypatch.setattr(moonlighter, "check_budget", lambda *_args: None)
    monkeypatch.setattr(
        moonlighter, "run_tick", lambda *_args, **_kw: TickResult(0, 0, 0, "test gate")
    )
    monkeypatch.setattr(moonlighter, "resolve_moon_executable", lambda *_: Path("/usr/bin/moon"))
    monkeypatch.setattr(
        moonlighter, "install_units", lambda *_: (tmp_path / "service", tmp_path / "timer")
    )
    monkeypatch.setattr(moonlighter, "uninstall_units", lambda: (True, True))
    for name in ("enable_timer", "disable_timer", "reload_systemd_user"):
        monkeypatch.setattr(moonlighter, name, lambda: None)
    monkeypatch.setattr(
        moonlighter,
        "read_service_status",
        lambda: ServiceStatus(
            tmp_path / "service",
            tmp_path / "timer",
            True,
            False,
            True,
            None,
            False,
            "NEXT  LEFT  UNIT\nfixture data",
        ),
    )
    monkeypatch.setattr(
        "moonlighter.status._render_service_status", lambda **_: ["Service: simulated"]
    )
    monkeypatch.setattr(
        "moonlighter.status._render_runner_status", lambda **_: ["Runner: simulated"]
    )
    return config


HUMAN_COMMANDS = [
    ["config", "init"],
    ["config", "check"],
    ["init", "new"],
    ["activate", "alpha"],
    ["priority"],
    ["priority", "alpha"],
    ["priority", "alpha", "urgent"],
    ["pause"],
    ["resume"],
    ["pause", "alpha"],
    ["resume", "alpha"],
    ["status"],
    ["status", "alpha"],
    ["log"],
    ["report"],
    ["report", "alpha"],
    ["run"],
    ["work"],
    ["service", "install"],
    ["service", "enable"],
    ["service", "disable"],
    ["service", "status"],
    ["service", "uninstall"],
    ["setup", "completion", "--shell", "bash", "--yes"],
]


@pytest.mark.parametrize("command", HUMAN_COMMANDS)
def test_human_commands_honor_force_and_never(isolated_cli, capsys, command) -> None:
    moonlighter.main([*command, "--color", "always"])
    colored = capsys.readouterr().out
    assert "\033[" in colored, command
    moonlighter.main([*command, "--color", "never"])
    assert "\033[" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "command",
    [
        ["completion", "bash"],
        ["completion", "zsh"],
        ["completion", "fish"],
        ["setup", "completion", "--print", "--shell", "bash"],
        ["setup", "completion", "--print", "--shell", "zsh"],
        ["setup", "completion", "--print", "--shell", "fish"],
        ["service", "print"],
        ["service", "install", "--print"],
        ["--version"],
    ],
)
def test_generated_outputs_remain_byte_identical_with_forced_color(isolated_cli, capsys, command):
    outputs = []
    for choice in ("always", "never"):
        try:
            moonlighter.main(["--color", choice, *command])
        except SystemExit as exc:
            assert exc.code == 0
        outputs.append(capsys.readouterr().out)
    assert outputs[0] == outputs[1]
    assert "\033[" not in outputs[0]


@pytest.mark.parametrize(
    "command",
    [
        [],
        ["config"],
        ["config", "check"],
        ["setup"],
        ["setup", "completion"],
        ["service"],
        ["service", "status"],
        ["init"],
        ["claim"],
        ["release"],
        ["activate"],
        ["brief"],
        ["priority"],
        ["pause"],
        ["resume"],
        ["status"],
        ["log"],
        ["report"],
        ["run"],
        ["work"],
    ],
)
def test_help_colors_and_plain_help_have_identical_text(capsys, command) -> None:
    outputs = []
    for choice in ("always", "never"):
        with pytest.raises(SystemExit) as exc:
            moonlighter.main([*command, "--color", choice, "--help"])
        assert exc.value.code == 0
        outputs.append(capsys.readouterr().out)
    assert CYAN in outputs[0]
    assert plain(outputs[0]) == outputs[1]


def test_claim_release_and_brief_colors_preserve_paths(isolated_cli, tmp_path, monkeypatch, capsys):
    source = tmp_path / "imported"
    source.mkdir()
    moonlighter.main(["claim", str(source), "--color", "always"])
    output = capsys.readouterr().out
    assert GREEN + "Claimed project" + RESET in output
    assert str(isolated_cli.project_root / "imported") in plain(output)
    moonlighter.main(["release", "imported", "--color", "always"])
    assert GREEN + "Released project" + RESET in capsys.readouterr().out
    assert source.exists()
    monkeypatch.setattr(moonlighter, "open_editor_for_brief", lambda *_a, **_kw: True)
    moonlighter.main(["brief", "alpha", "--color", "always"])
    assert CYAN + "Brief" + RESET in capsys.readouterr().out


def test_color_flags_inherit_and_override_at_any_command_level() -> None:
    parser = moonlighter.build_parser()
    assert parser.parse_args(["--color", "always", "service", "status"]).color == "always"
    assert parser.parse_args(["service", "--color", "always", "status"]).color == "always"
    assert parser.parse_args(["--color", "always", "status", "--color", "never"]).color == "never"
    assert parser.parse_args(["log"]).color == "auto"
    assert moonlighter.normalize_command_aliases(["--color=always", "tick"]) == [
        "--color=always",
        "work",
    ]


def test_environment_and_redirected_stream_policy(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    assert color_enabled("auto")
    monkeypatch.setenv("NO_COLOR", "")
    assert not color_enabled("auto")
    assert color_enabled("always")
    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setenv("TERM", "dumb")
    assert not color_enabled("auto")
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    assert not color_enabled("auto")
    assert not color_enabled("never")


def test_errors_use_stderr_and_their_own_tty_policy(capsys, monkeypatch) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    with pytest.raises(SystemExit) as exc:
        moonlighter.main(["not-a-command"])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == "" and RED in captured.err
    with pytest.raises(SystemExit):
        moonlighter.main(["log", "--limit", "0", "--color", "never"])
    assert "\033[" not in capsys.readouterr().err


def test_color_flags_after_literal_separator_are_not_interpreted(isolated_cli, capsys) -> None:
    moonlighter.main(["init", "--", "--color"])
    output = capsys.readouterr().out
    assert "\033[" not in output
    assert (isolated_cli.project_root / "--color").exists()


def test_color_context_does_not_leak_between_invocations(capsys) -> None:
    with pytest.raises(SystemExit):
        moonlighter.main(["--color", "always", "--help"])
    assert "\033[" in capsys.readouterr().out
    assert not color_enabled()
    with pytest.raises(SystemExit):
        moonlighter.main(["--help"])
    assert "\033[" not in capsys.readouterr().out


def test_labels_do_not_color_paths_or_prose() -> None:
    text = "  └─ Tokens: 12 · Duration: 3s\nPath: /tmp/alpha\nThis is ordinary prose."
    rendered = labelled(text, enabled=True)
    assert plain(rendered) == text
    assert CYAN + "Tokens:" + RESET in rendered
    assert CYAN + "Duration:" + RESET in rendered
    assert rendered.endswith("/tmp/alpha\nThis is ordinary prose.")
    assert paint("Initialized project: /tmp/alpha", "success", enabled=True) == (
        GREEN + "Initialized project" + RESET + ": /tmp/alpha"
    )
    assert RED in paint_priority("urgent", enabled=True)


def test_config_diagnostics_have_semantic_colors(isolated_cli, monkeypatch, capsys) -> None:
    config = isolated_cli
    result = ConfigCheckResult(
        Path("/tmp/config"),
        config,
        (ConfigIssue("warning", "fixture warning"), ConfigIssue("error", "fixture error")),
    )
    monkeypatch.setattr(moonlighter, "check_config", lambda: result)
    with pytest.raises(SystemExit) as exc:
        moonlighter.main(["config", "check", "--color", "always"])
    assert exc.value.code == 1
    output = capsys.readouterr().out
    assert YELLOW + "WARNING" in output and RED + "ERROR" in output
