"""Manual Moonlighter tick orchestration."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from random import Random

from moonlighter.budget import BudgetGateResult, check_budget
from moonlighter.config import Config, default_state_dir
from moonlighter.gates import GateResult, preflight_tick_gates
from moonlighter.projects import (
    PRIORITY_TIERS,
    ProjectError,
    ProjectRef,
    discover_projects,
    initialize_project,
    load_project_state,
    state_path,
)
from moonlighter.runner import RunnerError, RunnerRequest, RunnerResult, run_project_chunk

Runner = Callable[[RunnerRequest], RunnerResult]
GateChecker = Callable[[Config], GateResult]
BudgetChecker = Callable[[Config], BudgetGateResult]


class TickError(RuntimeError):
    """Raised when a manual tick cannot run."""


@dataclass(frozen=True)
class TickResult:
    """Outcome from one manual tick."""

    ran_chunks: int
    succeeded_chunks: int
    failed_chunks: int
    skipped_reason: str | None = None

    @property
    def exit_code(self) -> int:
        """Return the CLI exit code for this tick outcome."""
        if self.failed_chunks and not self.succeeded_chunks:
            return 1
        return 0


def run_tick(
    config: Config,
    *,
    runner: Runner = run_project_chunk,
    gate_checker: GateChecker = preflight_tick_gates,
    rng: Random | None = None,
    force: bool = False,
    project_name: str | None = None,
    chunk_minutes: int | None = None,
    ignore_budget: bool = False,
    budget_checker: BudgetChecker = check_budget,
    update_budget_after_chunk: bool = False,
) -> TickResult:
    """Run one manual scheduler tick."""
    if not config.project_root.exists():
        raise TickError(f"project root does not exist: {config.project_root}")
    if not config.project_root.is_dir():
        raise TickError(f"project root is not a directory: {config.project_root}")

    first_gate = _initial_gate(
        config,
        force=force,
        ignore_budget=ignore_budget,
        gate_checker=gate_checker,
        budget_checker=budget_checker,
    )
    if not first_gate.allowed:
        result = TickResult(0, 0, 0, skipped_reason=first_gate.reason)
        append_global_tick_log(f"skip: {first_gate.reason}")
        return result

    discovered = discover_projects(config.project_root)
    uninitialized = tuple(project for project in discovered if not project.initialized)
    for project in uninitialized:
        initialize_project(project.path)

    attempted: set[Path] = set()
    succeeded = 0
    failed = 0
    random_source = rng or random.Random()

    while True:
        project = choose_next_project(
            config.project_root, uninitialized, attempted, random_source, project_name=project_name
        )
        if project is None:
            break

        if not force:
            gate = gate_checker(config)
            if not gate.allowed:
                break

        attempted.add(project)
        try:
            result = runner(
                RunnerRequest(project_dir=project, config=config, chunk_minutes=chunk_minutes)
            )
        except (ProjectError, RunnerError, OSError) as exc:
            result = RunnerResult(success=False, elapsed_seconds=0, error=str(exc))

        append_chunk_log(project.name, result)
        if update_budget_after_chunk:
            budget_result = budget_checker(config)
            append_global_tick_log(f"budget refresh: {budget_result.reason}")
        if result.success:
            succeeded += 1
        else:
            failed += 1

        if force or project_name is not None:
            break

    tick_result = TickResult(
        ran_chunks=succeeded + failed,
        succeeded_chunks=succeeded,
        failed_chunks=failed,
        skipped_reason=None if succeeded or failed else "no eligible projects",
    )
    if tick_result.skipped_reason is not None:
        append_global_tick_log(f"skip: {tick_result.skipped_reason}")
    return tick_result


def append_chunk_log(project_name: str, result: RunnerResult) -> None:
    """Append a terse global tick summary for a project chunk."""
    status = "ok" if result.success else "failed"
    parts = [
        f"project={project_name}",
        f"status={status}",
        f"elapsed={result.elapsed_seconds:.1f}s",
        f"commits={result.commit_count}",
        f"diff=+{result.inserted_lines} -{result.deleted_lines}",
    ]
    if result.disposition is not None:
        parts.append(f"disposition={result.disposition}")
    if result.error is not None:
        parts.append(f"error={result.error}")
    append_global_tick_log(" ".join(parts))


def append_global_tick_log(message: str) -> None:
    """Append one terse line to the global tick log."""
    logs = default_state_dir() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / "tick.log").open("a", encoding="utf-8") as file:
        file.write(f"{datetime.now().astimezone().isoformat()} {message}\n")


def _initial_gate(
    config: Config,
    *,
    force: bool,
    ignore_budget: bool,
    gate_checker: GateChecker,
    budget_checker: BudgetChecker,
) -> GateResult:
    if not force:
        return gate_checker(config)
    if ignore_budget:
        return GateResult(True, "forced")
    budget = budget_checker(config)
    return GateResult(budget.allowed, budget.reason, budget_result=budget)


def choose_next_project(
    project_root: Path,
    uninitialized_at_start: tuple[ProjectRef, ...],
    attempted: set[Path],
    rng: Random,
    project_name: str | None = None,
) -> Path | None:
    """Choose the next project for this tick."""
    if project_name is not None:
        project_dir = project_root / project_name
        if project_dir in attempted:
            return None
        if not project_dir.exists():
            project_dir.mkdir(parents=True)
            initialize_project(project_dir)
        elif not (project_dir / ".moon").is_dir():
            initialize_project(project_dir)
        return project_dir if _is_eligible(project_dir) else None
    uninitialized_candidates = [
        project.path
        for project in uninitialized_at_start
        if project.path not in attempted and _is_eligible(project.path)
    ]
    if uninitialized_candidates:
        return rng.choice(uninitialized_candidates)

    candidates = [
        project.path
        for project in discover_projects(project_root)
        if project.path not in attempted and _is_eligible(project.path)
    ]
    if not candidates:
        return None
    return min(candidates, key=_priority_last_run_sort_key)


def _is_eligible(project_dir: Path) -> bool:
    try:
        state = load_project_state(state_path(project_dir))
    except ProjectError:
        return False
    return not state.paused and state.disposition == "active"


def _priority_last_run_sort_key(project_dir: Path) -> tuple[int, str, str]:
    try:
        state = load_project_state(state_path(project_dir))
    except ProjectError:
        return (len(PRIORITY_TIERS), "", project_dir.name)
    return (PRIORITY_TIERS.index(state.priority), state.last_run_at or "", project_dir.name)
