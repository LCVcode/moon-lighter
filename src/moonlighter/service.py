"""User-level systemd service/timer management for Moonlighter."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SERVICE_UNIT_NAME = "moon.service"
TIMER_UNIT_NAME = "moon.timer"
MANAGED_HEADER = "# Managed by Moonlighter. Do not edit manually."
DEFAULT_INTERVAL = "10min"

UnitKind = Literal["service", "timer", "both"]
_INTERVAL_RE = re.compile(
    r"^(?P<count>[1-9][0-9]*)(?P<unit>s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours)$"
)


class ServiceError(RuntimeError):
    """Raised when Moonlighter service management fails."""


@dataclass(frozen=True)
class SystemctlResult:
    """Captured systemctl command result."""

    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ServiceStatus:
    """Read-only service/timer status."""

    service_path: Path
    timer_path: Path
    service_installed: bool
    timer_installed: bool
    timer_enabled: bool | None
    timer_active: bool | None
    service_active: bool | None
    list_timers: str | None


def user_systemd_dir() -> Path:
    """Return the user systemd unit directory."""
    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home).expanduser() / "systemd" / "user"
    return Path.home() / ".config" / "systemd" / "user"


def service_unit_path() -> Path:
    """Return the managed service unit path."""
    return user_systemd_dir() / SERVICE_UNIT_NAME


def timer_unit_path() -> Path:
    """Return the managed timer unit path."""
    return user_systemd_dir() / TIMER_UNIT_NAME


def resolve_moon_executable(explicit: str | None = None) -> Path:
    """Resolve the moon executable for ExecStart."""
    if explicit is not None:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            raise ServiceError(f"moon executable path must be absolute: {explicit}")
        return path.resolve(strict=False)

    discovered = shutil.which("moon")
    if discovered is None:
        raise ServiceError("moon executable was not found on PATH; pass --moon /path/to/moon")
    return Path(discovered).resolve(strict=False)


def normalize_interval(value: str) -> str:
    """Validate and normalize a compact systemd interval."""
    match = _INTERVAL_RE.fullmatch(value.strip())
    if match is None:
        raise ServiceError(
            "interval must be a positive duration like 30s, 10m, 10min, 1h, or 1hour"
        )
    count = match.group("count")
    unit = match.group("unit")
    if unit.startswith("s"):
        return f"{count}s"
    if unit.startswith("m"):
        return f"{count}min"
    return f"{count}h"


def service_path_env(moon_executable: Path) -> str:
    """Return an explicit PATH for Moonlighter's user systemd service."""
    entries: list[str] = []

    def add(path: Path | str) -> None:
        text = str(path)
        if text and text not in entries:
            entries.append(text)

    pi_executable = shutil.which("pi")
    if pi_executable is not None:
        add(Path(pi_executable).parent)
    add(moon_executable.parent)
    for entry in os.environ.get("PATH", os.defpath).split(os.pathsep):
        add(entry)
    for entry in ("/usr/local/bin", "/usr/bin", "/bin"):
        add(entry)
    return os.pathsep.join(entries)


def render_service_unit(moon_executable: Path) -> str:
    """Render the Moonlighter systemd service unit."""
    if not moon_executable.is_absolute():
        raise ServiceError(f"moon executable path must be absolute: {moon_executable}")
    path_env = service_path_env(moon_executable)
    return f"""{MANAGED_HEADER}
[Unit]
Description=Moonlighter scheduled work run
Documentation=https://github.com/LCVcode/moon-lighter

[Service]
Type=oneshot
Environment=MOON_TRIGGER=systemd
Environment=PATH={path_env}
ExecStart={moon_executable} work
"""


def render_timer_unit(interval: str = DEFAULT_INTERVAL) -> str:
    """Render the Moonlighter systemd timer unit."""
    normalized = normalize_interval(interval)
    return f"""{MANAGED_HEADER}
[Unit]
Description=Run Moonlighter scheduled work periodically
Documentation=https://github.com/LCVcode/moon-lighter

[Timer]
OnBootSec=2min
OnUnitActiveSec={normalized}
Unit={SERVICE_UNIT_NAME}
Persistent=false

[Install]
WantedBy=timers.target
"""


def render_units(moon_executable: Path, interval: str = DEFAULT_INTERVAL) -> tuple[str, str]:
    """Render service and timer units."""
    return render_service_unit(moon_executable), render_timer_unit(interval)


def install_units(moon_executable: Path, interval: str = DEFAULT_INTERVAL) -> tuple[Path, Path]:
    """Install managed user-level systemd units without enabling them."""
    service_text, timer_text = render_units(moon_executable, interval)
    service_path = service_unit_path()
    timer_path = timer_unit_path()
    _write_managed_unit(service_path, service_text)
    _write_managed_unit(timer_path, timer_text)
    return service_path, timer_path


def uninstall_units() -> tuple[bool, bool]:
    """Remove managed unit files, refusing to delete non-Moon files."""
    service_removed = _remove_managed_unit(service_unit_path())
    timer_removed = _remove_managed_unit(timer_unit_path())
    return service_removed, timer_removed


def enable_timer() -> None:
    """Enable and start the Moonlighter timer."""
    _run_systemctl_checked(["daemon-reload"])
    _run_systemctl_checked(["enable", "--now", TIMER_UNIT_NAME])


def disable_timer() -> None:
    """Disable and stop the Moonlighter timer."""
    _run_systemctl_checked(["disable", "--now", TIMER_UNIT_NAME])
    _run_systemctl_checked(["daemon-reload"])


def reload_systemd_user() -> None:
    """Reload the user systemd manager."""
    _run_systemctl_checked(["daemon-reload"])


def read_service_status() -> ServiceStatus:
    """Read installed/enabled/active status for Moonlighter units."""
    timer_enabled = _systemctl_bool(["is-enabled", TIMER_UNIT_NAME])
    timer_active = _systemctl_bool(["is-active", TIMER_UNIT_NAME])
    service_active = _systemctl_bool(["is-active", SERVICE_UNIT_NAME])
    list_result = run_systemctl(["list-timers", TIMER_UNIT_NAME, "--no-pager", "--all"])
    return ServiceStatus(
        service_path=service_unit_path(),
        timer_path=timer_unit_path(),
        service_installed=service_unit_path().exists(),
        timer_installed=timer_unit_path().exists(),
        timer_enabled=timer_enabled,
        timer_active=timer_active,
        service_active=service_active,
        list_timers=list_result.stdout if list_result.returncode == 0 else None,
    )


def run_systemctl(args: list[str]) -> SystemctlResult:
    """Run systemctl --user with captured output."""
    command = ["systemctl", "--user", *args]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return SystemctlResult(
        args=tuple(command),
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _run_systemctl_checked(args: list[str]) -> SystemctlResult:
    result = run_systemctl(args)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown systemctl failure"
        raise ServiceError(f"systemctl --user {' '.join(args)} failed: {detail}")
    return result


def _systemctl_bool(args: list[str]) -> bool | None:
    result = run_systemctl(args)
    if result.returncode == 0:
        return True
    output = (result.stdout + result.stderr).strip().lower()
    if any(word in output for word in ("disabled", "inactive", "unknown", "not-found")):
        return False
    return None


def _write_managed_unit(path: Path, text: str) -> None:
    if path.exists() and not _is_managed_unit(path):
        raise ServiceError(f"refusing to overwrite non-Moon-managed unit: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _remove_managed_unit(path: Path) -> bool:
    if not path.exists():
        return False
    if not _is_managed_unit(path):
        raise ServiceError(f"refusing to remove non-Moon-managed unit: {path}")
    path.unlink()
    return True


def _is_managed_unit(path: Path) -> bool:
    try:
        first_line = path.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except (OSError, IndexError):
        return False
    return first_line == MANAGED_HEADER
