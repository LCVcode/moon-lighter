"""Shared human-output policy; generated scripts/units never pass through this layer."""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Callable
from contextvars import ContextVar
from functools import wraps
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _typeshed import SupportsWrite

from moonlighter.colors import BLUE, BOLD, CYAN, DIM, GREEN, RED, YELLOW, style

_CHOICE: ContextVar[str] = ContextVar("moon_color", default="auto")
_ROLES = {
    "heading": (BOLD, CYAN),
    "info": (CYAN,),
    "success": (GREEN,),
    "warning": (YELLOW,),
    "error": (RED,),
    "hint": (DIM,),
}


def color_enabled(choice: str | None = None, *, stream: SupportsWrite[str] | None = None) -> bool:
    selected = choice or _CHOICE.get()
    if selected == "always":
        return True
    if selected == "never":
        return False
    return (
        "NO_COLOR" not in os.environ
        and os.environ.get("TERM") != "dumb"
        and bool(getattr(stream or sys.stdout, "isatty", lambda: False)())
    )


def paint(
    text: str,
    role: str = "info",
    *,
    enabled: bool | None = None,
    stream: SupportsWrite[str] | None = None,
) -> str:
    """Emphasize a label, keeping its value/path plain; hints are secondary throughout."""
    use_color = color_enabled(stream=stream) if enabled is None else enabled
    codes = _ROLES[role]
    if role == "hint":
        return style(text, *codes, enabled=use_color)
    label, separator, value = text.partition(": ")
    return style(label, *codes, enabled=use_color) + separator + value


def labelled(text: str, *, enabled: bool) -> str:
    """Decorate field labels, not prose, paths, timestamps, or pre-styled prefixes."""

    def replace(match: re.Match[str]) -> str:
        prefix, label = match.groups()
        kind = label.lower().rstrip(":")
        role = (
            "error"
            if kind == "error"
            else ("warning" if kind in {"stopped", "history incomplete", "warning"} else "info")
        )
        return prefix + paint(label, role, enabled=enabled)

    return re.sub(
        r"(^[ \t│├└─]*|(?<= · ))([A-Za-z][A-Za-z /()_-]*:)", replace, text, flags=re.MULTILINE
    )


def paint_priority(priority: str, *, enabled: bool | None = None) -> str:
    codes = {
        "urgent": (BOLD, RED),
        "high": (YELLOW,),
        "normal": (CYAN,),
        "low": (BLUE,),
        "backlog": (DIM,),
    }.get(priority, ())
    return style(priority, *codes, enabled=color_enabled() if enabled is None else enabled)


def selected_color(argv: list[str]) -> str:
    choice = "auto"
    for index, item in enumerate(argv):
        if item == "--":
            break
        value = (
            item.partition("=")[2]
            if item.startswith("--color=")
            else (argv[index + 1] if item == "--color" and index + 1 < len(argv) else "")
        )
        if value in {"auto", "always", "never"}:
            choice = value
    return choice


def command_colors(
    command: Callable[[list[str] | None], None],
) -> Callable[[list[str] | None], None]:
    """Scope policy to one invocation, including help and parse errors; never leak to the next."""

    @wraps(command)
    def wrapped(argv: list[str] | None = None) -> None:
        token = _CHOICE.set(selected_color(sys.argv[1:] if argv is None else argv))
        try:
            command(argv)
        finally:
            _CHOICE.reset(token)

    return wrapped


class CliArgumentParser(argparse.ArgumentParser):
    """Inheritable --color on every command, without overwriting ancestor choices."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Python 3.14's native help colors must not bypass Moon's --color policy.
        self.color = False
        self.add_argument(
            "--color",
            choices=("auto", "always", "never"),
            default=argparse.SUPPRESS,
            help="ANSI colors: auto (TTY only), always, or never.",
        )

    def _print_message(self, message: str, file: SupportsWrite[str] | None = None) -> None:
        if message:
            stream = file or sys.stderr
            if "error:" in message and stream is sys.stderr:
                prefix, separator, detail = message.partition("error:")
                message = (
                    style(prefix + separator, RED, enabled=color_enabled(stream=stream)) + detail
                )
            elif message.startswith("usage:"):
                lines = []
                for line in message.splitlines(keepends=True):
                    if line.startswith("usage:"):
                        line = paint(line, "info", stream=stream)
                    elif line.rstrip().endswith(":") and not line.startswith(" "):
                        line = paint(line, "heading", stream=stream)
                    lines.append(line)
                message = "".join(lines)
        super()._print_message(message, file)
