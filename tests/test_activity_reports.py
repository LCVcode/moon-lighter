from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from moonlighter.activity_report_view import render_activity_report
from moonlighter.activity_reports import aggregate, date_range, total
from moonlighter.history_queries import History, load_history, select_records
from moonlighter.run_history import RunRecord, append_run_record
from moonlighter.work_reports import ChunkReport, SessionReport, TokenUsage, save_report


def captured(tmp_path: Path) -> History:
    report = SessionReport(
        "one",
        "2026-01-01T02:00:00+00:00",
        "work",
        "systemd",
        None,
        status="success",
        elapsed_seconds=130,
    )
    report.chunks = [
        ChunkReport(
            "one/1",
            "alpha",
            report.started_at,
            status="success",
            elapsed_seconds=60,
            tokens=TokenUsage(total=100),
            commits=1,
            inserted_lines=10,
            deleted_lines=2,
            summary="Imports ready",
            next_step="Test rows",
        ),
        ChunkReport(
            "one/2",
            "beta",
            "2026-01-01T02:01:00+00:00",
            status="success",
            elapsed_seconds=60,
            tokens=TokenUsage(total=200),
            commits=2,
            inserted_lines=20,
            deleted_lines=3,
        ),
    ]
    save_report(tmp_path, report)
    return load_history(tmp_path)


def legacy(projects=("alpha",)) -> RunRecord:
    return RunRecord(
        "old",
        "2025-01-01T00:00:00+00:00",
        "2025-01-01T00:01:00+00:00",
        60,
        "work",
        "manual",
        None,
        projects,
        "success",
        None,
        None,
        "active",
        2,
        2,
        0,
    )


def test_project_totals_do_not_include_other_children_or_parent_time(tmp_path: Path) -> None:
    history = captured(tmp_path)
    global_totals = aggregate(history.records)
    assert global_totals.tokens.value == 300
    assert global_totals.session_time.value == 130
    assert global_totals.chunk_time.value == 120
    alpha = aggregate(history.records, "alpha")
    assert alpha.chunks == 1
    assert alpha.tokens.value == 100
    assert alpha.chunk_time.value == 60
    assert alpha.commits.value == 1
    output = render_activity_report(history, project="alpha")
    assert "Tokens: 100" in output
    assert "Tokens: 300" not in output
    assert "beta" not in output
    assert "Test rows" in output
    assert "Session time:" not in output
    assert "whole sessions" in output


def test_partial_unknown_and_zero_are_distinct(tmp_path: Path) -> None:
    history = captured(tmp_path)
    report = history.records[0].report
    assert report is not None
    report.chunks[1].tokens = None
    result = aggregate(history.records)
    assert result.tokens.value == 100 and result.tokens.partial
    assert "Tokens: 100 (partial)" in render_activity_report(history)
    report.chunks[0].tokens = TokenUsage(total=0)
    result = aggregate(history.records)
    assert result.tokens.value == 0 and result.tokens.partial
    report.chunks[0].tokens = None
    assert aggregate(history.records).tokens.value is None
    assert "Tokens: no data" in render_activity_report(history)
    assert total([0]).value == 0


def test_legacy_metrics_not_attributed_to_project_or_counted_as_zero(tmp_path: Path) -> None:
    history = captured(tmp_path)
    records = history.records + (legacy(("alpha", "beta")),)
    result = aggregate(records, "alpha")
    assert result.chunks == 1 and result.chunks_partial
    assert result.tokens.value == 100 and result.tokens.partial
    assert result.chunk_time.value == 60 and result.chunk_time.partial
    single = aggregate((legacy(),), "alpha")
    assert single.chunks == 2 and not single.chunks_partial
    assert single.tokens.value is None
    assert single.session_time.value == 60
    assert single.chunk_time.value is None


def test_history_index_and_sidecar_are_not_double_counted(tmp_path: Path) -> None:
    history = captured(tmp_path)
    append_run_record(tmp_path, replace(legacy(("alpha", "beta")), run_id="one"))
    merged = load_history(tmp_path)
    assert len(merged.records) == 1
    assert aggregate(merged.records).tokens.value == 300
    assert history.records[0].run_id == merged.records[0].run_id


def test_detail_limit_does_not_limit_aggregate_totals(tmp_path: Path) -> None:
    history = captured(tmp_path)
    records = history.records + (replace(history.records[0], run_id="two"),)
    output = render_activity_report(History(records), details=True, limit=1)
    assert "Tokens: 600" in output
    assert "showing 1/2" in output
    assert output.count("Session: ") == 1


def test_manual_detail_is_not_a_duplicate_child_row(tmp_path: Path) -> None:
    history = captured(tmp_path)
    report = history.records[0].report
    assert report is not None
    report.entrypoint = "run"
    report.chunks = report.chunks[:1]
    save_report(tmp_path, report)
    output = render_activity_report(load_history(tmp_path), details=True)
    assert "    2026-01-01" not in output
    assert "Imports ready" in output


def test_range_uses_invocation_start_with_inclusive_exclusive_boundaries(tmp_path: Path) -> None:
    history = captured(tmp_path)
    start = datetime(2026, 1, 1, 2, tzinfo=UTC)
    end = datetime(2026, 1, 1, 2, 1, tzinfo=UTC)
    selected = select_records(history.records, start=start, end=end)
    assert len(selected) == 1
    assert aggregate(selected).chunks == 2  # Child starts outside range but belongs to session.
    assert select_records(history.records, end=start) == ()
    assert select_records(history.records, session="missing") == ()


def test_local_week_starts_monday_and_dst_boundary_preserves_calendar_days() -> None:
    now = datetime(2026, 3, 8, 12, tzinfo=ZoneInfo("America/New_York"))
    start, end, label = date_range(week=True, now=now)
    assert start is not None and end is not None
    assert start.weekday() == 0
    assert (end.timestamp() - start.timestamp()) / 3600 == 167
    assert label == "This week"
    start, end, _ = date_range(today=True, now=now)
    assert start is not None and end is not None
    assert (end.timestamp() - start.timestamp()) / 3600 == 23


@pytest.mark.parametrize(
    "options",
    [
        {"today": True, "week": True},
        {"week": True, "until": "2026-01-01"},
        {"since": "invalid"},
        {"since": "2026-01-02", "until": "2026-01-01"},
    ],
)
def test_invalid_ranges(options) -> None:
    with pytest.raises(ValueError):
        date_range(**options)


def test_empty_and_corrupt_history_are_explicit() -> None:
    assert "No matching sessions" in render_activity_report(History(()))
    output = render_activity_report(History((), ("corrupt report",)))
    assert "History incomplete" in output and "corrupt report" in output
