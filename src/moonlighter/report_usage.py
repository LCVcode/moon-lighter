"""Observed quota and chunk-local agent usage, never inferred token costs."""

from __future__ import annotations

import fcntl
import json
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from moonlighter.budget import BudgetGateResult
from moonlighter.work_reports import TokenUsage, UsageObservation


def observe_budget(result: BudgetGateResult | None) -> UsageObservation:
    snapshot = result.snapshot if result else None
    if snapshot is None:
        return UsageObservation(
            checked_at=datetime.now().astimezone().isoformat(),
            error=result.reason if result else "usage not observed",
        )
    return UsageObservation(
        checked_at=snapshot.checked_at.isoformat(),
        five_hour_remaining=snapshot.five_hour.remaining_percent,
        weekly_remaining=snapshot.weekly.remaining_percent,
        five_hour_reset=_date(snapshot.five_hour.reset_at),
        weekly_reset=_date(snapshot.weekly.reset_at),
        source=str(snapshot.source),
    )


def _date(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def quota_delta(
    before: UsageObservation | None, after: UsageObservation | None, window: str
) -> str:
    if before is None or after is None:
        return "no data"
    if window == "5h":
        start, end = before.five_hour_remaining, after.five_hour_remaining
        reset_start, reset_end = before.five_hour_reset, after.five_hour_reset
    else:
        start, end = before.weekly_remaining, after.weekly_remaining
        reset_start, reset_end = before.weekly_reset, after.weekly_reset
    if start is None or end is None:
        return "no data"
    if reset_start is None or reset_end is None:
        return "unknown reset"
    if reset_start != reset_end or end > start:
        return "reset/changed"
    if datetime.fromisoformat(after.checked_at) >= datetime.fromisoformat(reset_start):
        return "reset/changed"
    return f"{start - end:.1f}%"


@contextmanager
def session_usage_lease(storage: Path) -> Generator[None, None, None]:
    """Do not allow overlapping writers to contaminate one project's token baseline."""
    storage.mkdir(parents=True, exist_ok=True)
    with (storage / ".usage.lock").open("a") as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise OSError("another chunk is already using this project's agent session") from exc
        yield


def session_offsets(storage: Path) -> dict[str, int] | None:
    """Baseline all existing files: reused sessions cannot contribute old messages."""
    try:
        return {str(path): path.stat().st_size for path in storage.rglob("*.jsonl")}
    except OSError:
        return None  # No trustworthy baseline means unknown usage, not lifetime usage.


def read_chunk_tokens(
    storage: Path,
    offsets: dict[str, int] | None,
    started_at: datetime | None = None,
) -> TokenUsage | None:
    if offsets is None:
        return None
    totals = {"totalTokens": 0, "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}
    seen = 0
    missing = False
    unavailable: set[str] = set()
    for path in storage.rglob("*.jsonl"):
        offset = offsets.get(str(path), 0)
        try:
            if path.stat().st_size < offset:
                missing = True  # Rotated/truncated session: cannot distinguish old data safely.
                continue
            with path.open("rb") as file:
                file.seek(offset)
                lines = file.readlines()
            for line in lines:
                try:
                    entry = json.loads(line)
                    message = entry.get("message", {})
                    if entry.get("type") != "message" or message.get("role") != "assistant":
                        continue
                    timestamp = message.get("timestamp")
                    if (
                        started_at is not None
                        and isinstance(timestamp, (int, float))
                        and timestamp < started_at.timestamp() * 1000
                    ):
                        continue  # A forked session may copy old messages into a new file.
                    usage = message.get("usage")
                    if not isinstance(usage, dict) or not _count(usage.get("totalTokens")):
                        missing = True
                        continue
                    seen += 1
                    for key in totals:
                        value = usage.get(key)
                        if _count(value):
                            totals[key] += value
                        else:
                            unavailable.add(key)
                except (ValueError, AttributeError, TypeError):
                    missing = True
        except OSError:
            missing = True
    if not seen:
        return None
    return TokenUsage(
        total=totals["totalTokens"],
        input=None if "input" in unavailable else totals["input"],
        output=None if "output" in unavailable else totals["output"],
        cache_read=None if "cacheRead" in unavailable else totals["cacheRead"],
        cache_write=None if "cacheWrite" in unavailable else totals["cacheWrite"],
        partial=missing,
    )


def _count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
