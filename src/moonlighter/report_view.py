"""Compact hierarchy and missing-data presentation for captured work reports."""

from __future__ import annotations

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
    return f"tokens={count}  quota Δ5h={deltas[0]} Δweek={deltas[1]}"


def report_lines(report: SessionReport, color: bool, *, details: bool = False) -> list[str]:
    if report.entrypoint == "run" and len(report.chunks) == 1:
        chunk = report.chunks[0]
        return [
            "  " + metrics(chunk.tokens, report.budget_before, report.budget_after, color),
            *_context(chunk, "  ", color, details=details),
        ]
    lines = [
        "  " + metrics(token_total(report.chunks), report.budget_before, report.budget_after, color)
    ]
    for chunk in report.chunks:
        elapsed = "no data" if chunk.elapsed_seconds is None else f"{chunk.elapsed_seconds:.1f}s"
        lines.append(f"    {chunk.started_at}  {chunk.project}  {chunk.status}  {elapsed}")
        lines.append(
            "      " + metrics(chunk.tokens, chunk.budget_before, chunk.budget_after, color)
        )
        lines.extend(_context(chunk, "      ", color, details=details))
    return lines


def _context(
    chunk: ChunkReport,
    prefix: str,
    color: bool,
    *,
    details: bool = False,
) -> list[str]:
    lines = []
    if chunk.summary:
        lines.append(prefix + " ".join(chunk.summary.split()))
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
