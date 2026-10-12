from __future__ import annotations

import os

from moonlighter.history_tree import TreeNode, render_tree
from moonlighter.report_view import report_lines
from moonlighter.work_reports import ChunkReport, SessionReport, TokenUsage


def test_tree_connectors_and_multiline_guides() -> None:
    nodes = [
        TreeNode(["totals"]),
        TreeNode(
            ["alpha"],
            [
                TreeNode(["summary", "  continuation"]),
                TreeNode(["metrics"]),
            ],
        ),
        TreeNode(["beta"], [TreeNode(["last child"])]),
    ]
    assert render_tree(nodes) == [
        "  ├─ totals",
        "  ├─ alpha",
        "  │  ├─ summary",
        "  │  │    continuation",
        "  │  └─ metrics",
        "  └─ beta",
        "     └─ last child",
    ]


def test_manual_run_remains_one_header_with_attached_summary(monkeypatch) -> None:
    monkeypatch.setattr(
        "moonlighter.report_view.shutil.get_terminal_size",
        lambda _fallback: os.terminal_size((54, 24)),
    )
    report = SessionReport(
        "one", "2026-01-01T00:00:00+00:00", "run", "manual", "alpha", status="success"
    )
    report.chunks = [
        ChunkReport(
            "one/1",
            "alpha",
            report.started_at,
            status="success",
            summary="Implemented several useful changes and validated behavior "
            "using focused regression tests and documentation.",
            commits=1,
            inserted_lines=10,
            deleted_lines=2,
            tokens=TokenUsage(total=100),
        )
    ]
    lines = report_lines(report, False)
    assert lines[0].startswith("  ├─ Tokens:")
    assert any(line.startswith("  ├─ Implemented") for line in lines)
    continuations = [line for line in lines if line.startswith("  │    ")]
    assert continuations and all(len(line) <= 54 for line in continuations)
    assert lines[-1].startswith("  └─ commits=")
    assert not any(report.started_at in line for line in lines)


def test_session_error_and_stop_reason_are_in_the_tree() -> None:
    report = SessionReport(
        "one",
        "2026-01-01T00:00:00+00:00",
        "work",
        "systemd",
        None,
        status="failed",
        error="cannot persist",
        stop_reason="worker failure",
    )
    lines = report_lines(report, False)
    assert "  ├─ error: cannot persist" in lines
    assert "  └─ stopped: worker failure" in lines
