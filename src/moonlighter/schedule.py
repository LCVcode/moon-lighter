"""Work-window evaluation for Moonlighter status output."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from moonlighter.config import WorkWindow

DAY_INDEXES = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}


@dataclass(frozen=True)
class WindowSpan:
    """A concrete datetime span for one configured work window occurrence."""

    start: datetime
    end: datetime

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


@dataclass(frozen=True)
class WorkStatus:
    """Current work-window status."""

    is_work_time: bool
    until: datetime | None
    next_window: WindowSpan | None


def evaluate_work_windows(
    windows: tuple[WorkWindow, ...], now: datetime | None = None
) -> WorkStatus:
    """Evaluate current and next work-window status in local time."""
    current_time = now or datetime.now().astimezone()
    spans = tuple(_candidate_spans(windows, current_time))
    active = [span for span in spans if span.start <= current_time < span.end]

    if active:
        return WorkStatus(
            is_work_time=True,
            until=max(span.end for span in active),
            next_window=None,
        )

    upcoming = [span for span in spans if span.start > current_time]
    next_window = min(upcoming, key=lambda span: span.start, default=None)
    return WorkStatus(
        is_work_time=False,
        until=next_window.start if next_window is not None else None,
        next_window=next_window,
    )


def format_duration(delta: timedelta) -> str:
    """Format a timedelta tersely for humans."""
    total_minutes = max(0, int(delta.total_seconds() // 60))
    days, remainder = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remainder, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts)


def _candidate_spans(windows: tuple[WorkWindow, ...], now: datetime) -> list[WindowSpan]:
    spans: list[WindowSpan] = []
    for day_offset in range(-1, 8):
        date = (now + timedelta(days=day_offset)).date()
        weekday = date.weekday()
        for window in windows:
            if not _day_matches(window.days, weekday):
                continue
            start_time = _parse_time(window.start)
            end_time = _parse_time(window.end)
            start = datetime.combine(date, start_time, tzinfo=now.tzinfo)
            end = datetime.combine(date, end_time, tzinfo=now.tzinfo)
            if end <= start:
                end += timedelta(days=1)
            spans.append(WindowSpan(start=start, end=end))
    return spans


def _day_matches(days: str, weekday: int) -> bool:
    normalized = days.strip().lower()
    if normalized == "daily":
        return True
    if normalized == "weekdays":
        return weekday < 5
    if normalized == "weekends":
        return weekday >= 5

    day_values = {part.strip().lower() for part in normalized.replace(",", " ").split()}
    indexes = {DAY_INDEXES[part] for part in day_values if part in DAY_INDEXES}
    return weekday in indexes


def _parse_time(value: str) -> time:
    try:
        hour_text, minute_text = value.split(":", 1)
        return time(hour=int(hour_text), minute=int(minute_text))
    except ValueError as exc:
        raise ValueError(f"invalid time {value!r}; expected HH:MM") from exc
