"""Current-state context from history, without changing project disposition."""

from __future__ import annotations

from pathlib import Path

from moonlighter.colors import outcome
from moonlighter.history_queries import load_history, project_work, timestamp
from moonlighter.projects import ProjectState


def project_history_lines(
    state_dir: Path,
    project: str,
    state: ProjectState,
    *,
    color: bool = False,
) -> list[str]:
    history = load_history(state_dir)
    work = project_work(history.records, project)
    lines: list[str] = []
    if state.disposition_summary:
        lines.append("Summary: " + compact(state.disposition_summary))
    if work:
        latest = work[0]
        lines.append(
            f"Latest outcome: {outcome(latest.status, enabled=color)} ({latest.started_at})"
        )
        if latest.reason:
            lines.append("  Reason: " + compact(latest.reason))
        success = next((item for item in work if item.status == "success"), None)
        if success:
            lines.append(f"Last successful work: {success.started_at}")
        context = next(
            (
                item
                for item in work
                if item.chunk
                and (item.chunk.summary or item.chunk.current_state or item.chunk.next_step)
            ),
            None,
        )
        if context and context.chunk:
            chunk = context.chunk
            historical = context is not latest or (
                chunk.disposition is not None and chunk.disposition != state.disposition
            )
            if state.last_run_at:
                try:
                    historical |= timestamp(state.last_run_at) > timestamp(
                        chunk.ended_at or chunk.started_at
                    )
                except ValueError:
                    historical = True
            label = "Historical handoff" if historical else "Latest handoff"
            lines.append(f"{label}: {context.started_at}")
            if chunk.summary and chunk.summary != state.disposition_summary:
                lines.append("  Work summary: " + compact(chunk.summary))
            if chunk.current_state:
                lines.append("  Recorded current state: " + compact(chunk.current_state))
            if chunk.next_step:
                lines.append("  Recorded next step: " + compact(chunk.next_step))
            if historical:
                lines.append(
                    "  Historical context; current disposition above remains authoritative."
                )
        elif not state.disposition_summary:
            lines.append("Work context: no data (legacy or missing handoff)")
    else:
        lines.append("Recorded work: no data")
    if history.warnings:
        lines.append(
            f"History incomplete: {len(history.warnings)} unreadable record(s); see moon report"
        )
    return lines


def global_history_lines(state_dir: Path, *, color: bool = False) -> list[str]:
    history = load_history(state_dir)
    lines = ["Recent work (historical, not budget permission):"]
    success = next((record for record in history.records if record.succeeded_chunks), None)
    if success:
        lines.append(f"  Last successful work: {success.started_at} — {','.join(success.projects)}")
    else:
        lines.append("  Last successful work: no data")
    problems = [
        record
        for record in history.records
        if record.status in {"failed", "interrupted", "running", "skipped"}
    ][:3]
    for record in problems:
        subject = ",".join(record.projects) or record.requested_project or "session"
        reason = record.error or record.skip_reason
        if not reason and record.report:
            reason = record.report.stop_reason
            if not reason:
                reason = next((chunk.error for chunk in record.report.chunks if chunk.error), None)
        label = outcome(record.status, enabled=color)
        if record.status == "running":
            label += "/unfinished"
        lines.append(
            f"  {record.started_at} {subject}: {label}"
            + (" — " + compact(reason) if reason else "")
        )
    if history.warnings:
        lines.append(f"  History incomplete: {len(history.warnings)} unreadable record(s)")
    return lines


def compact(text: str) -> str:
    return " ".join(text.split())[:240]


def meaningful_log_summary(text: str) -> str | None:
    """Headings are structure, never work summaries."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", "```")) and stripped not in {"---", "***"}:
            return compact(stripped)
    return None
