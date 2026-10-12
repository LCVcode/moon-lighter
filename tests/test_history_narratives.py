from __future__ import annotations

import os

import pytest

from moonlighter.activity_report_view import measure
from moonlighter.activity_reports import Total
from moonlighter.history_duration import format_elapsed
from moonlighter.report_view import detail_lines, report_lines
from moonlighter.run_history import format_duration_seconds
from moonlighter.work_reports import ChunkReport, SessionReport


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (-1, "0s"),
        (0, "0s"),
        (0.004, "<0.01s"),
        (0.034, "0.03s"),
        (0.5, "0.5s"),
        (3, "3s"),
        (3.9, "3s"),
        (59.9, "59s"),
        (60, "1m"),
        (480, "8m"),
        (3600, "1h"),
    ],
)
def test_short_work_durations_do_not_round_down_to_zero_minutes(seconds, expected) -> None:
    assert format_elapsed(seconds) == expected
    assert format_duration_seconds(seconds) == expected
    assert measure(Total(seconds), duration=True) == expected


def test_labeled_narratives_keep_hanging_indent() -> None:
    value = "Permission denied while preparing the worker environment; check permissions and retry."
    lines = detail_lines("error", value, "  ", width=42)
    assert len(lines) > 1
    assert lines[0].startswith("  error: ")
    assert all(line.startswith(" " * 9) for line in lines[1:])
    assert all(len(line) <= 42 for line in lines)
    restored = " ".join([lines[0].removeprefix("  error: "), *[line.strip() for line in lines[1:]]])
    assert restored == value


def test_session_errors_and_stop_reasons_wrap_with_tree_guides(monkeypatch) -> None:
    monkeypatch.setattr(
        "moonlighter.report_view.shutil.get_terminal_size",
        lambda _fallback: os.terminal_size((72, 24)),
    )
    report = SessionReport(
        "one",
        "2026-01-01T00:00:00+00:00",
        "work",
        "manual",
        None,
        status="failed",
        elapsed_seconds=3,
        error="Could not start the worker because its runtime directory "
        "was inaccessible; fix the directory permissions and retry.",
        stop_reason="Work ended before execution because the worker environment "
        "could not be prepared safely; no project changes were made.",
    )
    lines = report_lines(report, False)
    error_start = next(i for i, line in enumerate(lines) if "error:" in line)
    stop_start = next(i for i, line in enumerate(lines) if "stopped:" in line)
    assert lines[error_start].startswith("  ├─ error:")
    assert all(line.startswith("  │         ") for line in lines[error_start + 1 : stop_start])
    assert lines[stop_start].startswith("  └─ stopped:")
    assert all(line.startswith(" " * 13) for line in lines[stop_start + 1 :])
    assert all(len(line) <= 72 for line in lines[error_start:])
    assert "Duration: 3s" in lines[0]


def test_chunk_error_and_detailed_stop_reason_wrap_in_their_branch(monkeypatch) -> None:
    monkeypatch.setattr(
        "moonlighter.report_view.shutil.get_terminal_size",
        lambda _fallback: os.terminal_size((70, 24)),
    )
    report = SessionReport(
        "one", "2026-01-01T00:00:00+00:00", "work", "manual", None, status="failed"
    )
    message = (
        "The worker stopped because its environment was unavailable and further "
        "execution would not preserve the current project safely."
    )
    report.chunks = [
        ChunkReport(
            "one/1", "alpha", report.started_at, status="failed", error=message, stop_reason=message
        )
    ]
    lines = report_lines(report, False, details=True)
    error_start = next(i for i, line in enumerate(lines) if "error:" in line)
    stop_start = next(i for i, line in enumerate(lines) if "Stopped:" in line)
    assert stop_start - error_start > 1
    assert len(lines) - stop_start > 1
    assert all(len(line) <= 70 for line in lines[error_start:])
    assert any("│" in line for line in lines[error_start + 1 : stop_start])
