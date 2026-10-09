"""Append-only Moonlighter run history."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from moonlighter.schedule import format_duration

RUN_HISTORY_SCHEMA_VERSION = 1
RUN_HISTORY_FILE_NAME = "runs.jsonl"

RunStatus = Literal["skipped", "success", "failed"]


class RunHistoryError(ValueError):
    """Raised when run history cannot be read or written."""


@dataclass(frozen=True)
class RunRecord:
    """One Moonlighter run invocation record."""

    run_id: str
    started_at: str
    ended_at: str
    elapsed_seconds: float
    entrypoint: str
    trigger: str
    requested_project: str | None
    projects: tuple[str, ...]
    status: RunStatus
    skip_reason: str | None
    error: str | None
    disposition: str | None
    ran_chunks: int
    succeeded_chunks: int
    failed_chunks: int
    schema_version: int = RUN_HISTORY_SCHEMA_VERSION


def run_history_path(state_dir: Path) -> Path:
    """Return the run history JSONL path for a state directory."""
    return state_dir / RUN_HISTORY_FILE_NAME


def new_run_id(started_at: datetime) -> str:
    """Return a stable run id based on the run start time."""
    return started_at.isoformat()


def append_run_record(state_dir: Path, record: RunRecord) -> None:
    """Append one run record to the JSONL history file."""
    state_dir.mkdir(parents=True, exist_ok=True)
    path = run_history_path(state_dir)
    with path.open("a", encoding="utf-8") as file:
        file.write(f"{json.dumps(run_record_to_json(record), sort_keys=True)}\n")


def read_run_records(state_dir: Path) -> tuple[RunRecord, ...]:
    """Read run records from newest to oldest."""
    path = run_history_path(state_dir)
    if not path.exists():
        return ()

    records: list[RunRecord] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RunHistoryError(f"failed to read run history {path}: {exc}") from exc

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RunHistoryError(f"invalid run history JSON on line {line_number}: {exc}") from exc
        if not isinstance(data, dict):
            raise RunHistoryError(f"run history line {line_number} must be a JSON object")
        records.append(parse_run_record(data, line_number=line_number))
    return tuple(reversed(records))


def filter_run_records(
    records: tuple[RunRecord, ...],
    *,
    limit: int,
    project: str | None = None,
    status: str | None = None,
    include_no_work_skips: bool = False,
) -> tuple[RunRecord, ...]:
    """Filter records for CLI display."""
    filtered: list[RunRecord] = []
    for record in records:
        if not include_no_work_skips and is_no_work_skip(record):
            continue
        if project is not None and project not in record.projects:
            continue
        if status is not None and record.status != status:
            continue
        filtered.append(record)
        if len(filtered) >= limit:
            break
    return tuple(filtered)


def is_no_work_skip(record: RunRecord) -> bool:
    """Return whether a record skipped before doing project work.

    Older service units did not set MOON_TRIGGER, so some timer no-work skips were recorded
    as manual. Treat plain `moon work` gate skips with no chunks as hidden by default.
    """
    return (
        record.entrypoint == "work"
        and record.status == "skipped"
        and not record.projects
        and record.ran_chunks == 0
    )


def render_run_log(records: tuple[RunRecord, ...]) -> str:
    """Render run records for humans."""
    lines = ["Recent Moon runs", ""]
    if not records:
        lines.append("none")
        return "\n".join(lines) + "\n"

    for record in records:
        when = _format_timestamp(record.started_at)
        elapsed = format_duration_seconds(record.elapsed_seconds)
        source = f"{record.entrypoint}/{record.trigger}"
        subject = ",".join(record.projects) if record.projects else record.skip_reason or "-"
        lines.append(f"{when}  {source:<13} {record.status:<7} {elapsed:<5} {subject}")
    return "\n".join(lines) + "\n"


def format_duration_seconds(seconds: float) -> str:
    """Format elapsed seconds using Moonlighter's terse duration style."""
    return format_duration(datetime.fromtimestamp(max(0, seconds)) - datetime.fromtimestamp(0))


def run_record_to_json(record: RunRecord) -> dict[str, object]:
    """Convert a run record to JSON-compatible data."""
    return {
        "schema_version": record.schema_version,
        "run_id": record.run_id,
        "started_at": record.started_at,
        "ended_at": record.ended_at,
        "elapsed_seconds": round(record.elapsed_seconds, 3),
        "entrypoint": record.entrypoint,
        "trigger": record.trigger,
        "requested_project": record.requested_project,
        "projects": list(record.projects),
        "status": record.status,
        "skip_reason": record.skip_reason,
        "error": record.error,
        "disposition": record.disposition,
        "ran_chunks": record.ran_chunks,
        "succeeded_chunks": record.succeeded_chunks,
        "failed_chunks": record.failed_chunks,
    }


def parse_run_record(data: dict[str, object], *, line_number: int | None = None) -> RunRecord:
    """Parse and validate one run history JSON object."""
    label = f"run history line {line_number}" if line_number is not None else "run history record"
    schema_version = _required_int(data, "schema_version", label)
    if schema_version != RUN_HISTORY_SCHEMA_VERSION:
        raise RunHistoryError(
            f"{label} schema_version must be {RUN_HISTORY_SCHEMA_VERSION}, got {schema_version}"
        )
    status = _required_string(data, "status", label)
    if status not in {"skipped", "success", "failed"}:
        raise RunHistoryError(f"{label} status must be one of: skipped, success, failed")

    return RunRecord(
        schema_version=schema_version,
        run_id=_required_string(data, "run_id", label),
        started_at=_required_string(data, "started_at", label),
        ended_at=_required_string(data, "ended_at", label),
        elapsed_seconds=_required_number(data, "elapsed_seconds", label),
        entrypoint=_required_string(data, "entrypoint", label),
        trigger=_required_string(data, "trigger", label),
        requested_project=_optional_string(data, "requested_project", label),
        projects=_required_string_tuple(data, "projects", label),
        status=status,
        skip_reason=_optional_string(data, "skip_reason", label),
        error=_optional_string(data, "error", label),
        disposition=_optional_string(data, "disposition", label),
        ran_chunks=_required_int(data, "ran_chunks", label),
        succeeded_chunks=_required_int(data, "succeeded_chunks", label),
        failed_chunks=_required_int(data, "failed_chunks", label),
    )


def _format_timestamp(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def _required(data: dict[str, object], key: str, label: str) -> object:
    if key not in data:
        raise RunHistoryError(f"{label} missing required key: {key}")
    return data[key]


def _required_string(data: dict[str, object], key: str, label: str) -> str:
    value = _required(data, key, label)
    if not isinstance(value, str):
        raise RunHistoryError(f"{label} {key} must be a string")
    return value


def _optional_string(data: dict[str, object], key: str, label: str) -> str | None:
    value = _required(data, key, label)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RunHistoryError(f"{label} {key} must be a string or null")
    return value


def _required_int(data: dict[str, object], key: str, label: str) -> int:
    value = _required(data, key, label)
    if not isinstance(value, int) or isinstance(value, bool):
        raise RunHistoryError(f"{label} {key} must be an integer")
    return value


def _required_number(data: dict[str, object], key: str, label: str) -> float:
    value = _required(data, key, label)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise RunHistoryError(f"{label} {key} must be a number")
    return float(value)


def _required_string_tuple(data: dict[str, object], key: str, label: str) -> tuple[str, ...]:
    value = _required(data, key, label)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RunHistoryError(f"{label} {key} must be an array of strings")
    return tuple(value)
