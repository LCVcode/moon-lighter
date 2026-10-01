"""Project discovery, initialization, and state validation for Moonlighter."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, cast

MOON_DIR_NAME = ".moon"
BRIEF_FILE_NAME = "brief.md"
STATUS_FILE_NAME = "status.md"
STATE_FILE_NAME = "state.json"
AGENT_RESULT_FILE_NAME = "agent-result.json"
LOGS_DIR_NAME = "logs"

BRIEF_PLACEHOLDER = "Replace me with a project concept/description.\n"
INITIAL_STATUS_TEXT = "# Moon Status\n\nInitialized by Moonlighter.\n"
STATE_SCHEMA_VERSION = 1

Disposition = Literal["active", "needs_direction", "complete", "tabled"]
VALID_DISPOSITIONS: frozenset[str] = frozenset({"active", "needs_direction", "complete", "tabled"})


class ProjectError(ValueError):
    """Raised when project metadata is invalid or cannot be initialized."""


@dataclass(frozen=True)
class ProjectRef:
    """A direct child project under the configured project root."""

    name: str
    path: Path
    initialized: bool


@dataclass(frozen=True)
class ProjectState:
    """Moon-owned machine state for a project."""

    schema_version: int
    paused: bool
    disposition: Disposition
    last_run_at: str | None
    pi_session_id: str | None
    pi_session_file: str | None
    last_claimed_from: str | None
    disposition_summary: str | None = None


@dataclass(frozen=True)
class AgentResult:
    """Validated runner handoff written by the Pi agent."""

    disposition: Disposition
    summary: str | None = None


def moon_dir(project_dir: Path) -> Path:
    """Return the path to a project's Moon metadata directory."""
    return project_dir / MOON_DIR_NAME


def brief_path(project_dir: Path) -> Path:
    """Return the path to a project's human-authored brief."""
    return moon_dir(project_dir) / BRIEF_FILE_NAME


def status_path(project_dir: Path) -> Path:
    """Return the path to a project's human-readable Moon status."""
    return moon_dir(project_dir) / STATUS_FILE_NAME


def state_path(project_dir: Path) -> Path:
    """Return the path to a project's Moon-owned state file."""
    return moon_dir(project_dir) / STATE_FILE_NAME


def agent_result_path(project_dir: Path) -> Path:
    """Return the path to a project's agent-result handoff file."""
    return moon_dir(project_dir) / AGENT_RESULT_FILE_NAME


def logs_dir(project_dir: Path) -> Path:
    """Return the path to a project's Moon log directory."""
    return moon_dir(project_dir) / LOGS_DIR_NAME


def discover_projects(project_root: Path) -> tuple[ProjectRef, ...]:
    """Discover direct child project directories under a configured project root."""
    if not project_root.exists():
        raise ProjectError(f"project root does not exist: {project_root}")
    if not project_root.is_dir():
        raise ProjectError(f"project root is not a directory: {project_root}")

    projects = [
        ProjectRef(entry.name, entry, moon_dir(entry).is_dir())
        for entry in project_root.iterdir()
        if entry.is_dir()
    ]
    return tuple(sorted(projects, key=lambda project: project.name))


def initial_project_state() -> ProjectState:
    """Return the initial Moon-owned machine state for a project."""
    return ProjectState(
        schema_version=STATE_SCHEMA_VERSION,
        paused=False,
        disposition="active",
        last_run_at=None,
        pi_session_id=None,
        pi_session_file=None,
        last_claimed_from=None,
        disposition_summary=None,
    )


def project_state_to_json(state: ProjectState) -> dict[str, object]:
    """Convert project state to a JSON-serializable mapping."""
    return {
        "schema_version": state.schema_version,
        "paused": state.paused,
        "disposition": state.disposition,
        "last_run_at": state.last_run_at,
        "pi_session_id": state.pi_session_id,
        "pi_session_file": state.pi_session_file,
        "last_claimed_from": state.last_claimed_from,
        "disposition_summary": state.disposition_summary,
    }


def initialize_project(project_dir: Path) -> None:
    """Create the standard Moon project structure without overwriting existing files."""
    project_dir.mkdir(parents=True, exist_ok=True)
    moon_dir(project_dir).mkdir(exist_ok=True)
    logs_dir(project_dir).mkdir(exist_ok=True)

    _write_text_if_missing(brief_path(project_dir), BRIEF_PLACEHOLDER)
    _write_text_if_missing(status_path(project_dir), INITIAL_STATUS_TEXT)
    _write_json_if_missing(state_path(project_dir), project_state_to_json(initial_project_state()))

    ensure_project_git(project_dir)
    ensure_moon_gitignored(project_dir)


def load_project_state(path: Path) -> ProjectState:
    """Load and validate a Moon-owned state file without repairing it."""
    data = _load_json_object(path, "project state")
    return parse_project_state(data)


def save_project_state(path: Path, state: ProjectState) -> None:
    """Write validated Moon-owned project state."""
    path.write_text(
        f"{json.dumps(project_state_to_json(state), indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )


def set_project_claim_source(project_dir: Path, source_path: Path) -> None:
    """Record where a project was most recently claimed from."""
    state_file = state_path(project_dir)
    state = load_project_state(state_file)
    save_project_state(
        state_file,
        replace(state, last_claimed_from=str(source_path.resolve(strict=False))),
    )


def activate_project_state(project_dir: Path) -> None:
    """Clear project pause and return a project to active disposition."""
    state_file = state_path(project_dir)
    state = load_project_state(state_file)
    save_project_state(state_file, replace(state, paused=False, disposition="active"))


def set_project_paused(project_dir: Path, paused: bool) -> None:
    """Set per-project pause state."""
    state_file = state_path(project_dir)
    state = load_project_state(state_file)
    save_project_state(state_file, replace(state, paused=paused))


def parse_project_state(data: dict[str, object]) -> ProjectState:
    """Validate parsed project-state JSON."""
    schema_version = _required_int(data, "schema_version")
    if schema_version != STATE_SCHEMA_VERSION:
        raise ProjectError(
            f"state.schema_version must be {STATE_SCHEMA_VERSION}, got {schema_version}"
        )

    paused = _required_bool(data, "paused")
    disposition = _required_disposition(data, "disposition")
    last_run_at = _optional_string(data, "last_run_at")
    pi_session_id = _optional_string(data, "pi_session_id")
    pi_session_file = _optional_string(data, "pi_session_file")
    last_claimed_from = _optional_string(data, "last_claimed_from")
    disposition_summary = _optional_string_missing_ok(data, "disposition_summary")

    return ProjectState(
        schema_version=schema_version,
        paused=paused,
        disposition=disposition,
        last_run_at=last_run_at,
        pi_session_id=pi_session_id,
        pi_session_file=pi_session_file,
        last_claimed_from=last_claimed_from,
        disposition_summary=disposition_summary,
    )


def load_agent_result(path: Path) -> AgentResult:
    """Load and validate an agent-result handoff file."""
    data = _load_json_object(path, "agent result")
    return parse_agent_result(data)


def parse_agent_result(data: dict[str, object]) -> AgentResult:
    """Validate parsed agent-result JSON."""
    disposition = _required_disposition(data, "disposition")
    summary = _optional_string(data, "summary")
    return AgentResult(disposition=disposition, summary=summary)


def ensure_project_git(project_dir: Path) -> None:
    """Initialize a Git repository for the project if the project is not its own repo."""
    if shutil.which("git") is None:
        raise ProjectError("git executable was not found on PATH")

    if _is_project_git_toplevel(project_dir):
        return

    result = subprocess.run(
        ["git", "init"],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown git init failure"
        raise ProjectError(f"failed to initialize git repository at {project_dir}: {detail}")


def ensure_moon_gitignored(project_dir: Path) -> None:
    """Ensure the project .gitignore ignores the Moon metadata directory."""
    gitignore = project_dir / ".gitignore"
    line = f"{MOON_DIR_NAME}/"

    if not gitignore.exists():
        gitignore.write_text(f"{line}\n", encoding="utf-8")
        return

    text = gitignore.read_text(encoding="utf-8")
    lines = text.splitlines()
    if line in lines:
        return

    separator = "" if text.endswith("\n") or not text else "\n"
    gitignore.write_text(f"{text}{separator}{line}\n", encoding="utf-8")


def _write_text_if_missing(path: Path, text: str) -> None:
    if not path.exists():
        path.write_text(text, encoding="utf-8")


def _write_json_if_missing(path: Path, data: dict[str, object]) -> None:
    if not path.exists():
        path.write_text(f"{json.dumps(data, indent=2, sort_keys=True)}\n", encoding="utf-8")


def _is_project_git_toplevel(project_dir: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    try:
        toplevel = Path(result.stdout.strip()).resolve(strict=False)
        return toplevel == project_dir.resolve(strict=False)
    except OSError:
        return False


def _load_json_object(path: Path, label: str) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProjectError(f"failed to read {label} file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProjectError(f"invalid {label} JSON in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ProjectError(f"{label} JSON must be an object: {path}")
    return data


def _required_int(data: dict[str, object], key: str) -> int:
    value = _required(data, key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ProjectError(f"{key} must be an integer")
    return value


def _required_bool(data: dict[str, object], key: str) -> bool:
    value = _required(data, key)
    if not isinstance(value, bool):
        raise ProjectError(f"{key} must be a boolean")
    return value


def _required_disposition(data: dict[str, object], key: str) -> Disposition:
    value = _required(data, key)
    if not isinstance(value, str) or value not in VALID_DISPOSITIONS:
        valid = ", ".join(sorted(VALID_DISPOSITIONS))
        raise ProjectError(f"{key} must be one of: {valid}")
    return cast(Disposition, value)


def _optional_string(data: dict[str, object], key: str) -> str | None:
    if key not in data:
        raise ProjectError(f"missing required key: {key}")
    return _string_or_none(data[key], key)


def _optional_string_missing_ok(data: dict[str, object], key: str) -> str | None:
    if key not in data:
        return None
    return _string_or_none(data[key], key)


def _string_or_none(value: object, key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProjectError(f"{key} must be a string or null")
    return value


def _required(data: dict[str, object], key: str) -> object:
    if key not in data:
        raise ProjectError(f"missing required key: {key}")
    return data[key]
