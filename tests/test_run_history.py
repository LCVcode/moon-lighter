from __future__ import annotations

import json
from pathlib import Path

import pytest

from moonlighter.run_history import (
    RunHistoryError,
    RunRecord,
    RunStatus,
    append_run_record,
    filter_run_records,
    is_timer_noop,
    read_run_records,
    render_run_log,
    run_history_path,
)


def sample_record(
    run_id: str = "run-1", *, project: str = "alpha", status: RunStatus = "success"
) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        started_at="2026-01-01T00:00:00+00:00",
        ended_at="2026-01-01T00:01:00+00:00",
        elapsed_seconds=60,
        entrypoint="work",
        trigger="manual",
        requested_project=None,
        projects=(project,) if project else (),
        status=status,
        skip_reason="outside hours" if status == "skipped" else None,
        error="boom" if status == "failed" else None,
        disposition="active" if status == "success" else None,
        ran_chunks=1 if status != "skipped" else 0,
        succeeded_chunks=1 if status == "success" else 0,
        failed_chunks=1 if status == "failed" else 0,
    )


def test_append_and_read_run_records_newest_first(tmp_path: Path) -> None:
    append_run_record(tmp_path, sample_record("old", project="alpha"))
    append_run_record(tmp_path, sample_record("new", project="beta"))

    records = read_run_records(tmp_path)

    assert [record.run_id for record in records] == ["new", "old"]
    assert json.loads(run_history_path(tmp_path).read_text(encoding="utf-8").splitlines()[0])[
        "projects"
    ] == ["alpha"]


def test_filter_run_records_hides_systemd_timer_noops_by_default() -> None:
    timer_noop = RunRecord(
        run_id="noop",
        started_at="2026-01-01T00:00:00+00:00",
        ended_at="2026-01-01T00:00:01+00:00",
        elapsed_seconds=1,
        entrypoint="work",
        trigger="systemd",
        requested_project=None,
        projects=(),
        status="skipped",
        skip_reason="outside configured work windows",
        error=None,
        disposition=None,
        ran_chunks=0,
        succeeded_chunks=0,
        failed_chunks=0,
    )
    manual_skip = RunRecord(
        run_id="manual",
        started_at="2026-01-01T00:00:00+00:00",
        ended_at="2026-01-01T00:00:01+00:00",
        elapsed_seconds=1,
        entrypoint="work",
        trigger="manual",
        requested_project=None,
        projects=(),
        status="skipped",
        skip_reason="outside configured work windows",
        error=None,
        disposition=None,
        ran_chunks=0,
        succeeded_chunks=0,
        failed_chunks=0,
    )

    assert is_timer_noop(timer_noop) is True
    assert is_timer_noop(manual_skip) is True
    assert filter_run_records((timer_noop, manual_skip), limit=20) == ()
    assert filter_run_records((timer_noop, manual_skip), limit=20, include_timer_noops=True) == (
        timer_noop,
        manual_skip,
    )


def test_filter_run_records_by_project_status_and_limit(tmp_path: Path) -> None:
    records = (
        sample_record("3", project="alpha", status="failed"),
        sample_record("2", project="beta", status="success"),
        sample_record("1", project="alpha", status="success"),
    )

    filtered = filter_run_records(records, limit=1, project="alpha", status="success")

    assert [record.run_id for record in filtered] == ["1"]


def test_render_run_log_shows_recent_records() -> None:
    output = render_run_log((sample_record(project="alpha"),))

    assert "Recent Moon runs" in output
    assert "2026-01-01 00:00" in output
    assert "work/manual" in output
    assert "success" in output
    assert "alpha" in output


def test_read_run_records_rejects_invalid_json(tmp_path: Path) -> None:
    run_history_path(tmp_path).write_text("not json\n", encoding="utf-8")

    with pytest.raises(RunHistoryError, match="invalid run history JSON"):
        read_run_records(tmp_path)
