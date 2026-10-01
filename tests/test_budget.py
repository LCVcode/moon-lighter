from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from moonlighter.budget import (
    BudgetError,
    BudgetGateResult,
    BudgetSnapshot,
    QuotaWindow,
    check_budget,
    evaluate_budget_snapshot,
    parse_codex_usage_output,
    resolve_codex_usage_command,
    weekly_remaining_floor,
    write_budget_status,
)
from moonlighter.config import Config, RunnerConfig

UTC = ZoneInfo("UTC")

SAMPLE_USAGE = """OpenAI Codex · plus
5 hour   92.5% remaining   resets 2026-01-01 14:00
weekly   60.0% remaining   resets 2026-01-08 12:00
"""


def test_parse_codex_usage_output() -> None:
    checked_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    snapshot = parse_codex_usage_output(SAMPLE_USAGE, Path("codex-usage"), checked_at)

    assert snapshot.five_hour.remaining_percent == 92.5
    assert snapshot.weekly.remaining_percent == 60.0
    assert snapshot.weekly.reset_at is not None


def test_parse_codex_usage_output_fails_closed_for_missing_windows() -> None:
    with pytest.raises(BudgetError, match="both 5 hour and weekly"):
        parse_codex_usage_output("OpenAI Codex\n", Path("codex-usage"), datetime.now(tz=UTC))


def test_weekly_remaining_floor_reaches_reserve_on_sixth_day() -> None:
    now = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)

    assert weekly_remaining_floor(25, now + timedelta(days=7), now) == 100
    assert weekly_remaining_floor(25, now + timedelta(days=1), now) == 25
    assert weekly_remaining_floor(10, now + timedelta(hours=23), now) == 10
    assert weekly_remaining_floor(25, now + timedelta(days=4), now) == 62.5


def test_evaluate_budget_snapshot_allows_above_curve() -> None:
    now = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    snapshot = BudgetSnapshot(
        five_hour=QuotaWindow(remaining_percent=10, reset_at=now + timedelta(hours=1)),
        weekly=QuotaWindow(remaining_percent=70, reset_at=now + timedelta(days=3)),
        checked_at=now,
        source=Path("codex-usage"),
    )

    result = evaluate_budget_snapshot(snapshot, weekly_reserve_percent=25, now=now)

    assert result.allowed is True


def test_evaluate_budget_snapshot_blocks_below_curve() -> None:
    now = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    snapshot = BudgetSnapshot(
        five_hour=QuotaWindow(remaining_percent=10, reset_at=now + timedelta(hours=1)),
        weekly=QuotaWindow(remaining_percent=30, reset_at=now + timedelta(days=3)),
        checked_at=now,
        source=Path("codex-usage"),
    )

    result = evaluate_budget_snapshot(snapshot, weekly_reserve_percent=25, now=now)

    assert result.allowed is False
    assert "safe-spend curve" in result.reason


def test_resolve_codex_usage_command_prefers_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed = tmp_path / "codex-usage"
    installed.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr("moonlighter.budget.shutil.which", lambda _name: str(installed))

    command = resolve_codex_usage_command()

    assert command.source == installed
    assert command.argv == (str(installed),)


def test_resolve_codex_usage_command_uses_python_for_bundled_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fallback = tmp_path / "codex-usage"
    fallback.write_text("print('ok')\n", encoding="utf-8")
    monkeypatch.setattr("moonlighter.budget.shutil.which", lambda _name: None)
    monkeypatch.setattr("moonlighter.budget.bundled_codex_usage_path", lambda: fallback)

    command = resolve_codex_usage_command()

    assert command.source == fallback
    assert command.argv[-1] == str(fallback)


def test_check_budget_fails_closed_and_writes_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing-codex-usage"
    monkeypatch.setattr("moonlighter.budget.shutil.which", lambda _name: None)
    monkeypatch.setattr("moonlighter.budget.bundled_codex_usage_path", lambda: missing)
    monkeypatch.setattr("moonlighter.budget.default_state_dir", lambda: tmp_path / "state")
    config = Config(
        project_root=tmp_path / "projects",
        runner=RunnerConfig(provider="openai-codex", model="gpt-5.5", thinking="medium"),
    )

    result = check_budget(config, now=datetime(2026, 1, 1, 0, 0, tzinfo=UTC))

    assert result.allowed is False
    status = json.loads((tmp_path / "state" / "status.json").read_text(encoding="utf-8"))
    assert status["budget_allowed"] is False
    assert "fallback is missing" in status["budget_reason"]
    log_text = (tmp_path / "state" / "logs" / "budget.log").read_text(encoding="utf-8")
    assert "budget blocked" in log_text


def test_write_budget_status_summary(tmp_path: Path) -> None:
    checked_at = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    snapshot = BudgetSnapshot(
        five_hour=QuotaWindow(remaining_percent=80, reset_at=None),
        weekly=QuotaWindow(remaining_percent=75, reset_at=None),
        checked_at=checked_at,
        source=Path("codex-usage"),
    )

    write_budget_status(
        tmp_path,
        BudgetGateResult(True, "ok", snapshot),
        checked_at,
    )

    data = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert data["budget"] == "allowed: 5-hour 80.0% remaining; weekly 75.0% remaining"
