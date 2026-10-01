"""Configuration loading and validation for Moonlighter."""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Literal

CONFIG_RELATIVE_PATH = Path(".config/moon/config.toml")
STATE_RELATIVE_PATH = Path(".local/state/moon")
SUPPORTED_PROVIDER = "openai-codex"
VALID_THINKING_LEVELS = frozenset({"off", "minimal", "low", "medium", "high", "xhigh", "max"})
DEFAULT_RUNNER_IMAGE = "moonlighter-runner:0.1.0-dev"

SAMPLE_CONFIG = """# Moonlighter configuration

project_root = "~/moon-projects"

[runner]
provider = "openai-codex"
model = "gpt-5.5"
thinking = "medium"
image = "moonlighter-runner:0.1.0-dev"
chunk_minutes = 20

[budget]
weekly_reserve_percent = 25

[[work_windows]]
days = "daily"
start = "02:00"
end = "04:00"
"""


@dataclass(frozen=True)
class RunnerConfig:
    """Pi/Docker runner configuration."""

    provider: str
    model: str
    thinking: str
    image: str = DEFAULT_RUNNER_IMAGE
    chunk_minutes: int = 20


@dataclass(frozen=True)
class BudgetConfig:
    """Budget policy configuration."""

    weekly_reserve_percent: int = 25


@dataclass(frozen=True)
class WorkWindow:
    """A configured work-hours window."""

    days: str
    start: str
    end: str


@dataclass(frozen=True)
class Config:
    """Moonlighter configuration."""

    project_root: Path
    runner: RunnerConfig
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    work_windows: tuple[WorkWindow, ...] = ()


@dataclass(frozen=True)
class ConfigIssue:
    """A config validation issue."""

    severity: Literal["error", "warning"]
    message: str


@dataclass(frozen=True)
class ConfigCheckResult:
    """Config validation result."""

    config_path: Path
    config: Config | None
    issues: tuple[ConfigIssue, ...]

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(issue.severity == "warning" for issue in self.issues)


def default_config_path() -> Path:
    """Return the default user config path."""
    return Path.home() / CONFIG_RELATIVE_PATH


def default_state_dir() -> Path:
    """Return the default user state directory."""
    return Path.home() / STATE_RELATIVE_PATH


def bundled_codex_usage_path() -> Path:
    """Return the installed bundled codex-usage fallback path."""
    return Path(str(resources.files("moonlighter.resources").joinpath("codex-usage")))


def expand_user_path(value: str) -> Path:
    """Expand a user-facing path string."""
    return Path(value).expanduser()


def _as_mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a table")
    return value


def _as_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _as_int(value: object, name: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def parse_config_text(text: str) -> Config:
    """Parse config TOML text into a Config object."""
    data = tomllib.loads(text)

    project_root = expand_user_path(_as_string(data.get("project_root"), "project_root"))

    runner_data = _as_mapping(data.get("runner"), "runner")
    runner = RunnerConfig(
        provider=_as_string(runner_data.get("provider"), "runner.provider"),
        model=_as_string(runner_data.get("model"), "runner.model"),
        thinking=_as_string(runner_data.get("thinking"), "runner.thinking"),
        image=_as_string(runner_data.get("image", DEFAULT_RUNNER_IMAGE), "runner.image"),
        chunk_minutes=_as_int(runner_data.get("chunk_minutes", 20), "runner.chunk_minutes"),
    )

    budget_data = data.get("budget", {})
    budget_mapping = _as_mapping(budget_data, "budget")
    budget = BudgetConfig(
        weekly_reserve_percent=_as_int(
            budget_mapping.get("weekly_reserve_percent", 25),
            "budget.weekly_reserve_percent",
        )
    )

    window_values = data.get("work_windows", [])
    if not isinstance(window_values, list):
        raise ValueError("work_windows must be an array of tables")
    work_windows = tuple(
        WorkWindow(
            days=_as_string(
                _as_mapping(window, "work_windows entry").get("days"), "work_windows.days"
            ),
            start=_as_string(window.get("start"), "work_windows.start"),
            end=_as_string(window.get("end"), "work_windows.end"),
        )
        for window in window_values
    )

    return Config(
        project_root=project_root, runner=runner, budget=budget, work_windows=work_windows
    )


def load_config(path: Path | None = None) -> Config:
    """Load config from disk."""
    config_path = path or default_config_path()
    return parse_config_text(config_path.read_text(encoding="utf-8"))


def validate_config(config: Config) -> list[ConfigIssue]:
    """Validate a parsed config."""
    issues: list[ConfigIssue] = []

    if config.runner.provider != SUPPORTED_PROVIDER:
        issues.append(
            ConfigIssue(
                "error",
                "unsupported provider "
                f"{config.runner.provider!r}; v1 supports {SUPPORTED_PROVIDER!r}",
            )
        )

    if not config.runner.model:
        issues.append(ConfigIssue("error", "runner.model must be non-empty"))

    if config.runner.thinking not in VALID_THINKING_LEVELS:
        valid = ", ".join(sorted(VALID_THINKING_LEVELS))
        issues.append(ConfigIssue("error", f"runner.thinking must be one of: {valid}"))

    if config.runner.chunk_minutes <= 0:
        issues.append(ConfigIssue("error", "runner.chunk_minutes must be greater than zero"))

    if not 0 <= config.budget.weekly_reserve_percent <= 100:
        issues.append(
            ConfigIssue("error", "budget.weekly_reserve_percent must be between 0 and 100")
        )

    if not config.project_root.exists():
        issues.append(ConfigIssue("warning", f"project root does not exist: {config.project_root}"))
    elif not config.project_root.is_dir():
        issues.append(
            ConfigIssue("error", f"project root is not a directory: {config.project_root}")
        )

    fallback = bundled_codex_usage_path()
    if not fallback.exists():
        issues.append(ConfigIssue("error", f"bundled codex-usage fallback is missing: {fallback}"))
    elif not fallback.is_file():
        issues.append(
            ConfigIssue("error", f"bundled codex-usage fallback is not a file: {fallback}")
        )

    docker = shutil.which("docker")
    if docker is None:
        issues.append(ConfigIssue("error", "docker executable was not found on PATH"))
    else:
        result = subprocess.run(
            [docker, "image", "inspect", config.runner.image],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            issues.append(
                ConfigIssue(
                    "warning",
                    f"runner image is not available locally: {config.runner.image}",
                )
            )

    if not config.work_windows:
        issues.append(
            ConfigIssue("warning", "no work windows configured; moon tick will not run work")
        )

    return issues


def check_config(path: Path | None = None) -> ConfigCheckResult:
    """Load and validate config, collecting user-facing issues."""
    config_path = path or default_config_path()
    issues: list[ConfigIssue] = []

    if not config_path.exists():
        return ConfigCheckResult(
            config_path=config_path,
            config=None,
            issues=(
                ConfigIssue(
                    "error",
                    f"config file does not exist: {config_path}. "
                    "Run `moon config init` to create one.",
                ),
            ),
        )

    try:
        config = load_config(config_path)
    except (OSError, tomllib.TOMLDecodeError, ValueError) as exc:
        return ConfigCheckResult(
            config_path=config_path,
            config=None,
            issues=(ConfigIssue("error", f"failed to load config: {exc}"),),
        )

    issues.extend(validate_config(config))
    return ConfigCheckResult(config_path=config_path, config=config, issues=tuple(issues))


def write_sample_config(path: Path | None = None) -> Path:
    """Write the sample config if it does not already exist."""
    config_path = path or default_config_path()
    if config_path.exists():
        return config_path
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(SAMPLE_CONFIG, encoding="utf-8")
    return config_path
