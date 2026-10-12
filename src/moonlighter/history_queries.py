"""Shared history selection; keep state views and activity reports consistent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from moonlighter.run_history import RunRecord, read_run_records
from moonlighter.work_reports import ChunkReport


@dataclass(frozen=True)
class History:
    records: tuple[RunRecord, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectWork:
    record: RunRecord
    chunk: ChunkReport | None = None

    @property
    def started_at(self) -> str:
        return self.chunk.started_at if self.chunk else self.record.started_at

    @property
    def status(self) -> str:
        return self.chunk.status if self.chunk else self.record.status

    @property
    def reason(self) -> str | None:
        if self.chunk:
            return self.chunk.error or self.chunk.stop_reason
        return self.record.error or self.record.skip_reason


def timestamp(value: str) -> datetime:
    """Legacy naive times are local; aware timestamps retain their absolute instant."""
    return datetime.fromisoformat(value).astimezone()


def load_history(state_dir: Path, *, reconcile: bool = False) -> History:
    warnings: list[str] = []
    records = read_run_records(state_dir, strict=False, reconcile=reconcile, issues=warnings)
    return History(records, tuple(warnings))


def project_work(records: tuple[RunRecord, ...], project: str) -> tuple[ProjectWork, ...]:
    work: list[ProjectWork] = []
    for record in records:
        if record.report:
            chunks = [chunk for chunk in record.report.chunks if chunk.project == project]
            work.extend(ProjectWork(record, chunk) for chunk in chunks)
            if not chunks and not record.report.chunks and record.requested_project == project:
                work.append(ProjectWork(record))
        elif project in record.projects or record.requested_project == project:
            work.append(ProjectWork(record))
    return tuple(sorted(work, key=lambda item: timestamp(item.started_at), reverse=True))


def select_records(
    records: tuple[RunRecord, ...],
    *,
    project: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    session: str | None = None,
    include_routine_skips: bool = False,
) -> tuple[RunRecord, ...]:
    """Ranges select sessions by invocation start, not individual child timestamps."""
    from moonlighter.run_history import is_no_work_skip

    selected = []
    for record in records:
        if session is not None and record.run_id != session:
            continue
        if not include_routine_skips and is_no_work_skip(record):
            continue
        if project is not None and not project_work((record,), project):
            continue
        when = timestamp(record.started_at)
        if start is not None and when < start:
            continue
        if end is not None and when >= end:
            continue
        selected.append(record)
    return tuple(selected)
