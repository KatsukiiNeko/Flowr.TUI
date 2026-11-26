"""Small box and layout helpers shared by the panel, help and editor."""

from __future__ import annotations

from typing import Optional

from ..render.buffer import CellBuffer
from ..text import display_width, fit, truncate


def draw_box(buffer: CellBuffer, x: int, y: int, width: int, height: int,
             title: str = "", color: Optional[int] = 244, title_color: Optional[int] = 231) -> None:
    if width < 2 or height < 2:
        return
    right = x + width - 1
    bottom = y + height - 1
    for row in range(y + 1, bottom):
        buffer.fill(row, x + 1, width - 2, " ", None)
    buffer.put(y, x, "+", color)
    buffer.put(y, right, "+", color)
    buffer.put(bottom, x, "+", color)
    buffer.put(bottom, right, "+", color)
    for col in range(x + 1, right):
        buffer.put(y, col, "-", color)
        buffer.put(bottom, col, "-", color)
    for row in range(y + 1, bottom):
        buffer.put(row, x, "|", color)
        buffer.put(row, right, "|", color)
    if title and width > 6:
        label = truncate(" " + title + " ", width - 4)
        buffer.put_text(y, x + 2, label, title_color, max_width=width - 4)


def draw_notice(buffer: CellBuffer, message: str, ascii_mode: bool = False,
                color: Optional[int] = 205) -> None:
    from ..text import ascii_text

    text = ascii_text(message) if ascii_mode else message
    lines = text.split("\n")
    width = min(buffer.cols - 2, max(display_width(line) for line in lines) + 4)
    height = len(lines) + 4
    x = max(0, (buffer.cols - width) // 2)
    y = max(0, (buffer.rows - height) // 2)
    draw_box(buffer, x, y, width, height, "Bouquet")
    for index, line in enumerate(lines):
        buffer.put_text(y + 2 + index, x + 2, truncate(line, width - 4), color,
                        max_width=width - 4)


def draw_confirm(buffer: CellBuffer, ascii_mode: bool = False) -> None:
    width = min(buffer.cols - 2, 52)
    height = 6
    x = max(0, (buffer.cols - width) // 2)
    y = max(0, (buffer.rows - height) // 2)
    draw_box(buffer, x, y, width, height, "Restore defaults")
    buffer.put_text(y + 2, x + 2, truncate("Restore every setting?", width - 4), 231,
                    max_width=width - 4)
    hint = "Enter confirms / Esc cancels" if ascii_mode else "Enter confirms \u00b7 Esc cancels"
    buffer.put_text(y + 3, x + 2, truncate(hint, width - 4), 244,
                    max_width=width - 4)
