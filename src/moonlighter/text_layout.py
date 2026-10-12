"""Terminal text widths and padding, ignoring ANSI styling."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def plain(text: str) -> str:
    return _ANSI.sub("", text)


def visible_width(text: str) -> int:
    return sum(
        0
        if unicodedata.combining(char) or unicodedata.category(char) == "Cf"
        else 2
        if unicodedata.east_asian_width(char) in ("W", "F")
        else 1
        for char in plain(text)
    )


def ellipsize(text: str, width: int) -> str:
    text = " ".join(plain(text).split())
    if visible_width(text) <= width:
        return text
    result = ""
    for char in text:
        if visible_width(result + char) > max(0, width - 1):
            break
        result += char
    return result.rstrip() + "…"


def render_table(headers: tuple[str, ...], rows: Sequence[tuple[str, ...]]) -> list[str]:
    widths = [
        max(visible_width(row[index]) for row in [headers, *rows]) for index in range(len(headers))
    ]
    widths[0] = max(16, widths[0])
    output = []
    for row in [headers, *rows]:
        cells = []
        for index, cell in enumerate(row):
            padding = " " * (widths[index] - visible_width(cell))
            cells.append(cell + padding if index == 0 else padding + cell)
        output.append("  ".join(cells).rstrip())
    return output
