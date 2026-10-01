"""Read-only status rendering for Moonlighter."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from moonlighter.budget import weekly_remaining_floor
from moonlighter.colors import BLUE, BOLD, CYAN, DIM, GREEN, MAGENTA, RED, YELLOW, style
from moonlighter.config import Config, default_state_dir
from moonlighter.projects import (
    BRIEF_PLACEHOLDER,
    ProjectError,
    ProjectState,
    brief_path,
    discover_projects,
    load_project_state,
    logs_dir,
    moon_dir,
    state_path,
    status_path,
)
from moonlighter.runtime_state import RuntimeStateError, load_global_state
from moonlighter.schedule import WorkStatus, evaluate_work_windows, format_duration


@dataclass(frozen=True)
class ProjectStatus:
    """Read-only status for one project."""

    name: str
    path: Path
    initialized: bool
    state: ProjectState | None = None
    needs_brief: bool = False
    error: str | None = None

    @property
    def section(self) -> str:
        """Return the global status section this project belongs in."""
        if not self.initialized:
            return "uninitialized"
        if self.error is not None:
            return "invalid"
        if self.state is None:
            return "invalid"
        if self.state.paused:
            return "paused"
        if self.needs_brief:
            return "needs brief"
        if self.state.disposition == "needs_direction":
            return "needs direction"
        if self.state.disposition in {"complete", "tabled"}:
            return "completed/tabled"
        return "active"


def render_global_status(
    config: Config, now: datetime | None = None, *, color: bool = False
) -> str:
    """Render read-only global Moonlighter status."""
    lines = [style("Moonlighter status", BOLD, CYAN, enabled=color), ""]

    try:
        global_state = load_global_state(default_state_dir())
        pause_text = "paused" if global_state.paused else "not paused"
        pause_color = RED if global_state.paused else GREEN
        lines.append(f"Global pause: {style(pause_text, pause_color, enabled=color)}")
    except RuntimeStateError as exc:
        lines.append(f"Global pause: {style(f'unknown ({exc})', RED, enabled=color)}")

    work_status = evaluate_work_windows(config.work_windows, now)
    lines.extend(_render_work_status(work_status, now, color=color))
    lines.extend(_render_runner_status(color=color))
    lines.append("")

    try:
        project_statuses = classify_projects(config.project_root)
    except ProjectError as exc:
        lines.append(f"Projects: unavailable ({exc})")
    else:
        for section in (
            "active",
            "paused",
            "needs brief",
            "needs direction",
            "completed/tabled",
            "uninitialized",
            "invalid",
        ):
            names = [status.name for status in project_statuses if status.section == section]
            if names:
                lines.append(style(f"{section.title()}:", *_section_style(section), enabled=color))
                lines.extend(f"  - {name}" for name in names)
        if not project_statuses:
            lines.append(f"Projects: {style('none', DIM, enabled=color)}")

    lines.append("")
    lines.extend(_render_last_known_budget(default_state_dir(), config=config, color=color))
    return "\n".join(lines).rstrip() + "\n"


def render_project_status(config: Config, project_name: str, *, color: bool = False) -> str:
    """Render read-only status for one project."""
    project_dir = config.project_root / project_name
    lines = [f"Project: {style(project_name, BOLD, CYAN, enabled=color)}", f"Path: {project_dir}"]

    if not project_dir.exists():
        lines.append(f"State: {style('missing', RED, enabled=color)}")
        return "\n".join(lines) + "\n"
    if not project_dir.is_dir():
        lines.append(f"State: {style('not a directory', RED, enabled=color)}")
        return "\n".join(lines) + "\n"
    if not moon_dir(project_dir).is_dir():
        lines.append(f"State: {style('uninitialized', YELLOW, enabled=color)}")
        return "\n".join(lines) + "\n"

    status = classify_project(project_dir)
    if status.error is not None:
        lines.append(f"State: {style(f'invalid ({status.error})', RED, enabled=color)}")
        return "\n".join(lines) + "\n"

    assert status.state is not None
    lines.append(f"State: {style('initialized', GREEN, enabled=color)}")
    disposition = style(
        status.state.disposition,
        *_disposition_style(status.state.disposition),
        enabled=color,
    )
    paused = style(
        "yes" if status.state.paused else "no",
        YELLOW if status.state.paused else GREEN,
        enabled=color,
    )
    needs_brief = style(
        "yes" if status.needs_brief else "no",
        YELLOW if status.needs_brief else GREEN,
        enabled=color,
    )
    lines.append(f"Disposition: {disposition}")
    lines.append(f"Paused: {paused}")
    lines.append(f"Needs brief: {needs_brief}")
    lines.append(f"Last run: {status.state.last_run_at or 'never'}")
    lines.append(f"Pi session ID: {status.state.pi_session_id or 'none'}")
    lines.append(f"Pi session file: {status.state.pi_session_file or 'none'}")
    lines.append(f"Last claimed from: {status.state.last_claimed_from or 'none'}")
    if status.state.disposition == "needs_direction":
        feedback = feedback_request_text(project_dir, status.state.disposition_summary)
        lines.append("")
        lines.append(style("Feedback requested:", BOLD, MAGENTA, enabled=color))
        for line in feedback.splitlines():
            lines.append(f"  {line}")
        lines.append(f"Edit guidance: moon brief {project_name}")

    summaries = recent_run_summaries(project_dir, limit=3)
    if summaries:
        lines.append("")
        lines.append(style("Recent runs:", BOLD, BLUE, enabled=color))
        lines.extend(f"  - {summary}" for summary in summaries)

    return "\n".join(lines) + "\n"


def classify_projects(project_root: Path) -> tuple[ProjectStatus, ...]:
    """Classify discovered projects for status output."""
    return tuple(classify_project(project.path) for project in discover_projects(project_root))


def classify_project(project_dir: Path) -> ProjectStatus:
    """Classify a project without mutating it."""
    initialized = moon_dir(project_dir).is_dir()
    if not initialized:
        return ProjectStatus(name=project_dir.name, path=project_dir, initialized=False)

    try:
        state = load_project_state(state_path(project_dir))
    except ProjectError as exc:
        return ProjectStatus(
            name=project_dir.name,
            path=project_dir,
            initialized=True,
            error=str(exc),
        )

    return ProjectStatus(
        name=project_dir.name,
        path=project_dir,
        initialized=True,
        state=state,
        needs_brief=brief_needs_replacement(project_dir),
    )


def feedback_request_text(project_dir: Path, disposition_summary: str | None) -> str:
    """Return user-facing feedback request text for a needs-direction project."""
    if disposition_summary:
        return disposition_summary
    parsed = _parse_feedback_from_status(project_dir)
    if parsed:
        return parsed
    return "See .moon/status.md for requested direction."


def _parse_feedback_from_status(project_dir: Path) -> str | None:
    path = status_path(project_dir)
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for index, line in enumerate(lines):
        normalized = line.strip().lower().rstrip(":")
        if normalized.startswith(("direction needed", "feedback requested")):
            collected: list[str] = []
            for following in lines[index + 1 :]:
                stripped = following.strip()
                if not stripped:
                    if collected:
                        break
                    continue
                if stripped.startswith("#"):
                    break
                if stripped.endswith(":") and collected:
                    break
                collected.append(stripped)
            if collected:
                return "\n".join(collected)
    return None


def _render_runner_status(*, color: bool) -> list[str]:
    containers = running_moon_containers()
    if not containers:
        return [f"Runner: {style('not running', DIM, enabled=color)}"]
    lines = [f"Runner: {style('running', GREEN, enabled=color)}"]
    for container in containers:
        project = container.get("project") or "unknown project"
        running_for = container.get("running_for") or "unknown duration"
        name = container.get("name") or "unknown container"
        lines.append(f"  - {project} ({running_for}, {name})")
    return lines


def running_moon_containers() -> tuple[dict[str, str], ...]:
    """Return running Moonlighter Docker containers, if Docker is available."""
    if shutil.which("docker") is None:
        return ()
    result = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            "label=moonlighter=true",
            "--format",
            "{{json .}}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ()

    containers: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        labels = _parse_docker_labels(str(row.get("Labels", "")))
        containers.append(
            {
                "project": labels.get("moonlighter.project", ""),
                "running_for": str(row.get("RunningFor", "")),
                "name": str(row.get("Names", "")),
            }
        )
    return tuple(containers)


def _parse_docker_labels(text: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    for part in text.split(","):
        key, separator, value = part.partition("=")
        if separator:
            labels[key.strip()] = value.strip()
    return labels


def _section_style(section: str) -> tuple[str, ...]:
    return {
        "active": (BOLD, GREEN),
        "paused": (BOLD, YELLOW),
        "needs brief": (BOLD, YELLOW),
        "needs direction": (BOLD, MAGENTA),
        "completed/tabled": (BOLD, BLUE),
        "uninitialized": (BOLD, DIM),
        "invalid": (BOLD, RED),
    }.get(section, (BOLD,))


def _disposition_style(disposition: str) -> tuple[str, ...]:
    return {
        "active": (GREEN,),
        "needs_direction": (MAGENTA,),
        "complete": (BLUE,),
        "tabled": (BLUE,),
    }.get(disposition, ())


def brief_needs_replacement(project_dir: Path) -> bool:
    """Return whether the project brief is missing or still placeholder-only."""
    path = brief_path(project_dir)
    if not path.exists():
        return True
    text = path.read_text(encoding="utf-8").strip()
    return text == "" or text == BRIEF_PLACEHOLDER.strip()


def recent_run_summaries(project_dir: Path, limit: int = 3) -> tuple[str, ...]:
    """Return terse summaries from the most recent project log files."""
    path = logs_dir(project_dir)
    if not path.is_dir():
        return ()

    summaries: list[str] = []
    files = sorted((entry for entry in path.iterdir() if entry.is_file()), reverse=True)
    for entry in files[:limit]:
        text = entry.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            summaries.append(entry.name)
            continue
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), entry.name)
        summaries.append(first_line[:120])
    return tuple(summaries)


def _render_work_status(work_status: WorkStatus, now: datetime | None, *, color: bool) -> list[str]:
    current_time = now or datetime.now().astimezone()
    lines: list[str] = []
    if work_status.is_work_time:
        if work_status.until is None:
            lines.append(f"Work window: {style('active', GREEN, enabled=color)}")
        else:
            duration = format_duration(work_status.until - current_time)
            lines.append(f"Work window: {style('active', GREEN, enabled=color)} for {duration}")
        return lines

    if work_status.until is None:
        inactive = style("inactive", YELLOW, enabled=color)
        lines.append(f"Work window: {inactive}; no upcoming window configured")
    else:
        duration = format_duration(work_status.until - current_time)
        lines.append(f"Work window: {style('inactive', YELLOW, enabled=color)} for {duration}")
        if work_status.next_window is not None:
            lines.append(
                "Next work window: "
                f"{work_status.next_window.start.strftime('%Y-%m-%d %H:%M')} "
                f"for {format_duration(work_status.next_window.duration)}"
            )
    return lines


def _render_last_known_budget(state_dir: Path, *, config: Config, color: bool) -> list[str]:
    status_path = state_dir / "status.json"
    if not status_path.exists():
        return [f"Last-known budget: {style('unknown', DIM, enabled=color)}"]

    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Last-known budget: {style(f'invalid ({exc})', RED, enabled=color)}"]

    if not isinstance(data, dict):
        return [f"Last-known budget: {style('invalid', RED, enabled=color)}"]

    budget = data.get("budget")
    target_gap = _weekly_target_gap(data, config)
    suffix = f" ({target_gap})" if target_gap is not None else ""
    if isinstance(budget, str):
        budget_color = GREEN if "allowed" in budget else YELLOW if "blocked" in budget else CYAN
        return [f"Last-known budget: {style(budget + suffix, budget_color, enabled=color)}"]
    if isinstance(budget, dict):
        rendered = json.dumps(budget, sort_keys=True) + suffix
        return [f"Last-known budget: {style(rendered, CYAN, enabled=color)}"]
    return [f"Last-known budget: {style('unknown', DIM, enabled=color)}"]


def _weekly_target_gap(data: dict[str, object], config: Config) -> str | None:
    details = data.get("budget_details")
    if not isinstance(details, dict):
        return None
    remaining = details.get("weekly_remaining_percent")
    reset_text = details.get("weekly_reset_at")
    checked_text = data.get("budget_checked_at")
    if not isinstance(remaining, int | float) or not isinstance(reset_text, str):
        return None
    try:
        reset_at = datetime.fromisoformat(reset_text)
        checked_at = datetime.fromisoformat(checked_text) if isinstance(checked_text, str) else None
    except ValueError:
        return None
    target = weekly_remaining_floor(
        config.budget.weekly_reserve_percent,
        reset_at,
        checked_at,
    )
    if target is None:
        return None
    gap = float(remaining) - target
    if gap >= 0:
        return f"{gap:.1f}% behind target"
    return f"{abs(gap):.1f}% past target"
