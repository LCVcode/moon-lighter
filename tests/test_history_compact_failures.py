from __future__ import annotations

import os
from pathlib import Path

from moonlighter.activity_report_view import render_activity_report
from moonlighter.colors import RED, RESET
from moonlighter.history_queries import load_history
from moonlighter.run_history import render_run_log
from moonlighter.text_layout import plain, render_table, visible_width
from moonlighter.work_reports import ChunkReport, SessionReport, TokenUsage, save_report


def test_failed_log_is_one_line_but_report_retains_context(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "moonlighter.run_history.shutil.get_terminal_size",
        lambda _fallback: os.terminal_size((80, 24)),
    )
    report = SessionReport(
        "failure-id",
        "2026-01-01T00:00:00+00:00",
        "run",
        "manual",
        "alpha",
        status="failed",
        error="Docker runtime failed because the worker could "
        "not mount the workspace. Check permissions and retry.",
    )
    report.chunks = [
        ChunkReport(
            "one",
            "alpha",
            report.started_at,
            status="failed",
            summary="Retained useful work context",
            tokens=TokenUsage(total=10),
        )
    ]
    save_report(tmp_path, report)
    history = load_history(tmp_path)
    log = render_run_log(history.records, color=True)
    lines = log.splitlines()[2:]
    assert len(lines) == 1
    assert RED + "failed" + RESET in lines[0]
    assert "Docker runtime" in lines[0] and lines[0].endswith("…")
    assert visible_width(lines[0]) <= 80
    detailed = render_activity_report(history, details=True)
    assert "Retained useful work context" in detailed and "Check permissions and retry." in detailed
    assert "Tokens: 10" in detailed


def test_failed_work_uses_child_reason_and_names_the_project(tmp_path) -> None:
    report = SessionReport(
        "one", "2026-01-01T00:00:00+00:00", "work", "manual", None, status="failed"
    )
    report.chunks = [
        ChunkReport("one/1", "alpha", report.started_at, status="success"),
        ChunkReport("one/2", "beta", report.started_at, status="failed", error="worker crashed"),
    ]
    save_report(tmp_path, report)
    log = render_run_log(load_history(tmp_path).records)
    assert "beta: worker crashed" in log
    assert len(log.splitlines()[2:]) == 1


def test_details_report_project_table_stays_aligned(tmp_path) -> None:
    report = SessionReport(
        "one", "2026-01-01T00:00:00+00:00", "work", "manual", None, status="success"
    )
    report.chunks = [
        ChunkReport(
            "one/1",
            "alpha",
            report.started_at,
            status="success",
            elapsed_seconds=3,
            tokens=TokenUsage(total=1200),
        ),
        ChunkReport(
            "one/2",
            "项目",
            report.started_at,
            status="success",
            elapsed_seconds=480,
            tokens=TokenUsage(total=1000000, partial=True),
        ),
        ChunkReport("one/3", "long-project-name", report.started_at, status="success"),
    ]
    save_report(tmp_path, report)
    history = load_history(tmp_path)
    colored = render_activity_report(history, details=True, color=True)
    assert plain(colored) == render_activity_report(history, details=True, color=False)
    lines = plain(colored).splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Project "))
    table = lines[start : start + 4]
    assert len({visible_width(line) for line in table}) == 1


def test_table_columns_use_visible_widths_with_color_partial_and_wide_names() -> None:
    rows = [
        ("alpha", "1", "3s", "1,200"),
        ("项目", "2 partial", "1h 20m (partial)", "\033[33mno data\033[0m"),
        ("long-project-name", "10", "no data", "1,000,000 (partial)"),
    ]
    headers = ("Project", "Chunks", "Chunk time", "Tokens")
    colored = render_table(headers, rows)
    uncolored = render_table(headers, [tuple(plain(cell) for cell in row) for row in rows])
    assert [plain(line) for line in colored] == uncolored
    widths = [
        max(16 if i == 0 else 0, *(visible_width(row[i]) for row in [headers, *rows]))
        for i in range(4)
    ]
    assert all(visible_width(line) == sum(widths) + 6 for line in colored)
