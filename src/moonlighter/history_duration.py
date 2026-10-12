"""Elapsed work durations; preserve the scheduler's separate time-window formatting."""

from __future__ import annotations

from datetime import timedelta

from moonlighter.schedule import format_duration


def format_elapsed(seconds: float) -> str:
    seconds = max(0.0, seconds)
    if seconds == 0:
        return "0s"
    if seconds < 0.01:
        return "<0.01s"
    if seconds < 1:
        return f"{seconds:.2f}".rstrip("0").rstrip(".") + "s"
    if seconds < 60:
        return f"{int(seconds)}s"
    return format_duration(timedelta(seconds=seconds))
