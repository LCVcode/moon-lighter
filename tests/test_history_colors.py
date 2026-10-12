from __future__ import annotations

import re
from pathlib import Path

import pytest

from moonlighter.colors import CYAN, GREEN, RED, RESET, YELLOW, outcome
from moonlighter.run_history import read_run_records, render_run_log
from moonlighter.work_reports import ChunkReport, SessionReport, save_report


@pytest.mark.parametrize(
    "status,code",
    [
        ("success", GREEN),
        ("failed", RED),
        ("skipped", YELLOW),
        ("interrupted", YELLOW),
        ("running", CYAN),
    ],
)
def test_status_colors_and_plain_output(status: str, code: str) -> None:
    assert outcome(status, enabled=True) == code + status + RESET
    assert outcome(status, enabled=False) == status
    assert outcome("unknown", enabled=True) == "unknown"


def test_session_and_chunk_status_words_are_colored_without_changing_alignment(tmp_path: Path):
    report = SessionReport(
        "one",
        "2026-01-01T00:00:00+00:00",
        "work",
        "manual",
        None,
        status="success",
        elapsed_seconds=60,
    )
    report.chunks = [ChunkReport("one/1", "alpha", report.started_at, status="success")]
    save_report(tmp_path, report)
    records = read_run_records(tmp_path)
    colored = render_run_log(records, color=True)
    plain = render_run_log(records, color=False)
    assert colored.count(GREEN + "success" + RESET) == 2
    assert GREEN + "alpha" not in colored
    assert GREEN + "├─" not in colored
    assert re.sub(r"\x1b\[[0-9;]*m", "", colored) == plain
    assert "\x1b[" not in plain
