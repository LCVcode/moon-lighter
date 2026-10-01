"""Global Moonlighter runtime state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

GLOBAL_STATE_SCHEMA_VERSION = 1


class RuntimeStateError(ValueError):
    """Raised when global runtime state is invalid."""


@dataclass(frozen=True)
class GlobalState:
    """Moon-owned global machine state."""

    schema_version: int = GLOBAL_STATE_SCHEMA_VERSION
    paused: bool = False


def global_state_path(state_dir: Path) -> Path:
    """Return the global machine-state file path for a state directory."""
    return state_dir / "state.json"


def load_global_state(state_dir: Path) -> GlobalState:
    """Load global state, returning defaults when it has not been created yet."""
    path = global_state_path(state_dir)
    if not path.exists():
        return GlobalState()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeStateError(f"failed to read global state file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeStateError(f"invalid global state JSON in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeStateError(f"global state JSON must be an object: {path}")

    schema_version = data.get("schema_version")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise RuntimeStateError("global state schema_version must be an integer")
    if schema_version != GLOBAL_STATE_SCHEMA_VERSION:
        raise RuntimeStateError(
            f"global state schema_version must be {GLOBAL_STATE_SCHEMA_VERSION}, "
            f"got {schema_version}"
        )

    paused = data.get("paused")
    if not isinstance(paused, bool):
        raise RuntimeStateError("global state paused must be a boolean")

    return GlobalState(schema_version=schema_version, paused=paused)


def save_global_state(state_dir: Path, state: GlobalState) -> None:
    """Write global state."""
    state_dir.mkdir(parents=True, exist_ok=True)
    data = {"schema_version": state.schema_version, "paused": state.paused}
    global_state_path(state_dir).write_text(
        f"{json.dumps(data, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )


def set_global_paused(state_dir: Path, paused: bool) -> None:
    """Set global pause state."""
    current = load_global_state(state_dir)
    save_global_state(state_dir, GlobalState(schema_version=current.schema_version, paused=paused))
