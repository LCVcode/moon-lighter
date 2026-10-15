from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from moonlighter.report_usage import (
    quota_delta,
    read_chunk_tokens,
    session_offsets,
    session_usage_lease,
)
from moonlighter.report_view import metrics, summary_lines, token_total
from moonlighter.run_history import filter_run_records, read_run_records, render_run_log
from moonlighter.work_reports import (
    ChunkReport,
    ReportLease,
    SessionReport,
    TokenUsage,
    UsageObservation,
    load_report,
    read_reports,
    report_path,
    save_report,
)


def session(entrypoint: str = "work") -> SessionReport:
    return SessionReport("test", "2026-01-01T00:00:00+00:00", entrypoint, "manual", None)


def chunk(tokens: int | None = 100) -> ChunkReport:
    return ChunkReport(
        "test/1",
        "alpha",
        "2026-01-01T00:00:00+00:00",
        tokens=TokenUsage(total=tokens) if tokens is not None else None,
    )


def test_report_roundtrip_and_lease_protects_live_owner(tmp_path: Path) -> None:
    report = session()
    report.chunks.append(chunk())
    with ReportLease(tmp_path, report):
        assert read_reports(tmp_path)[0].status == "running"
        tokens = load_report(report_path(tmp_path, report.run_id)).chunks[0].tokens
        assert tokens is not None and tokens.total == 100
        with pytest.raises(BlockingIOError), ReportLease(tmp_path, report):
            pass
    reconciled = read_reports(tmp_path)[0]
    assert reconciled.status == "interrupted"
    assert reconciled.chunks[0].status == "interrupted"
    assert reconciled.chunks[0].tokens is not None
    assert reconciled.chunks[0].tokens.total == 100
    assert reconciled.ended_at is None  # We do not invent when a crash happened.


def test_orphan_container_liveness_is_required(tmp_path: Path, monkeypatch) -> None:
    report = session()
    report.chunks.append(replace(chunk(), container="worker"))
    save_report(tmp_path, report)
    monkeypatch.setattr("moonlighter.work_reports.container_gone", lambda _name: False)
    assert read_reports(tmp_path)[0].status == "running"
    monkeypatch.setattr("moonlighter.work_reports.container_gone", lambda _name: True)
    assert read_reports(tmp_path)[0].status == "interrupted"


def test_failed_atomic_replace_keeps_previous_report(tmp_path: Path, monkeypatch) -> None:
    report = session()
    save_report(tmp_path, report)
    report.status = "success"

    def fail(*_args):
        raise OSError("disk full")

    monkeypatch.setattr("moonlighter.work_reports.os.replace", fail)
    with pytest.raises(OSError, match="disk full"):
        save_report(tmp_path, report)
    assert load_report(report_path(tmp_path, report.run_id)).status == "running"
    assert len(list((tmp_path / "reports").glob("*"))) == 1


@pytest.mark.parametrize("prefix", ["  ", "      "])
def test_summary_continuations_keep_hanging_tree_indent(prefix: str) -> None:
    summary = "Implemented several changes and validated the behavior with many focused tests. " * 3
    lines = summary_lines(summary, prefix, width=44)
    assert len(lines) > 1
    assert lines[0].startswith(prefix + "- ")
    assert all(line.startswith(prefix + "  ") for line in lines[1:])
    assert all(len(line) <= 44 for line in lines)
    assert " ".join(line.strip().removeprefix("- ") for line in lines) == summary.strip()


def test_friendly_metric_labels_and_quota_direction() -> None:
    reset = "2026-01-02T00:00:00+00:00"
    before = UsageObservation("2026-01-01T00:00:00+00:00", 80, 85, reset, reset)
    after = replace(before, five_hour_remaining=76, weekly_remaining=84)
    assert metrics(TokenUsage(total=12340), before, after, False, duration=480) == (
        "Tokens: 12,340 · Duration: 8m · Quota: 5h −4.0%, week −1.0%"
    )
    assert "−0.0%" not in metrics(None, before, before, False)
    assert "no data" in metrics(None, None, None, False)
    assert "partial" in metrics(TokenUsage(total=10, partial=True), before, after, False)


def test_partial_tokens_and_missing_values() -> None:
    assert token_total([]) is None
    result = token_total([chunk(10), chunk(None), chunk(20)])
    assert result is not None
    assert result.total == 30
    assert result.partial
    zero = token_total([chunk(0)])
    assert zero is not None and not zero.partial


def message(total: int | None = 100) -> str:
    usage = {"totalTokens": total, "input": 50, "output": 10, "cacheRead": 40}
    return json.dumps({"type": "message", "message": {"role": "assistant", "usage": usage}}) + "\n"


def test_tokens_exclude_resumed_session_and_do_not_double_count_cache(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    path.write_text(message(1000))
    baseline = session_offsets(tmp_path)
    with path.open("a") as file:
        file.write(message(100))
        file.write(message(200))
    usage = read_chunk_tokens(tmp_path, baseline)
    assert usage is not None
    assert usage.total == 300
    assert usage.cache_read == 80
    assert usage.cache_write is None
    assert not usage.partial
    assert read_chunk_tokens(tmp_path, session_offsets(tmp_path)) is None


def test_unknown_and_truncated_usage(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    path.write_text(message())
    baseline = session_offsets(tmp_path)
    path.write_text("{}\n")
    assert read_chunk_tokens(tmp_path, baseline) is None
    path.write_text(message() + message(None) + "broken\n")
    usage = read_chunk_tokens(tmp_path, {})
    assert usage is not None and usage.partial


def test_usage_lease_prevents_concurrent_project_writers(tmp_path: Path) -> None:
    with (
        session_usage_lease(tmp_path),
        pytest.raises(OSError, match="another chunk"),
        session_usage_lease(tmp_path),
    ):
        pass


def test_quota_reset_missing_and_nonoverlapping_deltas() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    reset = (now + timedelta(days=1)).isoformat()
    before = UsageObservation(now.isoformat(), 90, 80, reset, reset)
    after = replace(before, five_hour_remaining=70, weekly_remaining=78)
    assert quota_delta(before, after, "5h") == "20.0%"
    assert quota_delta(before, after, "weekly") == "2.0%"
    assert quota_delta(None, after, "5h") == "no data"
    assert quota_delta(before, replace(after, weekly_reset=None), "weekly") == "unknown reset"
    assert quota_delta(before, replace(after, weekly_remaining=100), "weekly") == "reset/changed"
    assert quota_delta(before, replace(after, checked_at=reset), "weekly") == "reset/changed"


def test_log_hierarchy_manual_flattening_and_colors(tmp_path: Path) -> None:
    report = session()
    report.status = "success"
    report.elapsed_seconds = 42
    report.chunks = [replace(chunk(), status="success", elapsed_seconds=42)]
    report.chunks[0].log_paths = [str(tmp_path / "missing.md")]
    save_report(tmp_path, report)
    records = read_run_records(tmp_path)
    output = render_run_log(records, color=True)
    assert "  └─ 2026-01-01" in output
    from moonlighter.text_layout import plain

    assert "Tokens: 100" in plain(output)
    assert "(account)" not in output
    assert "Quota:" not in output
    assert "\033[33mdetailed log unavailable" in output
    assert "detailed log unavailable" in output
    report.entrypoint = "run"
    save_report(tmp_path, report)
    output = render_run_log(read_run_records(tmp_path))
    assert "  └─ 2026-01-01" not in output
    assert "Tokens: 100" in output
    assert "\033[" not in output


def test_budget_skip_is_visible_without_children(tmp_path: Path) -> None:
    report = session()
    report.status = "skipped"
    report.stop_reason = "weekly budget below curve"
    save_report(tmp_path, report)
    records = filter_run_records(read_run_records(tmp_path), limit=20)
    assert len(records) == 1
    assert records[0].ran_chunks == 0
    assert "weekly budget" in render_run_log(records)


def test_corrupt_report_does_not_hide_valid_reports(tmp_path: Path) -> None:
    report = session()
    report.status = "success"
    save_report(tmp_path, report)
    (tmp_path / "reports" / "corrupt.json").write_text("broken")
    assert len(read_reports(tmp_path)) == 1


@pytest.mark.parametrize(
    "field,value", [("elapsed_seconds", -1), ("started_at", []), ("status", "bogus")]
)
def test_malformed_report_fields_are_rejected(tmp_path: Path, field, value) -> None:
    report = session()
    save_report(tmp_path, report)
    path = report_path(tmp_path, report.run_id)
    data = json.loads(path.read_text())
    data[field] = value
    path.write_text(json.dumps(data))
    assert read_reports(tmp_path) == ()


def test_forked_session_does_not_count_copied_old_messages(tmp_path: Path) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    old = json.loads(message(1000))
    old["message"]["timestamp"] = (now.timestamp() - 100) * 1000
    new = json.loads(message(100))
    new["message"]["timestamp"] = (now.timestamp() + 1) * 1000
    (tmp_path / "fork.jsonl").write_text(json.dumps(old) + "\n" + json.dumps(new) + "\n")
    usage = read_chunk_tokens(tmp_path, {}, now)
    assert usage is not None and usage.total == 100


def test_completed_identity_cannot_be_overwritten(tmp_path: Path) -> None:
    report = session()
    report.status = "success"
    save_report(tmp_path, report)
    with pytest.raises(OSError, match="already exists"), ReportLease(tmp_path, report):
        pass
    assert load_report(report_path(tmp_path, report.run_id)).status == "success"


@pytest.mark.parametrize(
    "code,stdout,stderr,gone",
    [
        (1, "", "error: no such object: worker", True),
        (1, "", "Error: No such object: worker", True),
        (1, "", "Error response from daemon: No such container: worker", True),
        (0, "false\n", "", True),
        (0, "true\n", "", False),
        (1, "", "Cannot connect to Docker daemon", False),
        (1, "", "permission denied", False),
        (1, "", "no such object: different-worker-name", False),
    ],
)
def test_container_absence_recognizes_docker_variants(monkeypatch, code, stdout, stderr, gone):
    from subprocess import CompletedProcess

    from moonlighter.work_reports import container_gone

    monkeypatch.setattr(
        "moonlighter.work_reports.subprocess.run",
        lambda *_args, **_kwargs: CompletedProcess([], code, stdout, stderr),
    )
    assert container_gone("worker") is gone


def test_cli_log_color_and_status_filters(tmp_path: Path, monkeypatch, capsys) -> None:
    import moonlighter

    report = session()
    report.status = "success"
    report.chunks = [replace(chunk(None), status="success")]
    save_report(tmp_path, report)
    monkeypatch.setattr(moonlighter, "default_state_dir", lambda: tmp_path)
    assert moonlighter.main(["log", "--color", "always", "--status", "success"]) is None
    assert "\033[33mno data" in capsys.readouterr().out
    assert moonlighter.main(["log", "--color", "never", "--status", "success"]) is None
    assert "\033[" not in capsys.readouterr().out
