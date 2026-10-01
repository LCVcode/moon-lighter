"""Reusable scheduler and budget gates for future tick execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from moonlighter.budget import BudgetGateResult, check_budget
from moonlighter.config import Config, default_state_dir
from moonlighter.runtime_state import RuntimeStateError, load_global_state
from moonlighter.schedule import WorkStatus, evaluate_work_windows


@dataclass(frozen=True)
class GateResult:
    """Combined preflight gate decision."""

    allowed: bool
    reason: str
    work_status: WorkStatus | None = None
    budget_result: BudgetGateResult | None = None


def check_work_window_gate(config: Config, now: datetime | None = None) -> GateResult:
    """Check whether configured work windows currently allow work."""
    work_status = evaluate_work_windows(config.work_windows, now)
    if not work_status.is_work_time:
        return GateResult(False, "outside configured work windows", work_status=work_status)
    return GateResult(True, "inside configured work window", work_status=work_status)


def preflight_tick_gates(config: Config, now: datetime | None = None) -> GateResult:
    """Check global pause, work-window, and budget gates for a future tick."""
    try:
        global_state = load_global_state(default_state_dir())
    except RuntimeStateError as exc:
        return GateResult(False, f"global state is invalid: {exc}")

    if global_state.paused:
        return GateResult(False, "Moonlighter is globally paused")

    work_gate = check_work_window_gate(config, now)
    if not work_gate.allowed:
        return work_gate

    budget_gate = check_budget(config, now)
    return GateResult(
        budget_gate.allowed,
        budget_gate.reason,
        work_status=work_gate.work_status,
        budget_result=budget_gate,
    )
