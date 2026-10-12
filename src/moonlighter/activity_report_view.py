"""Human-readable report summaries and selected session/chunk details."""

from __future__ import annotations

from dataclasses import replace

from moonlighter.activity_reports import Total, aggregate, matching_chunks
from moonlighter.history_queries import History, select_records
from moonlighter.report_usage import quota_delta
from moonlighter.report_view import report_lines, warning
from moonlighter.run_history import RunRecord, format_duration_seconds


def measure(value: Total, *, duration: bool = False, color: bool = False) -> str:
    if value.value is None:
        return warning("no data", color)
    text = format_duration_seconds(float(value.value)) if duration else f"{int(value.value):,}"
    return text + (" " + warning("(partial)", color) if value.partial else "")


def render_activity_report(
    history: History,
    *,
    project: str | None = None,
    label: str = "All history",
    details: bool = False,
    limit: int = 20,
    color: bool = False,
) -> str:
    records = history.records
    title = f"{project} — {label}" if project else label
    lines = [title, ""]
    if history.warnings:
        lines.append(warning("History incomplete: totals cover readable records only.", color))
        lines.extend("  " + message for message in history.warnings[:3])
        if len(history.warnings) > 3:
            lines.append(f"  ... {len(history.warnings) - 3} additional warning(s)")
    if not records:
        lines.append("No matching sessions.")
        return "\n".join(lines) + "\n"
    activity = aggregate(records, project)
    names = sorted({name for record in records for name in record.projects})
    chunk_count = str(activity.chunks) + (" (partial)" if activity.chunks_partial else "")
    lines.append(
        f"Sessions: {activity.sessions}   Chunks: {chunk_count}"
        + (f"   Projects: {len(names)}" if project is None else " (matching project)")
    )
    outcomes = ", ".join(f"{count} {status}" for status, count in sorted(activity.outcomes.items()))
    lines.append("Session outcomes: " + outcomes + (" (whole sessions)" if project else ""))
    lines.append(
        "Chunk outcomes: "
        + (
            ", ".join(
                f"{count} {status}" for status, count in sorted(activity.chunk_outcomes.items())
            )
            or "no data"
        )
    )
    lines.append(
        "Triggers: "
        + ", ".join(f"{key}={value}" for key, value in sorted(activity.triggers.items()))
    )
    if project is None:
        lines.append("Session time: " + measure(activity.session_time, duration=True, color=color))
    lines.append("Chunk time: " + measure(activity.chunk_time, duration=True, color=color))
    lines.append("Tokens: " + measure(activity.tokens, color=color))
    lines.append(
        "Commits: "
        + measure(activity.commits, color=color)
        + "   Lines: +"
        + measure(activity.inserted, color=color)
        + " / -"
        + measure(activity.deleted, color=color)
    )
    lines.append("Quota: shared-account observations, not project token costs; never summed.")
    for window in ("5h", "weekly"):
        comparable = sum(
            quota_delta(record.report.budget_before, record.report.budget_after, window).endswith(
                "%"
            )
            for record in records
            if record.report
        )
        lines.append(
            f"  {window}: {comparable}/{len(records)} comparable session samples"
            " (details show reset/missing data)"
        )
    if project is None and names:
        width = max(16, max(map(len, names)))
        lines.extend(["", f"{'Project':<{width}}  Chunks  Chunk time  Tokens"])
        for name in names:
            selected = select_records(records, project=name, include_routine_skips=True)
            contribution = aggregate(selected, name)
            count = str(contribution.chunks) + (" partial" if contribution.chunks_partial else "")
            lines.append(
                f"{name:<{width}}  {count:>6}  "
                + measure(contribution.chunk_time, duration=True, color=color)
                + "  "
                + measure(contribution.tokens, color=color)
            )
    if details or project is not None:
        lines.extend(["", f"Latest sessions: showing {min(limit, len(records))}/{len(records)}"])
        for record in records[:limit]:
            lines.extend(session_detail(record, project=project, color=color))
    else:
        lines.append(
            "\nUse --details or --session RUN_ID for work summaries and chunk observations."
        )
    lines.append("\nRanges select invocation starts; unfinished durations remain unknown.")
    return "\n".join(lines) + "\n"


def session_detail(record: RunRecord, *, project: str | None, color: bool) -> list[str]:
    subject = project or ",".join(record.projects) or record.requested_project or "session"
    time = Total(record.report.elapsed_seconds if record.report else record.elapsed_seconds)
    label = "project contribution" if project and record.entrypoint == "work" else record.entrypoint
    lines = [
        f"\nSession: {record.run_id}",
        f"{record.started_at}  {subject}  {label}  {record.status}",
    ]
    if project is None:
        lines.append("Session time: " + measure(time, duration=True, color=color))
    if record.report:
        report = record.report
        if project:
            report = replace(report, chunks=matching_chunks(record, project))
            lines.append("Only matching chunks below; quota observations remain shared-account.")
        lines.extend(
            report_lines(report, color, details=True, include_session_duration=project is None)
        )
    else:
        lines.append("  Captured chunk/usage detail: " + warning("no data (legacy record)", color))
    return lines
