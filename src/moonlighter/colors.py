"""Tiny ANSI color helpers for Moonlighter CLI output."""

from __future__ import annotations

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"


def outcome(status: str, *, enabled: bool) -> str:
    """Color only the outcome word; preserve readable text without ANSI support."""
    code = {
        "success": GREEN,
        "failed": RED,
        "skipped": YELLOW,
        "interrupted": YELLOW,
        "running": CYAN,
    }.get(status)
    return style(status, *([code] if code else []), enabled=enabled)


def style(text: str, *codes: str, enabled: bool) -> str:
    """Apply ANSI style codes when enabled."""
    if not enabled or not codes:
        return text
    return f"{''.join(codes)}{text}{RESET}"
