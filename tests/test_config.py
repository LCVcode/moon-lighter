from __future__ import annotations

import os
from pathlib import Path

import pytest

from moonlighter.config import (
    SAMPLE_CONFIG,
    ConfigIssue,
    check_config,
    parse_config_text,
    validate_config,
    write_sample_config,
)


def test_parse_sample_config() -> None:
    config = parse_config_text(SAMPLE_CONFIG)

    assert config.runner.provider == "openai-codex"
    assert config.runner.model == "gpt-5.5"
    assert config.runner.thinking == "medium"
    assert config.runner.image == "moonlighter-runner:0.1.0-dev"
    assert config.runner.chunk_minutes == 20
    assert config.budget.weekly_reserve_percent == 25
    assert len(config.work_windows) == 1


def test_write_sample_config_does_not_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("existing", encoding="utf-8")

    assert write_sample_config(path) == path
    assert path.read_text(encoding="utf-8") == "existing"


def test_check_config_missing_file(tmp_path: Path) -> None:
    result = check_config(tmp_path / "missing.toml")

    assert result.has_errors
    assert result.config is None
    assert "moon config init" in result.issues[0].message


def test_validate_rejects_bad_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = tmp_path / "projects"
    project_root.mkdir()
    text = SAMPLE_CONFIG.replace(
        'project_root = "~/moon-projects"', f'project_root = "{project_root}"'
    )
    config = parse_config_text(text.replace('provider = "openai-codex"', 'provider = "anthropic"'))

    monkeypatch.setattr(
        "moonlighter.config.bundled_codex_usage_path", lambda: Path("scripts/codex-usage")
    )
    monkeypatch.setattr("moonlighter.config.shutil.which", lambda _name: None)

    issues = validate_config(config)

    assert ConfigIssue("error", "docker executable was not found on PATH") in issues
    assert any("unsupported provider" in issue.message for issue in issues)


def test_default_config_path_uses_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", os.fspath(tmp_path))
    from moonlighter.config import default_config_path

    assert default_config_path() == tmp_path / ".config" / "moon" / "config.toml"
