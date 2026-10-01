"""Budget checks for Moonlighter."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from moonlighter.config import Config, bundled_codex_usage_path, default_state_dir

WINDOW_RE = re.compile(
    r"^(?P<name>5\s*hour|weekly)\s+"
    r"(?P<remaining>\d+(?:\.\d+)?)%\s+remaining\s+resets\s+"
    r"(?P<reset>.+)$",
    re.IGNORECASE,
)


class BudgetError(ValueError):
    """Raised when budget information cannot be obtained or parsed."""


@dataclass(frozen=True)
class QuotaWindow:
    """A parsed usage quota window."""

    remaining_percent: float
    reset_at: datetime | None


@dataclass(frozen=True)
class BudgetSnapshot:
    """Parsed budget information from codex-usage."""

    five_hour: QuotaWindow
    weekly: QuotaWindow
    checked_at: datetime
    source: Path


@dataclass(frozen=True)
class CodexUsageCommand:
    """Resolved codex-usage command invocation."""

    argv: tuple[str, ...]
    source: Path


@dataclass(frozen=True)
class BudgetGateResult:
    """Decision from the budget gate."""

    allowed: bool
    reason: str
    snapshot: BudgetSnapshot | None = None


def resolve_codex_usage_command() -> CodexUsageCommand:
    """Find codex-usage, preferring PATH over the bundled fallback."""
    installed = shutil.which("codex-usage")
    if installed is not None:
        path = Path(installed)
        return CodexUsageCommand(argv=(str(path),), source=path)

    fallback = bundled_codex_usage_path()
    if fallback.exists() and fallback.is_file():
        return CodexUsageCommand(argv=(sys.executable, str(fallback)), source=fallback)

    raise BudgetError(f"codex-usage command not found and fallback is missing: {fallback}")


def parse_codex_usage_output(text: str, source: Path, checked_at: datetime) -> BudgetSnapshot:
    """Parse codex-usage human output into a budget snapshot."""
    windows: dict[str, QuotaWindow] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = WINDOW_RE.match(line)
        if match is None:
            continue
        name = "five_hour" if match.group("name").lower().replace(" ", "") == "5hour" else "weekly"
        remaining = float(match.group("remaining"))
        if not 0 <= remaining <= 100:
            raise BudgetError(f"{match.group('name')} remaining percent out of range: {remaining}")
        windows[name] = QuotaWindow(
            remaining_percent=remaining,
            reset_at=_parse_reset_time(match.group("reset")),
        )

    five_hour = windows.get("five_hour")
    weekly = windows.get("weekly")
    if five_hour is None or weekly is None:
        raise BudgetError("codex-usage output did not include both 5 hour and weekly windows")

    return BudgetSnapshot(five_hour=five_hour, weekly=weekly, checked_at=checked_at, source=source)


def check_budget(config: Config, now: datetime | None = None) -> BudgetGateResult:
    """Run the budget check, store last-known status, and fail closed on errors."""
    checked_at = now or datetime.now().astimezone()
    state_dir = default_state_dir()

    try:
        command = resolve_codex_usage_command()
        result = subprocess.run(
            list(command.argv),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "no command output"
            raise BudgetError(f"codex-usage failed: {detail}")
        snapshot = parse_codex_usage_output(result.stdout, command.source, checked_at)
        gate = evaluate_budget_snapshot(snapshot, config.budget.weekly_reserve_percent, checked_at)
    except BudgetError as exc:
        gate = BudgetGateResult(allowed=False, reason=str(exc), snapshot=None)

    write_budget_status(state_dir, gate, checked_at)
    if not gate.allowed:
        append_budget_log(state_dir, gate, checked_at)
    return gate


def evaluate_budget_snapshot(
    snapshot: BudgetSnapshot, weekly_reserve_percent: int, now: datetime | None = None
) -> BudgetGateResult:
    """Apply Moonlighter's conservative budget policy to a parsed snapshot."""
    current_time = now or snapshot.checked_at
    if snapshot.five_hour.remaining_percent <= 0:
        return BudgetGateResult(False, "5-hour Codex budget is exhausted", snapshot)

    weekly_floor = weekly_remaining_floor(
        reserve_percent=weekly_reserve_percent,
        reset_at=snapshot.weekly.reset_at,
        now=current_time,
    )
    if weekly_floor is None:
        return BudgetGateResult(False, "weekly reset time is unknown", snapshot)

    if snapshot.weekly.remaining_percent < weekly_floor:
        return BudgetGateResult(
            False,
            "weekly Codex budget is below the safe-spend curve "
            f"({snapshot.weekly.remaining_percent:.1f}% remaining; need {weekly_floor:.1f}%)",
            snapshot,
        )

    return BudgetGateResult(
        True,
        "budget is above the safe-spend curve "
        f"({snapshot.weekly.remaining_percent:.1f}% remaining; need {weekly_floor:.1f}%)",
        snapshot,
    )


def weekly_remaining_floor(
    reserve_percent: int, reset_at: datetime | None, now: datetime | None = None
) -> float | None:
    """Return the minimum safe weekly remaining percent for a linear weekly curve."""
    if reset_at is None:
        return None
    current_time = now or datetime.now().astimezone()
    final_day = timedelta(days=1)
    spend_window = timedelta(days=6)
    remaining = reset_at - current_time
    curve_remaining = remaining - final_day
    remaining_fraction = max(
        0.0,
        min(1.0, curve_remaining.total_seconds() / spend_window.total_seconds()),
    )
    return reserve_percent + (100 - reserve_percent) * remaining_fraction


def write_budget_status(state_dir: Path, result: BudgetGateResult, checked_at: datetime) -> None:
    """Store last-known budget status for read-only `moon status`."""
    state_dir.mkdir(parents=True, exist_ok=True)
    data: dict[str, object] = {
        "budget": _budget_summary(result),
        "budget_allowed": result.allowed,
        "budget_reason": result.reason,
        "budget_checked_at": checked_at.isoformat(),
    }
    if result.snapshot is not None:
        data["budget_details"] = {
            "five_hour_remaining_percent": result.snapshot.five_hour.remaining_percent,
            "five_hour_reset_at": _datetime_to_json(result.snapshot.five_hour.reset_at),
            "weekly_remaining_percent": result.snapshot.weekly.remaining_percent,
            "weekly_reset_at": _datetime_to_json(result.snapshot.weekly.reset_at),
            "source": str(result.snapshot.source),
        }
    (state_dir / "status.json").write_text(
        f"{json.dumps(data, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )


def append_budget_log(state_dir: Path, result: BudgetGateResult, checked_at: datetime) -> None:
    """Append a terse global budget gate log line."""
    logs = state_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    status = "allowed" if result.allowed else "blocked"
    with (logs / "budget.log").open("a", encoding="utf-8") as file:
        file.write(f"{checked_at.isoformat()} budget {status}: {result.reason}\n")


def _budget_summary(result: BudgetGateResult) -> str:
    if result.snapshot is None:
        return f"blocked: {result.reason}"
    snapshot = result.snapshot
    status = "allowed" if result.allowed else "blocked"
    return (
        f"{status}: 5-hour {snapshot.five_hour.remaining_percent:.1f}% remaining; "
        f"weekly {snapshot.weekly.remaining_percent:.1f}% remaining"
    )


def _parse_reset_time(value: str) -> datetime | None:
    stripped = value.strip()
    if stripped.lower() == "unknown":
        return None
    try:
        return datetime.strptime(stripped, "%Y-%m-%d %H:%M").astimezone()
    except ValueError as exc:
        raise BudgetError(f"invalid reset time {value!r}; expected YYYY-MM-DD HH:MM") from exc


def _datetime_to_json(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
