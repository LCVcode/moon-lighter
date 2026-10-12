"""Durable per-invocation reports, independent of legacy history records."""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import IO


class ReportError(OSError):
    """History could not be persisted or read safely."""


@dataclass
class UsageObservation:
    checked_at: str
    five_hour_remaining: float | None = None
    weekly_remaining: float | None = None
    five_hour_reset: str | None = None
    weekly_reset: str | None = None
    source: str | None = None
    error: str | None = None


@dataclass
class TokenUsage:
    total: int | None = None
    input: int | None = None
    output: int | None = None
    cache_read: int | None = None
    cache_write: int | None = None
    partial: bool = False
    source: str = "pi-session"


@dataclass
class ChunkReport:
    chunk_id: str
    project: str
    started_at: str
    status: str = "running"
    ended_at: str | None = None
    elapsed_seconds: float | None = None
    summary: str | None = None
    disposition: str | None = None
    stop_reason: str | None = None
    current_state: str | None = None
    next_step: str | None = None
    error: str | None = None
    tokens: TokenUsage | None = None
    budget_before: UsageObservation | None = None
    budget_after: UsageObservation | None = None
    commits: int | None = None
    inserted_lines: int | None = None
    deleted_lines: int | None = None
    provider: str | None = None
    model: str | None = None
    runner: str = "pi"
    log_paths: list[str] = field(default_factory=list)
    container: str | None = None


@dataclass
class SessionReport:
    run_id: str
    started_at: str
    entrypoint: str
    trigger: str
    requested_project: str | None
    status: str = "running"
    ended_at: str | None = None
    elapsed_seconds: float | None = None
    stop_reason: str | None = None
    error: str | None = None
    budget_before: UsageObservation | None = None
    budget_after: UsageObservation | None = None
    chunks: list[ChunkReport] = field(default_factory=list)
    schema_version: int = 1


def report_path(state_dir: Path, run_id: str) -> Path:
    key = hashlib.sha256(run_id.encode()).hexdigest()
    return state_dir / "reports" / f"{key}.json"


def _durable_directory(path: Path) -> None:
    missing = []
    directory = path
    while not directory.exists():
        missing.append(directory)
        directory = directory.parent
    for directory in reversed(missing):
        directory.mkdir(exist_ok=True)
        descriptor = os.open(directory.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def save_report(state_dir: Path, report: SessionReport) -> None:
    """Atomic replace with file and directory fsync; no partially written JSON."""
    path = report_path(state_dir, report.run_id)
    _durable_directory(path.parent)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as file:
            temporary = file.name
            json.dump(asdict(report), file, allow_nan=False)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        temporary = None
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except (OSError, ValueError) as exc:
        raise ReportError(f"Cannot persist work report {path}: {exc}") from exc
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def load_report(path: Path) -> SessionReport:
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("unsupported report schema")
        chunks = data.pop("chunks")
        if not isinstance(chunks, list):
            raise ValueError("chunks must be a list")
        report = SessionReport(**data)
        report.budget_before = _observation(report.budget_before)
        report.budget_after = _observation(report.budget_after)
        for value in chunks:
            chunk = ChunkReport(**value)
            chunk.budget_before = _observation(chunk.budget_before)
            chunk.budget_after = _observation(chunk.budget_after)
            if isinstance(chunk.tokens, dict):
                chunk.tokens = TokenUsage(**chunk.tokens)
            report.chunks.append(chunk)
        _validate_report(report)
        return report
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ReportError(f"Cannot read work report {path}: {exc}") from exc


def _validate_report(report: SessionReport) -> None:
    for item in (report, *report.chunks):
        for name in ("started_at", "status"):
            if not isinstance(getattr(item, name), str):
                raise ValueError(f"invalid {name}")
        for name in ("error", "stop_reason"):
            value = getattr(item, name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"invalid {name}")
        datetime.fromisoformat(item.started_at)
        if item.ended_at is not None:
            datetime.fromisoformat(item.ended_at)
        if item.elapsed_seconds is not None and (
            isinstance(item.elapsed_seconds, bool)
            or not isinstance(item.elapsed_seconds, (int, float))
            or not math.isfinite(item.elapsed_seconds)
            or item.elapsed_seconds < 0
        ):
            raise ValueError("invalid elapsed time")
        if item.status not in {"running", "success", "failed", "skipped", "interrupted"}:
            raise ValueError("invalid lifecycle state")
        for observation in (item.budget_before, item.budget_after):
            if observation is None:
                continue
            if not isinstance(observation, UsageObservation):
                raise ValueError("invalid observation")
            datetime.fromisoformat(observation.checked_at)
            for value in (observation.five_hour_remaining, observation.weekly_remaining):
                if value is not None and (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or not 0 <= value <= 100
                ):
                    raise ValueError("invalid quota percentage")
            for value in (observation.five_hour_reset, observation.weekly_reset):
                if value is not None:
                    datetime.fromisoformat(value)
    if not all(
        isinstance(value, str) for value in (report.run_id, report.entrypoint, report.trigger)
    ):
        raise ValueError("invalid report identity")
    for chunk in report.chunks:
        for value in (
            chunk.summary,
            chunk.disposition,
            chunk.current_state,
            chunk.next_step,
            chunk.provider,
            chunk.model,
            chunk.container,
        ):
            if value is not None and not isinstance(value, str):
                raise ValueError("invalid chunk context")
        for value in (chunk.commits, chunk.inserted_lines, chunk.deleted_lines):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError("invalid coding metric")
        if not isinstance(chunk.project, str) or not isinstance(chunk.chunk_id, str):
            raise ValueError("invalid chunk identity")
        if not isinstance(chunk.log_paths, list) or not all(
            isinstance(value, str) for value in chunk.log_paths
        ):
            raise ValueError("invalid log references")
        if chunk.tokens is not None:
            if not isinstance(chunk.tokens, TokenUsage):
                raise ValueError("invalid tokens")
            for value in (
                chunk.tokens.total,
                chunk.tokens.input,
                chunk.tokens.output,
                chunk.tokens.cache_read,
                chunk.tokens.cache_write,
            ):
                if value is not None and (
                    isinstance(value, bool) or not isinstance(value, int) or value < 0
                ):
                    raise ValueError("invalid token count")


def _observation(value: UsageObservation | None) -> UsageObservation | None:
    if isinstance(value, dict):
        return UsageObservation(**value)
    return value


class ReportLease:
    """Exclusive per-session lease; a held lock is proof of a live owner."""

    def __init__(self, state_dir: Path, report: SessionReport) -> None:
        self.state_dir = state_dir
        self.report = report
        self.file: IO[str] | None = None

    def __enter__(self) -> ReportLease:
        path = report_path(self.state_dir, self.report.run_id)
        _durable_directory(path.parent)
        self.file = path.with_suffix(".lock").open("a")
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if path.exists():
                raise ReportError(f"Work report already exists: {path}")
            save_report(self.state_dir, self.report)
        except BaseException:
            self.file.close()
            raise
        return self

    def __exit__(self, *_args: object) -> None:
        if self.file is not None:
            self.file.close()
        path = report_path(self.state_dir, self.report.run_id)
        if not path.exists():
            path.with_suffix(".lock").unlink(missing_ok=True)


def read_reports(
    state_dir: Path,
    *,
    reconcile: bool = True,
    issues: list[str] | None = None,
) -> tuple[SessionReport, ...]:
    reports = []
    for path in sorted((state_dir / "reports").glob("*.json")):
        try:
            report = load_report(path)
        except ReportError as exc:
            if issues is not None:
                issues.append(str(exc))
            continue
        if reconcile and report.status == "running":
            _reconcile(path, report, state_dir)
        reports.append(report)
    return tuple(reports)


def _reconcile(path: Path, report: SessionReport, state_dir: Path) -> None:
    """Never use age alone; orphaned Docker workers may outlive the host process."""
    try:
        with path.with_suffix(".lock").open("a") as lease:
            try:
                fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            report_now = load_report(path)
            if report_now.status != "running":
                return
            for chunk in report_now.chunks:
                if (
                    chunk.status == "running"
                    and chunk.container
                    and not container_gone(chunk.container)
                ):
                    return
            report_now.status = "interrupted"
            report_now.stop_reason = "owner exited before recording an outcome"
            for chunk in report_now.chunks:
                if chunk.status == "running":
                    chunk.status = "interrupted"
                    chunk.stop_reason = report_now.stop_reason
            save_report(state_dir, report_now)
            report.status = report_now.status
            report.stop_reason = report_now.stop_reason
            report.chunks = report_now.chunks
    except OSError:
        # Read-only callers still see an unfinished report when reconciliation fails.
        return


def container_gone(name: str) -> bool:
    """Return true only when Docker confirms a named container is absent or stopped."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", name],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        detail = result.stderr.casefold()
        absent = (
            re.search(
                r"no such (?:object|container):?\s+" + re.escape(name.casefold()) + r"(?=\s|$)",
                detail,
            )
            is not None
        )
        return (result.returncode == 0 and result.stdout.strip() == "false") or (
            result.returncode != 0 and absent
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
