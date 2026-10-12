from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

import pytest

import moonlighter
from moonlighter.config import Config, RunnerConfig
from moonlighter.gates import GateResult
from moonlighter.history_queries import load_history
from moonlighter.projects import initialize_project
from moonlighter.report_usage import quota_delta, read_chunk_tokens, session_offsets
from moonlighter.runner import RunnerResult
from moonlighter.tick import run_tick
from moonlighter.work_reports import (
    ChunkReport,
    ReportError,
    SessionReport,
    TokenUsage,
    UsageObservation,
    load_report,
    save_report,
)


def test_capture_through_all_cli_consumers(tmp_path, monkeypatch, capsys) -> None:
    state = tmp_path / "state"
    root = tmp_path / "projects"
    for name in ("alpha", "beta"):
        initialize_project(root / name)
    config = Config(root, RunnerConfig("openai-codex", "test-model", "medium"))
    for module in ("moonlighter", "moonlighter.tick", "moonlighter.status"):
        monkeypatch.setattr(module + ".default_state_dir", lambda: state)
    monkeypatch.setattr(moonlighter, "load_valid_config", lambda: config)
    monkeypatch.setattr(
        "moonlighter.status._render_service_status", lambda **_: ["Service: simulated"]
    )
    monkeypatch.setattr(
        "moonlighter.status._render_runner_status", lambda **_: ["Runner: simulated"]
    )
    run_tick(
        config,
        gate_checker=lambda _: GateResult(True, "ok"),
        runner=lambda request: RunnerResult(
            True,
            3,
            tokens=TokenUsage(total=30),
            summary=f"Built {request.project_dir.name}",
            next_step="Review the result",
        ),
    )
    assert len(load_history(state).records) == 1
    # One unreadable index line must not hide valid captured/legacy data.
    with (state / "runs.jsonl").open("ab") as file:
        file.write(b"\xff\xfe\n")
    moonlighter.main(["log", "--color", "never"])
    output = capsys.readouterr().out
    assert "History incomplete" in output and "Tokens: 60" in output
    assert "Built alpha" in output and "Built beta" in output
    assert "└─" in output
    moonlighter.main(["status", "alpha", "--color", "never"])
    assert "Built alpha" in capsys.readouterr().out
    moonlighter.main(["status", "--color", "never"])
    assert "success" in capsys.readouterr().out
    moonlighter.main(["report", "--color", "never"])
    assert "Tokens: 60" in capsys.readouterr().out
    moonlighter.main(["report", "alpha", "--details", "--color", "never"])
    output = capsys.readouterr().out
    assert "Tokens: 30" in output and "beta" not in output
    assert "Next: Review the result" in output


@pytest.mark.parametrize("mutation", ["partial", "source", "requested", "schema", "duplicates"])
def test_malformed_metadata_cannot_produce_complete_totals(tmp_path, mutation) -> None:
    report = SessionReport("one", "2026-01-01T00:00:00+00:00", "work", "manual", None)
    report.chunks = [ChunkReport("one/1", "alpha", report.started_at, tokens=TokenUsage(total=10))]
    data = asdict(report)
    if mutation in ("partial", "source"):
        data["chunks"][0]["tokens"][mutation] = "bad" if mutation == "partial" else 1
    elif mutation == "requested":
        data["requested_project"] = 42
    elif mutation == "schema":
        data["schema_version"] = True
    else:
        data["chunks"].append(data["chunks"][0])
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ReportError):
        load_report(path)


def test_new_forked_files_require_current_timestamps_and_missing_files_are_partial(
    tmp_path,
) -> None:
    old = tmp_path / "old.jsonl"
    old.write_text("")
    offsets = session_offsets(tmp_path)
    old.unlink()
    started = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    messages = [
        {"type": "message", "message": {"role": "assistant", "usage": {"totalTokens": 999}}},
        {
            "type": "message",
            "timestamp": "2025-12-31T23:59:00+00:00",
            "message": {"role": "assistant", "usage": {"totalTokens": 500}},
        },
        {
            "type": "message",
            "timestamp": "2026-01-01T00:01:00+00:00",
            "message": {"role": "assistant", "usage": {"totalTokens": 10}},
        },
    ]
    (tmp_path / "new.jsonl").write_text("\n".join(json.dumps(entry) for entry in messages))
    usage = read_chunk_tokens(tmp_path, offsets, started)
    assert usage is not None and usage.total == 10 and usage.partial
    # Losing a baseline file independently makes the remaining subtotal partial.
    (tmp_path / "new.jsonl").write_text(json.dumps(messages[-1]))
    usage = read_chunk_tokens(tmp_path, offsets, started)
    assert usage is not None and usage.total == 10 and usage.partial


def test_usage_enumeration_failure_is_unknown_not_an_execution_error(tmp_path, monkeypatch) -> None:
    def unavailable(*_args, **_kwargs):
        raise OSError("storage unavailable")

    monkeypatch.setattr(Path, "rglob", unavailable)
    assert read_chunk_tokens(tmp_path, {}) is None


def test_append_offsets_remain_authoritative_after_wall_clock_moves_backward(tmp_path) -> None:
    path = tmp_path / "session.jsonl"
    path.write_text("")
    offsets = session_offsets(tmp_path)
    path.write_text(
        json.dumps(
            {
                "type": "message",
                "message": {"role": "assistant", "timestamp": 0, "usage": {"totalTokens": 10}},
            }
        )
    )
    usage = read_chunk_tokens(tmp_path, offsets, datetime.now().astimezone())
    assert usage is not None and usage.total == 10


def test_project_log_includes_failures_before_a_chunk_started(
    tmp_path, monkeypatch, capsys
) -> None:
    report = SessionReport(
        "one",
        "2026-01-01T00:00:00+00:00",
        "run",
        "manual",
        "alpha",
        status="failed",
        error="runner unavailable",
    )
    save_report(tmp_path, report)
    monkeypatch.setattr(moonlighter, "default_state_dir", lambda: tmp_path)
    moonlighter.main(["log", "--project", "alpha", "--color", "never"])
    assert "runner unavailable" in capsys.readouterr().out


def test_latest_legacy_index_record_wins_when_no_report_exists(tmp_path) -> None:
    data = {
        "schema_version": 1,
        "run_id": "one",
        "started_at": "2026-01-01T00:00:00+00:00",
        "ended_at": "2026-01-01T00:01:00+00:00",
        "elapsed_seconds": 60,
        "entrypoint": "run",
        "trigger": "manual",
        "requested_project": "alpha",
        "projects": ["alpha"],
        "status": "success",
        "skip_reason": None,
        "error": None,
        "disposition": None,
        "ran_chunks": 1,
        "succeeded_chunks": 1,
        "failed_chunks": 0,
    }
    first = json.dumps(data)
    data.update(status="failed", error="corrected outcome", succeeded_chunks=0, failed_chunks=1)
    (tmp_path / "runs.jsonl").write_text(first + "\n" + json.dumps(data) + "\n")
    history = load_history(tmp_path)
    assert len(history.records) == 1
    assert history.records[0].status == "failed"


def test_quota_comparison_normalizes_naive_times_and_equivalent_offsets() -> None:
    before = UsageObservation(
        "2026-01-01T00:00:00", 80, five_hour_reset="2026-01-03T00:00:00+00:00"
    )
    after = replace(before, five_hour_remaining=76, five_hour_reset="2026-01-02T19:00:00-05:00")
    assert quota_delta(before, after, "5h") == "4.0%"
