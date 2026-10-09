from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path
from random import Random

import pytest

import moonlighter
from moonlighter.budget import BudgetGateResult
from moonlighter.config import Config, ConfigCheckResult, RunnerConfig
from moonlighter.gates import GateResult
from moonlighter.projects import (
    initialize_project,
    load_project_state,
    save_project_state,
    state_path,
)
from moonlighter.run_history import read_run_records
from moonlighter.runner import RunnerRequest, RunnerResult
from moonlighter.tick import TickError, TickResult, run_tick


def config_for(project_root: Path) -> Config:
    return Config(
        project_root=project_root,
        runner=RunnerConfig(provider="openai-codex", model="gpt-5.5", thinking="medium"),
    )


def allow_gate(_config: Config) -> GateResult:
    return GateResult(True, "allowed")


@pytest.fixture(autouse=True)
def isolate_tick_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("moonlighter.tick.default_state_dir", lambda: tmp_path / "state")


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_tick_initializes_uninitialized_projects_after_gates_and_runs_one(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "projects"
    alpha = project_root / "alpha"
    beta = project_root / "beta"
    alpha.mkdir(parents=True)
    beta.mkdir()
    calls: list[Path] = []

    def runner(request: RunnerRequest) -> RunnerResult:
        calls.append(request.project_dir)
        return RunnerResult(success=True, elapsed_seconds=1)

    result = run_tick(
        config_for(project_root), runner=runner, gate_checker=allow_gate, rng=Random(0)
    )

    assert result.exit_code == 0
    assert result.succeeded_chunks == 2
    assert state_path(alpha).exists()
    assert state_path(beta).exists()
    assert set(calls) == {alpha, beta}


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_tick_skips_paused_and_terminal_projects(tmp_path: Path) -> None:
    project_root = tmp_path / "projects"
    active = project_root / "active"
    paused = project_root / "paused"
    complete = project_root / "complete"
    for project in (active, paused, complete):
        initialize_project(project)
    paused_state = load_project_state(state_path(paused))
    save_project_state(state_path(paused), replace(paused_state, paused=True))
    complete_state = load_project_state(state_path(complete))
    save_project_state(state_path(complete), replace(complete_state, disposition="complete"))
    calls: list[Path] = []

    def runner(request: RunnerRequest) -> RunnerResult:
        calls.append(request.project_dir)
        return RunnerResult(success=True, elapsed_seconds=1)

    result = run_tick(config_for(project_root), runner=runner, gate_checker=allow_gate)

    assert result.succeeded_chunks == 1
    assert calls == [active]


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_tick_round_robins_by_oldest_last_run(tmp_path: Path) -> None:
    project_root = tmp_path / "projects"
    older = project_root / "older"
    newer = project_root / "newer"
    initialize_project(older)
    initialize_project(newer)
    older_state = load_project_state(state_path(older))
    newer_state = load_project_state(state_path(newer))
    save_project_state(state_path(older), replace(older_state, last_run_at="2026-01-01T00:00:00Z"))
    save_project_state(state_path(newer), replace(newer_state, last_run_at="2026-01-02T00:00:00Z"))
    calls: list[Path] = []

    def runner(request: RunnerRequest) -> RunnerResult:
        calls.append(request.project_dir)
        return RunnerResult(success=True, elapsed_seconds=1)

    run_tick(config_for(project_root), runner=runner, gate_checker=allow_gate)

    assert calls[:2] == [older, newer]


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_tick_prefers_higher_priority_before_oldest_last_run(tmp_path: Path) -> None:
    project_root = tmp_path / "projects"
    low_old = project_root / "low-old"
    high_new = project_root / "high-new"
    initialize_project(low_old)
    initialize_project(high_new)
    low_state = load_project_state(state_path(low_old))
    high_state = load_project_state(state_path(high_new))
    save_project_state(
        state_path(low_old),
        replace(low_state, priority="low", last_run_at="2026-01-01T00:00:00Z"),
    )
    save_project_state(
        state_path(high_new),
        replace(high_state, priority="high", last_run_at="2026-01-02T00:00:00Z"),
    )
    calls: list[Path] = []

    def runner(request: RunnerRequest) -> RunnerResult:
        calls.append(request.project_dir)
        return RunnerResult(success=True, elapsed_seconds=1)

    run_tick(config_for(project_root), runner=runner, gate_checker=allow_gate)

    assert calls[:2] == [high_new, low_old]


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_tick_rechecks_gate_between_chunks(tmp_path: Path) -> None:
    project_root = tmp_path / "projects"
    initialize_project(project_root / "alpha")
    initialize_project(project_root / "beta")
    gates = iter(
        (GateResult(True, "allowed"), GateResult(True, "allowed"), GateResult(False, "blocked"))
    )
    calls: list[Path] = []

    def runner(request: RunnerRequest) -> RunnerResult:
        calls.append(request.project_dir)
        return RunnerResult(success=True, elapsed_seconds=1)

    result = run_tick(
        config_for(project_root),
        runner=runner,
        gate_checker=lambda _config: next(gates),
    )

    assert result.succeeded_chunks == 1
    assert len(calls) == 1


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_tick_force_still_abides_by_budget(tmp_path: Path) -> None:
    project_root = tmp_path / "projects"
    initialize_project(project_root / "alpha")

    result = run_tick(
        config_for(project_root),
        runner=lambda _request: RunnerResult(success=True, elapsed_seconds=1),
        gate_checker=lambda _config: GateResult(False, "outside hours"),
        budget_checker=lambda _config: BudgetGateResult(False, "budget too low"),
        force=True,
    )

    assert result.ran_chunks == 0
    assert result.skipped_reason == "budget too low"


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_tick_force_ignore_budget_bypasses_gates_and_runs_one_chunk(tmp_path: Path) -> None:
    project_root = tmp_path / "projects"
    initialize_project(project_root / "alpha")
    initialize_project(project_root / "beta")
    calls: list[RunnerRequest] = []

    def runner(request: RunnerRequest) -> RunnerResult:
        calls.append(request)
        return RunnerResult(success=True, elapsed_seconds=1)

    result = run_tick(
        config_for(project_root),
        runner=runner,
        gate_checker=lambda _config: GateResult(False, "blocked"),
        force=True,
        project_name="beta",
        chunk_minutes=7,
        ignore_budget=True,
    )

    assert result.succeeded_chunks == 1
    assert len(calls) == 1
    assert calls[0].project_dir == project_root / "beta"
    assert calls[0].chunk_minutes == 7


def test_tick_refreshes_budget_after_chunk_when_requested(tmp_path: Path) -> None:
    project_root = tmp_path / "projects"
    initialize_project(project_root / "alpha")
    budget_calls = 0

    def budget_checker(_config: Config) -> BudgetGateResult:
        nonlocal budget_calls
        budget_calls += 1
        return BudgetGateResult(True, "budget refreshed")

    run_tick(
        config_for(project_root),
        runner=lambda _request: RunnerResult(success=True, elapsed_seconds=1),
        gate_checker=allow_gate,
        budget_checker=budget_checker,
        update_budget_after_chunk=True,
    )

    assert budget_calls == 1
    log_text = (tmp_path / "state" / "logs" / "tick.log").read_text(encoding="utf-8")
    assert "budget refresh: budget refreshed" in log_text


def test_tick_detects_systemd_trigger_from_invocation_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "projects"
    initialize_project(project_root / "alpha")
    monkeypatch.setenv("INVOCATION_ID", "systemd-run-id")
    monkeypatch.setenv("JOURNAL_STREAM", "8:12345")

    run_tick(
        config_for(project_root),
        runner=lambda _request: RunnerResult(success=True, elapsed_seconds=1),
        gate_checker=allow_gate,
        entrypoint="work",
    )

    record = read_run_records(tmp_path / "state")[0]
    assert record.trigger == "systemd"


def test_tick_does_not_treat_ci_invocation_id_as_systemd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "projects"
    initialize_project(project_root / "alpha")
    monkeypatch.setenv("INVOCATION_ID", "github-actions-id")
    monkeypatch.delenv("JOURNAL_STREAM", raising=False)

    run_tick(
        config_for(project_root),
        runner=lambda _request: RunnerResult(success=True, elapsed_seconds=1),
        gate_checker=allow_gate,
        entrypoint="work",
    )

    record = read_run_records(tmp_path / "state")[0]
    assert record.trigger == "manual"


def test_tick_writes_run_history_for_successful_invocation(tmp_path: Path) -> None:
    project_root = tmp_path / "projects"
    initialize_project(project_root / "alpha")

    run_tick(
        config_for(project_root),
        runner=lambda _request: RunnerResult(success=True, elapsed_seconds=1, disposition="active"),
        gate_checker=allow_gate,
        entrypoint="work",
    )

    records = read_run_records(tmp_path / "state")
    assert len(records) == 1
    record = records[0]
    assert record.entrypoint == "work"
    assert record.trigger == "manual"
    assert record.projects == ("alpha",)
    assert record.status == "success"
    assert record.disposition == "active"
    assert record.ran_chunks == 1


def test_tick_writes_run_history_for_skipped_invocation(tmp_path: Path) -> None:
    project_root = tmp_path / "projects"
    project_root.mkdir(parents=True)

    run_tick(
        config_for(project_root),
        gate_checker=lambda _config: GateResult(False, "blocked"),
        entrypoint="work",
    )

    record = read_run_records(tmp_path / "state")[0]
    assert record.status == "skipped"
    assert record.skip_reason == "blocked"
    assert record.projects == ()
    assert record.ran_chunks == 0


def test_tick_logs_skip_and_chunk_summaries(tmp_path: Path) -> None:
    project_root = tmp_path / "projects"
    initialize_project(project_root / "alpha")

    run_tick(
        config_for(project_root),
        runner=lambda _request: RunnerResult(
            success=True,
            elapsed_seconds=2.5,
            disposition="active",
            commit_count=1,
            inserted_lines=4,
            deleted_lines=2,
        ),
        gate_checker=allow_gate,
    )

    log_text = (tmp_path / "state" / "logs" / "tick.log").read_text(encoding="utf-8")
    assert "project=alpha status=ok elapsed=2.5s commits=1 diff=+4 -2" in log_text


def test_tick_respects_gate_before_touching_projects(tmp_path: Path) -> None:
    project_root = tmp_path / "projects"
    project = project_root / "alpha"
    project.mkdir(parents=True)

    result = run_tick(
        config_for(project_root),
        runner=lambda _request: RunnerResult(success=True, elapsed_seconds=1),
        gate_checker=lambda _config: GateResult(False, "blocked"),
    )

    assert result.exit_code == 0
    assert result.skipped_reason == "blocked"
    assert not (project / ".moon").exists()


def test_tick_errors_when_project_root_missing(tmp_path: Path) -> None:
    with pytest.raises(TickError, match="project root does not exist"):
        run_tick(config_for(tmp_path / "missing"), gate_checker=allow_gate)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_tick_exits_nonzero_when_all_runner_attempts_fail(tmp_path: Path) -> None:
    project_root = tmp_path / "projects"
    initialize_project(project_root / "alpha")

    result = run_tick(
        config_for(project_root),
        runner=lambda _request: RunnerResult(success=False, elapsed_seconds=1, error="boom"),
        gate_checker=allow_gate,
    )

    assert result.exit_code == 1


def test_cli_tick_prints_skip_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = config_for(tmp_path / "projects")
    check = ConfigCheckResult(config_path=Path("config.toml"), config=config, issues=())
    monkeypatch.setattr(moonlighter, "check_config", lambda _path=None: check)
    monkeypatch.setattr(
        moonlighter,
        "run_tick",
        lambda _config, **_kwargs: TickResult(0, 0, 0, "blocked"),
    )

    moonlighter.main(["work"])

    captured = capsys.readouterr()
    assert captured.out == "moon work skipped: blocked\n"
    assert captured.err == ""


def test_cli_run_starts_one_forced_chunk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = config_for(tmp_path / "projects")
    check = ConfigCheckResult(config_path=Path("config.toml"), config=config, issues=())
    monkeypatch.setattr(moonlighter, "check_config", lambda _path=None: check)
    calls: list[dict[str, object]] = []

    def fake_run_tick(_config: Config, **kwargs: object) -> TickResult:
        calls.append(kwargs)
        return TickResult(1, 1, 0, None)

    monkeypatch.setattr(moonlighter, "run_tick", fake_run_tick)

    moonlighter.main(["run", "alpha", "--chunk-minutes", "7"])

    captured = capsys.readouterr()
    assert captured.out == ""
    assert calls == [
        {
            "force": True,
            "ignore_budget": False,
            "project_name": "alpha",
            "chunk_minutes": 7,
            "update_budget_after_chunk": True,
            "entrypoint": "run",
        }
    ]


def test_cli_light_is_hidden_alias_for_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = config_for(tmp_path / "projects")
    check = ConfigCheckResult(config_path=Path("config.toml"), config=config, issues=())
    monkeypatch.setattr(moonlighter, "check_config", lambda _path=None: check)
    monkeypatch.setattr(
        moonlighter,
        "run_tick",
        lambda _config, **_kwargs: TickResult(0, 0, 0, "blocked"),
    )

    moonlighter.main(["light"])

    captured = capsys.readouterr()
    assert captured.out == "moon work skipped: blocked\n"
    assert captured.err == ""
