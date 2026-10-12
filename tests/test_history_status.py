from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from moonlighter.history_queries import load_history, project_work, select_records
from moonlighter.history_status import global_history_lines, project_history_lines
from moonlighter.projects import ProjectState
from moonlighter.status import recent_run_summaries
from moonlighter.work_reports import ChunkReport, SessionReport, save_report


def captured(state: Path, run_id: str = "old", *, status: str = "success") -> SessionReport:
    report = SessionReport(
        run_id,
        "2026-01-01T00:00:00+00:00",
        "work",
        "systemd",
        None,
        status=status,
        elapsed_seconds=60,
    )
    report.chunks = [
        ChunkReport(
            run_id + "/1",
            "alpha",
            report.started_at,
            status=status,
            ended_at="2026-01-01T00:01:00+00:00",
            elapsed_seconds=60,
            summary="Implemented imports",
            current_state="Imports ready",
            next_step="Test malformed rows",
            disposition="active",
        )
    ]
    save_report(state, report)
    return report


def state() -> ProjectState:
    return ProjectState(
        schema_version=1,
        paused=False,
        disposition="active",
        priority="normal",
        last_run_at=None,
        pi_session_id=None,
        pi_session_file=None,
        last_claimed_from=None,
    )


def test_project_context_does_not_override_newer_state(tmp_path: Path) -> None:
    captured(tmp_path)
    current = replace(state(), disposition="complete", disposition_summary="MVP verified")
    output = "\n".join(project_history_lines(tmp_path, "alpha", current))
    assert "Summary: MVP verified" in output
    assert "Historical handoff" in output
    assert "Recorded next step: Test malformed rows" in output
    assert "remains authoritative" in output


def test_recent_failure_does_not_erase_meaningful_context(tmp_path: Path) -> None:
    captured(tmp_path)
    failed = captured(tmp_path, "new", status="failed")
    failed.started_at = "2026-01-02T00:00:00+00:00"
    failed.chunks[0] = replace(
        failed.chunks[0],
        started_at=failed.started_at,
        summary=None,
        current_state=None,
        next_step=None,
        error="timeout",
    )
    save_report(tmp_path, failed)
    output = "\n".join(project_history_lines(tmp_path, "alpha", state()))
    assert "Latest outcome: failed" in output
    assert "Reason: timeout" in output
    assert "Imports ready" in output
    assert "Historical handoff" in output
    assert "Last successful work: 2026-01-01" in output


def test_shared_queries_preserve_valid_data_and_surface_damage(tmp_path: Path) -> None:
    captured(tmp_path)
    (tmp_path / "runs.jsonl").write_text("broken\n")
    (tmp_path / "reports" / "broken.json").write_text("{}")
    history = load_history(tmp_path)
    assert len(history.records) == 1
    assert len(history.warnings) == 2
    assert len(project_work(history.records, "alpha")) == 1
    assert select_records(history.records, project="other") == ()
    assert "History incomplete" in "\n".join(global_history_lines(tmp_path))


def test_status_reads_do_not_reconcile_or_modify_reports(tmp_path: Path) -> None:
    report = captured(tmp_path, status="running")
    before = {path: path.read_bytes() for path in (tmp_path / "reports").glob("*.json")}
    output = "\n".join(global_history_lines(tmp_path))
    assert "running/unfinished" in output
    assert before == {path: path.read_bytes() for path in before}
    stored = load_history(tmp_path).records[0].report
    assert stored is not None and stored.status == report.status


def test_heading_only_logs_are_not_summaries(tmp_path: Path) -> None:
    logs = tmp_path / ".moon" / "logs"
    logs.mkdir(parents=True)
    (logs / "3.md").write_text("# Chunk Summary\n## Changes\n")
    (logs / "2.md").write_text("# Chunk Summary\n\nImplemented useful behavior\n")
    (logs / "1.md").write_text("")
    assert recent_run_summaries(tmp_path) == ("Implemented useful behavior",)


def test_no_history_is_explicit(tmp_path: Path) -> None:
    assert "Recorded work: no data" in project_history_lines(tmp_path, "alpha", state())
    assert "  Last successful work: no data" in global_history_lines(tmp_path)
