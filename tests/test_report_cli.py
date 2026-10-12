from __future__ import annotations

from pathlib import Path

import pytest

import moonlighter
from moonlighter.work_reports import ChunkReport, SessionReport, TokenUsage, save_report


@pytest.fixture
def reports(tmp_path: Path, monkeypatch):
    report = SessionReport(
        "session-id",
        "2026-01-01T02:00:00+00:00",
        "work",
        "systemd",
        None,
        status="success",
        elapsed_seconds=130,
    )
    report.chunks = [
        ChunkReport(
            "1",
            "alpha",
            report.started_at,
            status="success",
            elapsed_seconds=60,
            tokens=TokenUsage(total=100),
            summary="Built alpha",
            next_step="Test alpha",
        ),
        ChunkReport(
            "2",
            "beta",
            report.started_at,
            status="success",
            elapsed_seconds=60,
            tokens=TokenUsage(total=200),
        ),
    ]
    save_report(tmp_path, report)
    monkeypatch.setattr(moonlighter, "default_state_dir", lambda: tmp_path)

    def no_budget(*_args):
        raise AssertionError("report must not refresh budget or launch work")

    monkeypatch.setattr(moonlighter, "check_budget", no_budget)
    monkeypatch.setattr(moonlighter, "run_tick", no_budget)
    return tmp_path


def test_global_report_and_project_contributions(reports, capsys) -> None:
    moonlighter.main(["report", "--since", "2026-01-01T00:00:00+00:00", "--color", "never"])
    output = capsys.readouterr().out
    assert "Tokens: 300" in output
    assert "alpha" in output and "beta" in output
    assert "Session: session-id" not in output
    moonlighter.main(["report", "alpha", "--since", "2026-01-01T00:00:00+00:00"])
    output = capsys.readouterr().out
    assert "Tokens: 100" in output
    assert "Built alpha" not in output and "Next: Test alpha" not in output
    assert "Latest sessions:" not in output and "Session: session-id" not in output
    assert "--details" in output
    assert "beta" not in output


def test_project_details_are_opt_in_and_keep_matching_chunks(reports, capsys) -> None:
    for selector in (["--details"], ["--session", "session-id"]):
        moonlighter.main(["report", "alpha", *selector, "--color", "never"])
        output = capsys.readouterr().out
        assert "Tokens: 100" in output
        assert "Built alpha" in output and "Next: Test alpha" in output
        assert "Session: session-id" in output
        assert "beta" not in output
        assert "Session time:" not in output


def test_session_selection(reports, capsys) -> None:
    moonlighter.main(["report", "--session", "session-id"])
    assert "Session: session-id" in capsys.readouterr().out
    with pytest.raises(SystemExit) as exc:
        moonlighter.main(["report", "--session", "absent"])
    assert exc.value.code == 1
    assert "session not found" in capsys.readouterr().err


@pytest.mark.parametrize(
    "args",
    [
        ["--since", "nope"],
        ["--week", "--until", "2026-01-01"],
        ["--limit", "0"],
    ],
)
def test_invalid_report_requests(reports, capsys, args) -> None:
    with pytest.raises(SystemExit) as exc:
        moonlighter.main(["report", *args])
    assert exc.value.code == 1
    assert "moon: error:" in capsys.readouterr().err


def test_empty_report_and_warnings(reports, capsys) -> None:
    (reports / "reports" / "corrupt.json").write_text("broken")
    moonlighter.main(["report", "absent-project"])
    output = capsys.readouterr().out
    assert "History incomplete" in output
    assert "No matching sessions" in output


def test_report_help_and_completion_are_discoverable(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        moonlighter.main(["report", "--help"])
    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert "--session" in output and "--details" in output and "--until" in output
