"""Moonlighter command-line entry point."""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import argcomplete

from moonlighter.budget import check_budget
from moonlighter.config import (
    Config,
    ConfigCheckResult,
    check_config,
    default_config_path,
    default_state_dir,
    write_sample_config,
)
from moonlighter.config import (
    load_config as load_config_no_validation,
)
from moonlighter.projects import (
    PRIORITY_TIERS,
    Priority,
    ProjectError,
    activate_project_state,
    brief_path,
    discover_projects,
    initialize_project,
    load_project_state,
    set_project_claim_source,
    set_project_paused,
    set_project_priority,
    state_path,
)
from moonlighter.run_history import (
    RunHistoryError,
    filter_run_records,
    read_run_records,
    render_run_log,
)
from moonlighter.runtime_state import RuntimeStateError, set_global_paused
from moonlighter.service import (
    DEFAULT_INTERVAL,
    ServiceError,
    disable_timer,
    enable_timer,
    install_units,
    read_service_status,
    reload_systemd_user,
    render_units,
    resolve_moon_executable,
    uninstall_units,
)
from moonlighter.status import render_global_status, render_project_status
from moonlighter.tick import TickError, run_tick

_VERSION = "0.1.0"


class CliError(ValueError):
    """Raised for user-facing command errors."""


def complete_project_names(prefix: str, **_kwargs: object) -> list[str]:
    """Complete configured project directory names without side effects."""
    try:
        config = load_config_no_validation()
    except (OSError, ValueError):
        return []
    root = config.project_root
    if not root.is_dir():
        return []
    return sorted(
        entry.name for entry in root.iterdir() if entry.is_dir() and entry.name.startswith(prefix)
    )


def add_project_completer(action: argparse.Action) -> None:
    """Attach the argcomplete project-name completer to an argparse action."""
    cast(Any, action).completer = complete_project_names


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level Moonlighter argument parser."""
    parser = argparse.ArgumentParser(
        prog="moon",
        description="Use surplus Codex budget to advance side projects during work windows.",
    )
    parser.add_argument("--version", action="version", version=f"moon {_VERSION}")

    subcommands = parser.add_subparsers(dest="command")

    config_parser = subcommands.add_parser("config", help="Manage Moonlighter configuration.")
    config_subcommands = config_parser.add_subparsers(dest="config_command")
    config_subcommands.add_parser("init", help="Create a sample config if one does not exist.")
    config_subcommands.add_parser("check", help="Validate the current config.")

    completion_parser = subcommands.add_parser(
        "completion", help="Print shell completion setup code."
    )
    completion_parser.add_argument("shell", choices=("bash", "zsh", "fish"))

    setup_parser = subcommands.add_parser("setup", help="Set up Moonlighter integrations.")
    setup_subcommands = setup_parser.add_subparsers(dest="setup_command")
    setup_completion = setup_subcommands.add_parser(
        "completion", help="Install shell completion in your shell startup file."
    )
    setup_completion.add_argument("--shell", choices=("bash", "zsh", "fish"))
    setup_completion.add_argument(
        "--yes", action="store_true", help="Modify files without prompting."
    )
    setup_completion.add_argument(
        "--print", action="store_true", help="Print the shell startup snippet without installing."
    )

    service_parser = subcommands.add_parser("service", help="Manage user systemd service/timer.")
    service_subcommands = service_parser.add_subparsers(dest="service_command")
    service_print = service_subcommands.add_parser("print", help="Print generated systemd units.")
    service_print.add_argument("--unit", choices=("service", "timer", "both"), default="both")
    service_print.add_argument("--interval", default=DEFAULT_INTERVAL)
    service_print.add_argument("--moon", help="Absolute path to moon executable for ExecStart.")
    service_install = service_subcommands.add_parser(
        "install", help="Install user systemd units without enabling them."
    )
    service_install.add_argument("--interval", default=DEFAULT_INTERVAL)
    service_install.add_argument("--moon", help="Absolute path to moon executable for ExecStart.")
    service_install.add_argument(
        "--print", action="store_true", help="Preview generated units without writing files."
    )
    service_subcommands.add_parser("enable", help="Enable and start the user systemd timer.")
    service_subcommands.add_parser("disable", help="Disable and stop the user systemd timer.")
    service_subcommands.add_parser("status", help="Show Moonlighter user systemd status.")
    service_subcommands.add_parser("uninstall", help="Remove Moon-managed user systemd units.")

    init_parser = subcommands.add_parser(
        "init", help="Initialize a project under the project root."
    )
    init_parser.add_argument("project", help="Project directory name under the configured root.")

    claim_parser = subcommands.add_parser(
        "claim", help="Move an existing project into Moon control."
    )
    claim_parser.add_argument("path", help="Project directory to move into the configured root.")

    release_parser = subcommands.add_parser("release", help="Move a project out of Moon control.")
    release_project_arg = release_parser.add_argument(
        "project", help="Project directory name under the configured root."
    )
    add_project_completer(release_project_arg)
    release_parser.add_argument(
        "dest",
        nargs="?",
        help="Destination path. Defaults to the project's recorded claim source path.",
    )

    activate_parser = subcommands.add_parser("activate", help="Reactivate a project.")
    activate_project_arg = activate_parser.add_argument(
        "project", help="Project directory name under the configured root."
    )
    add_project_completer(activate_project_arg)

    brief_parser = subcommands.add_parser("brief", help="Open a project's Moon brief in $EDITOR.")
    brief_project_arg = brief_parser.add_argument(
        "project", help="Project directory name under the configured root."
    )
    add_project_completer(brief_project_arg)

    priority_parser = subcommands.add_parser("priority", help="View or set project priority.")
    priority_project_arg = priority_parser.add_argument(
        "project", nargs="?", help="Optional project directory name."
    )
    add_project_completer(priority_project_arg)
    priority_parser.add_argument(
        "priority",
        nargs="?",
        choices=PRIORITY_TIERS,
        help="Priority tier: urgent, high, normal, low, or backlog.",
    )

    pause_parser = subcommands.add_parser("pause", help="Pause all work or one project.")
    pause_project_arg = pause_parser.add_argument(
        "project", nargs="?", help="Optional project directory name."
    )
    add_project_completer(pause_project_arg)

    resume_parser = subcommands.add_parser("resume", help="Resume all work or one project.")
    resume_project_arg = resume_parser.add_argument(
        "project", nargs="?", help="Optional project directory name."
    )
    add_project_completer(resume_project_arg)

    status_parser = subcommands.add_parser("status", help="Show Moonlighter status.")
    status_project_arg = status_parser.add_argument(
        "project", nargs="?", help="Optional project directory name."
    )
    add_project_completer(status_project_arg)
    status_parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="Colorize status output.",
    )

    log_parser = subcommands.add_parser("log", help="Show recent Moonlighter run history.")
    log_parser.add_argument("--limit", type=int, default=20, help="Maximum records to show.")
    log_project_arg = log_parser.add_argument("--project", help="Only show runs for a project.")
    add_project_completer(log_project_arg)
    log_parser.add_argument("--status", choices=("skipped", "success", "failed"))
    log_parser.add_argument(
        "--all",
        action="store_true",
        help="Include low-signal scheduler no-ops where moon work skipped before chunks.",
    )

    run_parser = subcommands.add_parser("run", help="Manually run one work chunk now.")
    run_project_arg = run_parser.add_argument(
        "project", nargs="?", help="Optional project directory name."
    )
    add_project_completer(run_project_arg)
    run_parser.add_argument(
        "--chunk-minutes",
        type=int,
        help="Override this manual chunk's maximum duration in minutes.",
    )
    run_parser.add_argument(
        "--ignore-budget",
        action="store_true",
        help="Bypass the budget gate for this manual chunk.",
    )

    work_parser = subcommands.add_parser("work", help="Run scheduled Moonlighter work if allowed.")
    work_parser.add_argument(
        "--force",
        action="store_true",
        help="Run one chunk ignoring pause and work-window gates.",
    )
    work_parser.add_argument(
        "--ignore-budget",
        action="store_true",
        help="With --force, also bypass the budget gate.",
    )
    work_project_arg = work_parser.add_argument(
        "--project", help="Run or select a specific project name."
    )
    add_project_completer(work_project_arg)
    work_parser.add_argument("--minutes", type=int, help="Override chunk duration in minutes.")

    return parser


def print_config_check(result: ConfigCheckResult) -> None:
    """Print a human-readable config-check result."""
    print(f"Config: {result.config_path}")
    if result.config is not None:
        print(f"Project root: {result.config.project_root}")
        print(
            "Runner: "
            f"{result.config.runner.provider} / {result.config.runner.model} "
            f"({result.config.runner.thinking})"
        )
        print(f"Runner image: {result.config.runner.image}")

    if not result.issues:
        print("OK: config looks good.")
        return

    for issue in result.issues:
        label = "ERROR" if issue.severity == "error" else "WARNING"
        print(f"{label}: {issue.message}")

    if result.has_errors:
        print("Config check failed.")
    elif result.has_warnings:
        print("Config check passed with warnings.")


def handle_completion(shell: str) -> int:
    """Print shell completion setup code."""
    print(argcomplete.shellcode(["moon"], shell=shell), end="")
    return 0


COMPLETION_BLOCK_START = "# >>> moon completion >>>"
COMPLETION_BLOCK_END = "# <<< moon completion <<<"


def detect_shell() -> str:
    """Detect the user's likely interactive shell."""
    shell = Path(os.environ.get("SHELL", "")).name
    if shell in {"bash", "zsh", "fish"}:
        return shell
    return "bash"


def completion_startup_path(shell: str) -> Path:
    """Return the shell startup file used for Moon completion setup."""
    if shell == "zsh":
        return Path.home() / ".zshrc"
    if shell == "fish":
        return Path.home() / ".config" / "fish" / "config.fish"
    return Path.home() / ".bashrc"


def completion_startup_snippet(shell: str) -> str:
    """Return the managed shell startup snippet for completions."""
    if shell == "fish":
        body = "moon completion fish | source"
    else:
        body = f'eval "$(moon completion {shell})"'
    return f"{COMPLETION_BLOCK_START}\n{body}\n{COMPLETION_BLOCK_END}\n"


def install_completion(shell: str, path: Path, *, assume_yes: bool) -> bool:
    """Install the managed completion snippet. Return True if the file changed."""
    snippet = completion_startup_snippet(shell)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if COMPLETION_BLOCK_START in existing and COMPLETION_BLOCK_END in existing:
        return False
    if not assume_yes:
        response = input(f"Append Moon completion setup to {path}? [y/N] ")
        if response.strip().lower() not in {"y", "yes"}:
            raise CliError("completion setup cancelled")
    path.parent.mkdir(parents=True, exist_ok=True)
    separator = "" if not existing or existing.endswith("\n") else "\n"
    path.write_text(f"{existing}{separator}{snippet}", encoding="utf-8")
    return True


def handle_setup(command: str | None, shell: str | None, assume_yes: bool, print_only: bool) -> int:
    """Handle `moon setup ...` commands."""
    if command != "completion":
        print("Usage: moon setup completion [--shell {bash,zsh,fish}] [--yes] [--print]")
        return 2
    selected_shell = shell or detect_shell()
    snippet = completion_startup_snippet(selected_shell)
    if print_only:
        print(snippet, end="")
        return 0
    path = completion_startup_path(selected_shell)
    changed = install_completion(selected_shell, path, assume_yes=assume_yes)
    if changed:
        print(f"Installed Moon completion for {selected_shell}: {path}")
        print("Restart your shell or source the file to activate completion.")
    else:
        print(f"Moon completion already installed in {path}")
    return 0


def handle_service(
    command: str | None,
    *,
    unit: str = "both",
    interval: str = DEFAULT_INTERVAL,
    moon_path: str | None = None,
    print_only: bool = False,
) -> int:
    """Handle `moon service ...`."""
    if command is None:
        print("Usage: moon service {print,install,enable,disable,status,uninstall}")
        return 2

    if command == "print":
        service_text, timer_text = render_units(resolve_moon_executable(moon_path), interval)
        print_service_units(service_text, timer_text, unit)
        return 0

    if command == "install":
        moon_executable = resolve_moon_executable(moon_path)
        service_text, timer_text = render_units(moon_executable, interval)
        if print_only:
            print_service_units(service_text, timer_text, "both")
            return 0
        service_path, timer_path = install_units(moon_executable, interval)
        reload_systemd_user()
        print(f"Installed service: {service_path}")
        print(f"Installed timer: {timer_path}")
        print("Timer is not enabled. Run `moon service enable` to start scheduled work.")
        return 0

    if command == "enable":
        enable_timer()
        print("Enabled Moonlighter timer.")
        return 0

    if command == "disable":
        disable_timer()
        print("Disabled Moonlighter timer.")
        return 0

    if command == "status":
        print(format_service_status(), end="")
        return 0

    if command == "uninstall":
        try:
            disable_timer()
        except ServiceError as exc:
            print(f"Warning: {exc}", file=sys.stderr)
        service_removed, timer_removed = uninstall_units()
        reload_systemd_user()
        if service_removed:
            print("Removed moon.service.")
        if timer_removed:
            print("Removed moon.timer.")
        if not service_removed and not timer_removed:
            print("No Moonlighter systemd units were installed.")
        return 0

    print("Usage: moon service {print,install,enable,disable,status,uninstall}")
    return 2


def print_service_units(service_text: str, timer_text: str, unit: str) -> None:
    """Print selected generated systemd unit text."""
    if unit in {"service", "both"}:
        print("# moon.service")
        print(service_text, end="")
    if unit == "both":
        print()
    if unit in {"timer", "both"}:
        print("# moon.timer")
        print(timer_text, end="")


def format_service_status() -> str:
    """Format user systemd service status."""
    status = read_service_status()
    lines = ["Moonlighter service", ""]
    lines.append(f"Service unit: {status.service_path}")
    lines.append(f"  installed: {_yes_no(status.service_installed)}")
    lines.append(f"  active: {_yes_no_unknown(status.service_active)}")
    lines.append(f"Timer unit: {status.timer_path}")
    lines.append(f"  installed: {_yes_no(status.timer_installed)}")
    lines.append(f"  enabled: {_yes_no_unknown(status.timer_enabled)}")
    lines.append(f"  active: {_yes_no_unknown(status.timer_active)}")
    if status.list_timers:
        lines.append("")
        lines.append("systemctl --user list-timers:")
        lines.extend(f"  {line}" for line in status.list_timers.rstrip().splitlines())
    return "\n".join(lines).rstrip() + "\n"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _yes_no_unknown(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return _yes_no(value)


def handle_config(command: str | None) -> int:
    """Handle `moon config ...` commands."""
    if command == "init":
        path = default_config_path()
        existed = path.exists()
        written_path = write_sample_config(path)
        if existed:
            print(f"Config already exists: {written_path}")
            print_config_check(check_config(written_path))
        else:
            print(f"Wrote sample config: {written_path}")
            print(
                "Edit this file, create the configured project root, then run `moon config check`."
            )
        return 0

    if command == "check":
        result = check_config()
        print_config_check(result)
        return 1 if result.has_errors else 0

    print("Usage: moon config {init,check}")
    return 2


def load_valid_config() -> Config:
    """Load configured Moonlighter settings, failing on validation errors."""
    result = check_config()
    if result.has_errors or result.config is None:
        messages = "; ".join(issue.message for issue in result.issues if issue.severity == "error")
        raise CliError(messages or "config check failed")
    return result.config


def resolve_project_dir(config: Config, project_name: str) -> Path:
    """Resolve a CLI project argument to a path under the configured project root."""
    project_path = Path(project_name)
    if (
        project_path.is_absolute()
        or project_path.name != project_name
        or project_name in {"", ".", ".."}
    ):
        raise CliError(
            f"project must be a directory name under {config.project_root}: {project_name!r}"
        )
    return config.project_root / project_name


def handle_init(project_name: str) -> int:
    """Handle `moon init <project>`."""
    config = load_valid_config()
    config.project_root.mkdir(parents=True, exist_ok=True)
    project_dir = resolve_project_dir(config, project_name)
    initialize_project(project_dir)
    open_editor_for_brief(project_dir)
    print(f"Initialized project: {project_dir}")
    return 0


def open_editor_for_brief(project_dir: Path, *, required: bool = False) -> bool:
    """Open $EDITOR on the project's brief when configured."""
    editor = os.environ.get("EDITOR")
    if not editor:
        if required:
            raise CliError(
                "$EDITOR is not set. Set EDITOR or open this file manually: "
                f"{brief_path(project_dir)}"
            )
        return False
    command = [*shlex.split(editor), str(brief_path(project_dir))]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise CliError(f"editor exited with status {result.returncode}: {editor}")
    return True


def handle_brief(project_name: str) -> int:
    """Handle `moon brief <project>`."""
    config = load_valid_config()
    project_dir = resolve_project_dir(config, project_name)
    if not project_dir.exists():
        raise CliError(f"project does not exist: {project_dir}")
    initialize_project(project_dir)
    open_editor_for_brief(project_dir, required=True)
    print(f"Brief: {brief_path(project_dir)}")
    return 0


def handle_claim(path_text: str) -> int:
    """Handle `moon claim <path>`."""
    config = load_valid_config()
    config.project_root.mkdir(parents=True, exist_ok=True)

    source = Path(path_text).expanduser().resolve(strict=False)
    if not source.exists():
        raise CliError(f"claim source does not exist: {source}")
    if not source.is_dir():
        raise CliError(f"claim source is not a directory: {source}")

    destination = config.project_root / source.name
    if destination.exists():
        raise CliError(f"cannot claim {source}: project already exists at {destination}")

    shutil.move(str(source), str(destination))
    try:
        initialize_project(destination)
        set_project_claim_source(destination, source)
    except Exception:
        if destination.exists() and not source.exists():
            shutil.move(str(destination), str(source))
        raise

    print(f"Claimed project: {destination}")
    print(f"Recorded claim source: {source}")
    return 0


def handle_release(project_name: str, dest_text: str | None) -> int:
    """Handle `moon release <project> [dest]`."""
    config = load_valid_config()
    project_dir = resolve_project_dir(config, project_name)
    if not project_dir.exists():
        raise CliError(f"project does not exist: {project_dir}")
    if not project_dir.is_dir():
        raise CliError(f"project path is not a directory: {project_dir}")

    if dest_text is None:
        state = load_project_state(state_path(project_dir))
        if state.last_claimed_from is None:
            raise CliError(
                "release destination was not provided and this project has no recorded "
                f"claim source. Re-run with: moon release {project_name} <dest>"
            )
        destination = Path(state.last_claimed_from).expanduser()
    else:
        destination = Path(dest_text).expanduser()

    destination = destination.resolve(strict=False)
    if destination.exists() and destination.is_dir() and dest_text is not None:
        destination = destination / project_name
    if destination.exists():
        raise CliError(f"cannot release {project_name}: destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    shutil.move(str(project_dir), str(destination))
    print(f"Released project: {destination}")
    return 0


def handle_activate(project_name: str) -> int:
    """Handle `moon activate <project>`."""
    config = load_valid_config()
    config.project_root.mkdir(parents=True, exist_ok=True)
    project_dir = resolve_project_dir(config, project_name)
    initialize_project(project_dir)
    activate_project_state(project_dir)
    print(f"Activated project: {project_dir}")
    return 0


def handle_priority(project_name: str | None, priority: str | None) -> int:
    """Handle `moon priority [project] [priority]`."""
    config = load_valid_config()
    if project_name is None:
        if priority is not None:
            raise CliError("priority requires a project name")
        print(render_priority_list(config))
        return 0

    project_dir = resolve_project_dir(config, project_name)
    if not project_dir.exists():
        raise CliError(f"project does not exist: {project_dir}")
    if not project_dir.is_dir():
        raise CliError(f"project path is not a directory: {project_dir}")
    if not (project_dir / ".moon").is_dir():
        raise CliError(f"project is not initialized: {project_dir}")

    if priority is None:
        state = load_project_state(state_path(project_dir))
        print(f"{project_name}: {state.priority}")
        return 0

    set_project_priority(project_dir, cast(Priority, priority))
    print(f"Priority set: {project_name} -> {priority}")
    return 0


def render_priority_list(config: Config) -> str:
    """Render initialized projects grouped by priority tier."""
    grouped: dict[str, list[str]] = {priority: [] for priority in PRIORITY_TIERS}
    invalid: list[str] = []
    uninitialized: list[str] = []
    for project in discover_projects(config.project_root):
        if not project.initialized:
            uninitialized.append(project.name)
            continue
        try:
            state = load_project_state(state_path(project.path))
        except ProjectError:
            invalid.append(project.name)
            continue
        grouped[state.priority].append(project.name)

    lines = ["Priorities", ""]
    for priority in PRIORITY_TIERS:
        lines.append(f"{priority}:")
        names = sorted(grouped[priority])
        if names:
            lines.extend(f"  - {name}" for name in names)
        else:
            lines.append("  none")
        lines.append("")
    if uninitialized:
        lines.append("uninitialized:")
        lines.extend(f"  - {name}" for name in sorted(uninitialized))
        lines.append("")
    if invalid:
        lines.append("invalid:")
        lines.extend(f"  - {name}" for name in sorted(invalid))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def handle_log(limit: int, project: str | None, status: str | None, include_all: bool) -> int:
    """Handle `moon log`."""
    if limit <= 0:
        raise CliError("--limit must be greater than zero")
    records = read_run_records(default_state_dir())
    filtered = filter_run_records(
        records,
        limit=limit,
        project=project,
        status=status,
        include_timer_noops=include_all,
    )
    print(render_run_log(filtered), end="")
    return 0


def handle_run(project_name: str | None, chunk_minutes: int | None, ignore_budget: bool) -> int:
    """Handle `moon run`."""
    if chunk_minutes is not None and chunk_minutes <= 0:
        raise CliError("--chunk-minutes must be greater than zero")
    config = load_valid_config()
    if project_name is not None:
        resolve_project_dir(config, project_name)
    result = run_tick(
        config,
        force=True,
        ignore_budget=ignore_budget,
        project_name=project_name,
        chunk_minutes=chunk_minutes,
        update_budget_after_chunk=True,
        entrypoint="run",
    )
    if result.skipped_reason is not None:
        print(f"moon run skipped: {result.skipped_reason}")
    return result.exit_code


def handle_tick(
    force: bool, ignore_budget: bool, project_name: str | None, minutes: int | None
) -> int:
    """Handle `moon work`."""
    if minutes is not None and minutes <= 0:
        raise CliError("--minutes must be greater than zero")
    if ignore_budget and not force:
        raise CliError("--ignore-budget requires --force")
    config = load_valid_config()
    if project_name is not None:
        resolve_project_dir(config, project_name)
    result = run_tick(
        config,
        force=force,
        ignore_budget=ignore_budget,
        project_name=project_name,
        chunk_minutes=minutes,
        update_budget_after_chunk=True,
        entrypoint="work",
    )
    if result.skipped_reason is not None:
        print(f"moon work skipped: {result.skipped_reason}")
    return result.exit_code


def should_color(choice: str) -> bool:
    """Return whether CLI output should use ANSI color."""
    if choice == "always":
        return True
    if choice == "never":
        return False
    return sys.stdout.isatty()


def handle_status(project_name: str | None, color_choice: str = "auto") -> int:
    """Handle status commands, refreshing budget before rendering."""
    config = load_valid_config()
    check_budget(config)
    color = should_color(color_choice)
    if project_name is None:
        print(render_global_status(config, color=color), end="")
    else:
        resolved = resolve_project_dir(config, project_name)
        print(render_project_status(config, resolved.name, color=color), end="")
    return 0


def handle_pause_resume(project_name: str | None, paused: bool) -> int:
    """Handle global or per-project pause/resume commands."""
    action = "Paused" if paused else "Resumed"
    if project_name is None:
        set_global_paused(default_state_dir(), paused)
        print(f"{action} Moonlighter.")
        return 0

    config = load_valid_config()
    project_dir = resolve_project_dir(config, project_name)
    if not project_dir.exists():
        raise CliError(f"project does not exist: {project_dir}")
    initialize_project(project_dir)
    if paused:
        set_project_paused(project_dir, True)
    else:
        activate_project_state(project_dir)
    print(f"{action} project: {project_dir}")
    return 0


def normalize_command_aliases(argv: list[str] | None) -> list[str] | None:
    """Map hidden/deprecated command aliases before argparse validation."""
    args = sys.argv[1:] if argv is None else list(argv)
    if args and args[0] in {"light", "tick"}:
        args[0] = "work"
    return args


def main(argv: list[str] | None = None) -> None:
    """Run the Moonlighter CLI."""
    parser = build_parser()
    argcomplete.autocomplete(parser)
    args = parser.parse_args(normalize_command_aliases(argv))

    try:
        exit_code = 0
        if args.command is None:
            parser.print_help()
        elif args.command == "config":
            exit_code = handle_config(args.config_command)
        elif args.command == "completion":
            exit_code = handle_completion(args.shell)
        elif args.command == "setup":
            exit_code = handle_setup(
                args.setup_command,
                getattr(args, "shell", None),
                getattr(args, "yes", False),
                getattr(args, "print", False),
            )
        elif args.command == "service":
            exit_code = handle_service(
                args.service_command,
                unit=getattr(args, "unit", "both"),
                interval=getattr(args, "interval", DEFAULT_INTERVAL),
                moon_path=getattr(args, "moon", None),
                print_only=getattr(args, "print", False),
            )
        elif args.command == "init":
            exit_code = handle_init(args.project)
        elif args.command == "claim":
            exit_code = handle_claim(args.path)
        elif args.command == "release":
            exit_code = handle_release(args.project, args.dest)
        elif args.command == "activate":
            exit_code = handle_activate(args.project)
        elif args.command == "brief":
            exit_code = handle_brief(args.project)
        elif args.command == "priority":
            exit_code = handle_priority(args.project, args.priority)
        elif args.command == "pause":
            exit_code = handle_pause_resume(args.project, paused=True)
        elif args.command == "resume":
            exit_code = handle_pause_resume(args.project, paused=False)
        elif args.command == "status":
            exit_code = handle_status(args.project, args.color)
        elif args.command == "log":
            exit_code = handle_log(args.limit, args.project, args.status, args.all)
        elif args.command == "run":
            exit_code = handle_run(args.project, args.chunk_minutes, args.ignore_budget)
        elif args.command == "work":
            exit_code = handle_tick(args.force, args.ignore_budget, args.project, args.minutes)
        else:
            parser.error(f"unknown command: {args.command}")
    except (
        CliError,
        ProjectError,
        RunHistoryError,
        RuntimeStateError,
        ServiceError,
        TickError,
    ) as exc:
        parser.exit(1, f"moon: error: {exc}\n")

    if exit_code:
        raise SystemExit(exit_code)
