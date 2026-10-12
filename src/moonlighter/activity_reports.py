"""Pure activity aggregation: distinguish session totals from project contributions."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from moonlighter.run_history import RunRecord
from moonlighter.work_reports import ChunkReport


@dataclass(frozen=True)
class Total:
    value: int | float | None
    partial: bool = False


@dataclass(frozen=True)
class Activity:
    sessions: int
    chunks: int
    chunks_partial: bool
    outcomes: dict[str, int]
    chunk_outcomes: dict[str, int]
    triggers: dict[str, int]
    session_time: Total
    chunk_time: Total
    tokens: Total
    commits: Total
    inserted: Total
    deleted: Total


def total(values: list[int | float | None], *, missing: bool = False) -> Total:
    known = [value for value in values if value is not None]
    return Total(sum(known) if known else None, missing or any(value is None for value in values))


def matching_chunks(record: RunRecord, project: str | None = None) -> list[ChunkReport]:
    if record.report is None:
        return []
    return [chunk for chunk in record.report.chunks if project is None or chunk.project == project]


def aggregate(records: tuple[RunRecord, ...], project: str | None = None) -> Activity:
    chunks = [chunk for record in records for chunk in matching_chunks(record, project)]
    count = len(chunks)
    unknown_metrics = False
    unknown_count = False
    chunk_outcomes = Counter(chunk.status for chunk in chunks)
    for record in records:
        if record.report is not None or not record.ran_chunks:
            continue
        unknown_metrics = True
        if project is None or record.projects == (project,):
            count += record.ran_chunks
            chunk_outcomes["success"] += record.succeeded_chunks
            chunk_outcomes["failed"] += record.failed_chunks
        else:
            unknown_count = True  # Legacy multi-project records cannot attribute child counts.
    tokens = total(
        [chunk.tokens.total if chunk.tokens else None for chunk in chunks],
        missing=unknown_metrics or any(c.tokens and c.tokens.partial for c in chunks),
    )
    return Activity(
        sessions=len(records),
        chunks=count,
        chunks_partial=unknown_count,
        outcomes=dict(Counter(record.status for record in records)),
        chunk_outcomes=dict(chunk_outcomes),
        triggers=dict(Counter(r.trigger for r in records)),
        session_time=total(
            [r.report.elapsed_seconds if r.report else r.elapsed_seconds for r in records]
        ),
        chunk_time=total([chunk.elapsed_seconds for chunk in chunks], missing=unknown_metrics),
        tokens=tokens,
        commits=total([chunk.commits for chunk in chunks], missing=unknown_metrics),
        inserted=total([chunk.inserted_lines for chunk in chunks], missing=unknown_metrics),
        deleted=total([chunk.deleted_lines for chunk in chunks], missing=unknown_metrics),
    )


def date_range(
    *,
    today: bool = False,
    week: bool = False,
    since: str | None = None,
    until: str | None = None,
    now: datetime | None = None,
) -> tuple[datetime | None, datetime | None, str]:
    """Local calendar boundaries, inclusive start/exclusive end, by session start."""
    current = now or datetime.now().astimezone()
    if (today or week) and until is not None:
        raise ValueError("--until is for --since or all-history ranges, not --today/--week")
    if sum((today, week, since is not None)) > 1:
        raise ValueError("choose only one of --today, --week, or --since")

    def midnight(day) -> datetime:
        value = datetime.combine(day, time.min)
        # Explicit now supplies a test/user timezone; production uses date-aware local conversion.
        return value.replace(tzinfo=current.tzinfo) if now else value.astimezone()

    if today or week:
        first_day = current.date() - timedelta(days=current.weekday() if week else 0)
        start = midnight(first_day)
        end = midnight(first_day + timedelta(days=7 if week else 1))
        return start, end, "This week" if week else "Today"
    start = parse_boundary(since) if since else None
    end = parse_boundary(until) if until else None
    if start is not None and end is not None and end <= start:
        raise ValueError("--until must be later than --since")
    label = "All history"
    if start:
        label = "Since " + start.isoformat()
    if end:
        label += " (before " + end.isoformat() + ")"
    return start, end, label


def parse_boundary(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value).astimezone()
    except ValueError as exc:
        raise ValueError(
            f"invalid date/time {value!r}; use YYYY-MM-DD or an ISO timestamp"
        ) from exc
