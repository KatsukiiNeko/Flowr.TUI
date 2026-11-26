"""A terminal-independent cell buffer.

Characters with a display width of two occupy a cell plus a continuation cell
(char ``""``).  Colors may be ``None`` (terminal default), an ``int`` xterm-256
index, or an ``(r, g, b)`` truecolor tuple.  Background colors are ``None`` by
default and only populated when explicitly needed (e.g. half-block style).
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from ..flowers.colorways import ColorValue
from ..text import cells, display_width


class CellBuffer:
    __slots__ = ("cols", "rows", "chars", "colors", "bg_colors", "zbuf")

    def __init__(self, cols: int, rows: int) -> None:
        self.cols = max(1, cols)
        self.rows = max(1, rows)
        self.chars: List[List[str]] = [[" "] * self.cols for _ in range(self.rows)]
        self.colors: List[List[ColorValue]] = [[None] * self.cols for _ in range(self.rows)]
        self.bg_colors: List[List[ColorValue]] = [[None] * self.cols for _ in range(self.rows)]
        self.zbuf: List[List[float]] = [[-1e9] * self.cols for _ in range(self.rows)]

    def clear(self) -> None:
        self.chars = [[" "] * self.cols for _ in range(self.rows)]
        self.colors = [[None] * self.cols for _ in range(self.rows)]
        self.bg_colors = [[None] * self.cols for _ in range(self.rows)]
        self.zbuf = [[-1e9] * self.cols for _ in range(self.rows)]

    def plot(
        self,
        col: int,
        row: int,
        z: float,
        ch: str,
        color: ColorValue,
        bg: ColorValue = None,
    ) -> None:
        if 0 <= row < self.rows and 0 <= col < self.cols and z > self.zbuf[row][col]:
            self.zbuf[row][col] = z
            self.chars[row][col] = ch
            self.colors[row][col] = color
            self.bg_colors[row][col] = bg

    def put(
        self,
        row: int,
        col: int,
        ch: str,
        color: ColorValue,
        bg: ColorValue = None,
    ) -> None:
        if 0 <= row < self.rows and 0 <= col < self.cols:
            self.chars[row][col] = ch
            self.colors[row][col] = color
            self.bg_colors[row][col] = bg

    def put_text(
        self,
        row: int,
        col: int,
        text: str,
        color: ColorValue,
        max_width: Optional[int] = None,
    ) -> int:
        """Write text; returns the column after the last written cell."""
        if not 0 <= row < self.rows:
            return col
        limit = self.cols if max_width is None else min(self.cols, col + max(0, max_width))
        cursor = col
        for cluster, width in cells(text):
            if width == 0:
                if cursor > 0:
                    previous = self.chars[row][cursor - 1]
                    if previous != "":
                        self.chars[row][cursor - 1] = previous + cluster
                continue
            if cursor + width > limit:
                break
            if width == 2 and cursor + 1 >= self.cols:
                break
            self.chars[row][cursor] = cluster
            self.colors[row][cursor] = color
            self.bg_colors[row][cursor] = None
            if width == 2:
                self.chars[row][cursor + 1] = ""
                self.colors[row][cursor + 1] = color
                self.bg_colors[row][cursor + 1] = None
            cursor += width
        return cursor

    def fill(
        self,
        row: int,
        col: int,
        width: int,
        ch: str = " ",
        color: ColorValue = None,
    ) ->None:
        if not 0 <= row < self.rows:
            return
        for offset in range(max(0, width)):
            self.put(row, col + offset, ch, color)

    def line(self, row: int) -> str:
        return "".join(self.chars[row]).rstrip()

    def text(self) -> str:
        return "\n".join(self.line(row) for row in range(self.rows))


def render_plain(buffer: CellBuffer) -> str:
    return buffer.text() + "\n"


def visible_width(text: str) -> int:
    return display_width(text)


def sequence_width(parts: Sequence[str]) -> int:
    return sum(display_width(part) for part in parts)
