from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from moonlighter.config import WorkWindow
from moonlighter.schedule import evaluate_work_windows, format_duration

UTC = ZoneInfo("UTC")


def test_daily_window_active() -> None:
    status = evaluate_work_windows(
        (WorkWindow(days="daily", start="09:00", end="17:00"),),
        now=datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
    )

    assert status.is_work_time is True
    assert status.until == datetime(2026, 1, 5, 17, 0, tzinfo=UTC)


def test_next_window_when_inactive() -> None:
    status = evaluate_work_windows(
        (WorkWindow(days="weekdays", start="09:00", end="17:00"),),
        now=datetime(2026, 1, 3, 10, 0, tzinfo=UTC),
    )

    assert status.is_work_time is False
    assert status.next_window is not None
    assert status.next_window.start == datetime(2026, 1, 5, 9, 0, tzinfo=UTC)


def test_overnight_window_active_after_midnight() -> None:
    status = evaluate_work_windows(
        (WorkWindow(days="daily", start="22:00", end="02:00"),),
        now=datetime(2026, 1, 6, 1, 0, tzinfo=UTC),
    )

    assert status.is_work_time is True
    assert status.until == datetime(2026, 1, 6, 2, 0, tzinfo=UTC)


def test_overlapping_windows_extend_until_latest_end() -> None:
    status = evaluate_work_windows(
        (
            WorkWindow(days="daily", start="09:00", end="11:00"),
            WorkWindow(days="daily", start="10:00", end="12:00"),
        ),
        now=datetime(2026, 1, 5, 10, 30, tzinfo=UTC),
    )

    assert status.is_work_time is True
    assert status.until == datetime(2026, 1, 5, 12, 0, tzinfo=UTC)


def test_format_duration() -> None:
    assert format_duration(timedelta(days=1, hours=2, minutes=3)) == "1d 2h 3m"
