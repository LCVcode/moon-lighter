from __future__ import annotations

from pathlib import Path

import pytest

from moonlighter.budget import BudgetGateResult
from moonlighter.config import Config, RunnerConfig
from moonlighter.gates import GateResult
from moonlighter.projects import initialize_project
from moonlighter.run_history import read_run_records
from moonlighter.runner import RunnerResult
from moonlighter.tick import TickError, run_tick
from moonlighter.work_reports import TokenUsage, read_reports


@pytest.fixture
def setup(tmp_path: Path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setattr("moonlighter.tick.default_state_dir", lambda: state)
    root = tmp_path / "projects"
    initialize_project(root / "alpha")
    initialize_project(root / "beta")
    return Config(root, RunnerConfig("openai-codex", "test-model", "medium")), state


def test_multichunk_report_is_durable_before_runner_and_matches_legacy(setup) -> None:
    config, state = setup

    def runner(_request):
        report = read_reports(state)[0]
        assert report.status == "running"
        assert report.chunks[-1].status == "running"
        return RunnerResult(
            success=True,
            elapsed_seconds=1,
            tokens=TokenUsage(total=30),
            summary="Implemented work",
            next_step="Test it",
            commit_count=2,
        )

    result = run_tick(config, gate_checker=lambda _config: GateResult(True, "ok"), runner=runner)
    report = read_reports(state)[0]
    assert result.ran_chunks == 2
    assert report.status == "success"
    assert len(report.chunks) == 2
    assert report.chunks[0].tokens is not None
    assert report.chunks[0].tokens.total == 30
    assert report.chunks[0].next_step == "Test it"
    assert report.chunks[0].commits == 2
    assert len(read_run_records(state)) == 1  # Sidecar and legacy record are one invocation.


def test_history_start_failure_prevents_execution(setup, monkeypatch) -> None:
    config, state = setup
    calls = []

    def fail(*_args):
        raise OSError("disk full")

    monkeypatch.setattr("moonlighter.work_reports.save_report", fail)
    with pytest.raises(TickError, match="History persistence failed"):
        run_tick(config, runner=lambda request: (calls.append(request), RunnerResult(True, 0))[1])
    assert calls == []
    assert read_reports(state) == ()


def test_child_start_failure_prevents_execution(setup, monkeypatch) -> None:
    config, _state = setup
    calls = []
    import moonlighter.tick as tick

    original = tick.save_report

    def fail_children(state, report):
        if report.chunks:
            raise OSError("cannot start child")
        original(state, report)

    monkeypatch.setattr(tick, "save_report", fail_children)
    with pytest.raises(TickError):
        run_tick(
            config,
            gate_checker=lambda _config: GateResult(True, "ok"),
            runner=lambda request: (calls.append(request), RunnerResult(True, 0))[1],
        )
    assert calls == []


def test_postrun_usage_failure_preserves_success(setup) -> None:
    config, state = setup

    def budget(_config):
        raise OSError("usage unavailable")

    run_tick(
        config,
        gate_checker=lambda _config: GateResult(True, "ok"),
        runner=lambda _request: RunnerResult(success=True, elapsed_seconds=1),
        budget_checker=budget,
        update_budget_after_chunk=True,
    )
    report = read_reports(state)[0]
    assert report.status == "success"
    assert report.chunks[0].budget_after is not None
    assert report.chunks[0].budget_after.error == "usage unavailable"


def test_aborted_invocation_keeps_started_child(setup) -> None:
    config, state = setup

    def runner(_request):
        raise SystemExit("simulated crash")

    with pytest.raises(SystemExit):
        run_tick(config, gate_checker=lambda _config: GateResult(True, "ok"), runner=runner)
    report = read_reports(state)[0]
    assert report.status == "interrupted"
    assert report.chunks[0].status == "interrupted"
    assert report.chunks[0].elapsed_seconds is None


@pytest.mark.parametrize(
    "reason", ["outside configured work windows", "Moonlighter is globally paused"]
)
def test_routine_skips_leave_no_report_or_history(setup, reason) -> None:
    config, state = setup
    result = run_tick(config, gate_checker=lambda _config: GateResult(False, reason))
    assert result.ran_chunks == 0
    assert read_reports(state) == ()
    assert read_run_records(state) == ()


def test_budget_and_operational_failures_are_retained(setup) -> None:
    config, state = setup
    run_tick(
        config, force=True, budget_checker=lambda _config: BudgetGateResult(False, "budget too low")
    )
    report = read_reports(state)[0]
    assert report.status == "skipped"
    assert report.chunks == []
    assert len(read_run_records(state)) == 1
    missing_config = Config(config.project_root / "absent", config.runner)
    with pytest.raises(TickError):
        run_tick(missing_config)
    assert len(read_reports(state)) == 2
    assert any(r.status == "failed" for r in read_reports(state))


def test_terminal_persistence_failure_preserves_completed_child(setup, monkeypatch) -> None:
    config, state = setup
    import moonlighter.tick as tick

    original = tick.save_report

    def fail_terminal(directory, report):
        if report.ended_at is not None:
            raise OSError("terminal write failed")
        original(directory, report)

    monkeypatch.setattr(tick, "save_report", fail_terminal)
    with pytest.raises(TickError, match="terminal write failed"):
        run_tick(
            config,
            force=True,
            ignore_budget=True,
            runner=lambda _request: RunnerResult(True, 1, summary="done"),
        )
    report = read_reports(state)[0]
    assert report.status == "interrupted"
    assert report.chunks[0].status == "success"
    assert report.chunks[0].summary == "done"


def test_ignore_budget_still_observes_usage_without_enforcement(setup) -> None:
    config, state = setup
    calls = []

    def budget(_config):
        calls.append(True)
        return BudgetGateResult(False, "usage unavailable")

    result = run_tick(
        config,
        force=True,
        ignore_budget=True,
        budget_checker=budget,
        update_budget_after_chunk=True,
        runner=lambda _request: RunnerResult(True, 1),
    )
    assert result.succeeded_chunks == 1
    assert len(calls) == 2
    report = read_reports(state)[0]
    assert report.budget_before is not None
    assert report.budget_before.error == "usage unavailable"
    assert report.status == "success"
