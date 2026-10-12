from __future__ import annotations

from dataclasses import replace

from moonlighter.report_view import metrics, report_lines
from moonlighter.work_reports import ChunkReport, SessionReport, UsageObservation


def test_compact_metrics_keep_unknown_tokens_but_omit_unobserved_quota() -> None:
    compact = metrics(None, None, None, False, duration=3, show_missing=False)
    assert compact == "Tokens: no data · Duration: 3s"
    assert "Quota: 5h no data, week no data" in metrics(None, None, None, False)
    before = UsageObservation(
        "2026-01-01T00:00:00+00:00", 80, five_hour_reset="2026-01-02T00:00:00+00:00"
    )
    after = replace(before, five_hour_remaining=76)
    assert metrics(None, before, after, False, show_missing=False).endswith("Quota: 5h −4.0%")
    after.five_hour_reset = "2026-01-03T00:00:00+00:00"
    assert "reset/changed" in metrics(None, before, after, False, show_missing=False)


def test_coding_noise_is_hidden_but_retained_in_details() -> None:
    report = SessionReport("one", "2026-01-01T00:00:00+00:00", "run", "manual", "alpha")
    chunk = ChunkReport(
        "one/1", "alpha", report.started_at, commits=0, inserted_lines=0, deleted_lines=0
    )
    report.chunks = [chunk]
    assert not any("commits=" in line or "diff=" in line for line in report_lines(report, False))
    assert any("commits=0 diff=+0 -0" in line for line in report_lines(report, False, details=True))
    chunk.commits = 1
    assert any(line.endswith("commits=1") for line in report_lines(report, False))
    chunk.commits = None
    chunk.inserted_lines = 10
    chunk.deleted_lines = None
    assert any("diff=+10 -no data" in line for line in report_lines(report, False))
