"""Compact hierarchy and missing-data presentation for captured work reports."""

from __future__ import annotations

import shutil
import textwrap
from datetime import timedelta

from moonlighter.colors import outcome
from moonlighter.history_tree import TreeNode, render_tree
from moonlighter.report_usage import quota_delta
from moonlighter.schedule import format_duration
from moonlighter.work_reports import ChunkReport, SessionReport, TokenUsage, UsageObservation


def warning(text: str, color: bool) -> str:
    return f"\033[33m{text}\033[0m" if color else text


def token_total(chunks: list[ChunkReport]) -> TokenUsage | None:
    known = [chunk.tokens for chunk in chunks if chunk.tokens and chunk.tokens.total is not None]
    if not known:
        return None
    return TokenUsage(
        total=sum(usage.total or 0 for usage in known),
        partial=len(known) != len(chunks) or any(usage.partial for usage in known),
        source="chunk-sum",
    )


def metrics(
    tokens: TokenUsage | None,
    before: UsageObservation | None,
    after: UsageObservation | None,
    color: bool,
    *,
    duration: float | None = None,
    show_duration: bool = True,
) -> str:
    count = (
        warning("no data", color)
        if tokens is None or tokens.total is None
        else (f"{tokens.total:,}" + (" " + warning("partial", color) if tokens.partial else ""))
    )
    deltas = [quota_delta(before, after, window) for window in ("5h", "weekly")]
    deltas = [
        warning(value, color) if value in ("no data", "unknown reset") else value
        for value in deltas
    ]
    deltas = ["−" + value if value.endswith("%") and value != "0.0%" else value for value in deltas]
    parts = [f"Tokens: {count}"]
    if show_duration:
        elapsed = (
            warning("no data", color)
            if duration is None
            else format_duration(timedelta(seconds=duration))
        )
        parts.append(f"Duration: {elapsed}")
    parts.append(f"Quota: 5h {deltas[0]}, week {deltas[1]}")
    return " · ".join(parts)


def report_lines(
    report: SessionReport,
    color: bool,
    *,
    details: bool = False,
    include_session_duration: bool = True,
) -> list[str]:
    columns = shutil.get_terminal_size((100, 24)).columns
    if report.entrypoint == "run" and len(report.chunks) == 1:
        chunk = report.chunks[0]
        nodes = [
            TreeNode(
                [
                    metrics(
                        chunk.tokens,
                        report.budget_before,
                        report.budget_after,
                        color,
                        duration=chunk.elapsed_seconds,
                    )
                ]
            )
        ]
        nodes.extend(_context_nodes(chunk, color, details=details, width=columns - 5))
    else:
        nodes = [
            TreeNode(
                [
                    metrics(
                        token_total(report.chunks),
                        report.budget_before,
                        report.budget_after,
                        color,
                        duration=report.elapsed_seconds,
                        show_duration=include_session_duration,
                    )
                ]
            )
        ]
        for chunk in report.chunks:
            children = [
                TreeNode(
                    [
                        metrics(
                            chunk.tokens,
                            chunk.budget_before,
                            chunk.budget_after,
                            color,
                            duration=chunk.elapsed_seconds,
                        )
                    ]
                )
            ]
            children.extend(_context_nodes(chunk, color, details=details, width=columns - 8))
            nodes.append(
                TreeNode(
                    [
                        f"{chunk.started_at}  {chunk.project}  "
                        f"{outcome(chunk.status, enabled=color)}"
                    ],
                    children,
                )
            )
    if report.error:
        nodes.append(TreeNode(["error: " + " ".join(report.error.split())]))
    if report.stop_reason:
        nodes.append(TreeNode(["stopped: " + " ".join(report.stop_reason.split())]))
    return render_tree(nodes)


def _context_nodes(
    chunk: ChunkReport,
    color: bool,
    *,
    details: bool,
    width: int,
) -> list[TreeNode]:
    nodes: list[TreeNode] = []
    for line in _context(chunk, "", color, details=details, width=width):
        if line.startswith("  ") and nodes:
            nodes[-1].lines.append(line)
        else:
            nodes.append(TreeNode([line.removeprefix("- ")]))
    return nodes


def summary_lines(summary: str, prefix: str, *, width: int | None = None) -> list[str]:
    """Explicit wrapping prevents terminal continuation lines escaping the tree."""
    columns = width if width is not None else shutil.get_terminal_size((100, 24)).columns
    return textwrap.wrap(
        " ".join(summary.split()),
        width=max(columns, len(prefix) + 4),
        initial_indent=prefix + "- ",
        subsequent_indent=prefix + "  ",
    )


def _context(
    chunk: ChunkReport,
    prefix: str,
    color: bool,
    *,
    details: bool = False,
    width: int | None = None,
) -> list[str]:
    lines = []
    if chunk.summary:
        lines.extend(summary_lines(chunk.summary, prefix, width=width))
    if chunk.error:
        lines.append(prefix + "error: " + " ".join(chunk.error.split()))
    if chunk.commits is not None:
        lines.append(
            prefix + f"commits={chunk.commits} diff=+{chunk.inserted_lines} -{chunk.deleted_lines}"
        )
    if details:
        for label, value in (
            ("State", chunk.current_state),
            ("Next", chunk.next_step),
            ("Disposition", chunk.disposition),
            ("Stopped", chunk.stop_reason),
        ):
            if value:
                lines.append(prefix + label + ": " + " ".join(value.split()))
        lines.extend(prefix + "Log: " + path for path in chunk.log_paths)
    # Missing logs do not invalidate retained metrics/context.
    from pathlib import Path

    if any(not Path(path).exists() for path in chunk.log_paths):
        lines.append(prefix + warning("detailed log unavailable", color))
    return lines
