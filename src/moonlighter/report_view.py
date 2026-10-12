"""Compact hierarchy and missing-data presentation for captured work reports."""

from __future__ import annotations

import shutil
import textwrap

from moonlighter.colors import outcome
from moonlighter.history_duration import format_elapsed
from moonlighter.history_tree import TreeNode, render_tree
from moonlighter.report_usage import quota_delta
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
    show_missing: bool = True,
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
        elapsed = warning("no data", color) if duration is None else format_elapsed(duration)
        parts.append(f"Duration: {elapsed}")
    quota = [
        f"{label} {value}"
        for label, value in zip(("5h", "week"), deltas, strict=True)
        if show_missing or "no data" not in value
    ]
    if quota:
        parts.append("Quota: " + ", ".join(quota))
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
                        show_missing=details,
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
                        show_missing=details,
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
                            show_missing=details,
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
        nodes.append(TreeNode(detail_lines("error", report.error, width=columns - 5)))
    if report.stop_reason:
        nodes.append(TreeNode(detail_lines("stopped", report.stop_reason, width=columns - 5)))
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


def detail_lines(
    label: str,
    value: str,
    prefix: str = "",
    *,
    width: int | None = None,
) -> list[str]:
    columns = width if width is not None else shutil.get_terminal_size((100, 24)).columns
    heading = label + ": "
    return textwrap.wrap(
        " ".join(value.split()),
        width=max(columns, len(prefix) + len(heading) + 2),
        initial_indent=prefix + heading,
        subsequent_indent=prefix + " " * len(heading),
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
        lines.extend(detail_lines("error", chunk.error, prefix, width=width))
    coding = []
    if chunk.commits is not None and (details or chunk.commits != 0):
        coding.append(f"commits={chunk.commits}")
    changes = (chunk.inserted_lines, chunk.deleted_lines)
    if any(value is not None for value in changes) and (
        details or any(value not in (None, 0) for value in changes)
    ):
        added, removed = [
            str(value) if value is not None else warning("no data", color) for value in changes
        ]
        coding.append(f"diff=+{added} -{removed}")
    if coding:
        lines.append(prefix + " ".join(coding))
    if details:
        for label, value in (
            ("State", chunk.current_state),
            ("Next", chunk.next_step),
            ("Disposition", chunk.disposition),
            ("Stopped", chunk.stop_reason),
        ):
            if value:
                lines.extend(detail_lines(label, value, prefix, width=width))
        lines.extend(prefix + "Log: " + path for path in chunk.log_paths)
    # Missing logs do not invalidate retained metrics/context.
    from pathlib import Path

    if any(not Path(path).exists() for path in chunk.log_paths):
        lines.append(prefix + warning("detailed log unavailable", color))
    return lines
