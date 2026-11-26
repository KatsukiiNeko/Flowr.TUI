"""ANSI diff presenter supporting xterm-256, 24-bit truecolor, and optional bg.

Only changed cells are written.  Alternate-screen entry, cursor hiding,
synchronised output and the exit sequence are all owned here so every exit
path (quit, signal, exception, atexit) can call the same idempotent restore.
"""

from __future__ import annotations

import sys
from typing import List, Optional, TextIO

from ..flowers.colorways import ColorValue
from .buffer import CellBuffer

ALT_ON = "\x1b[?1049h"
ALT_OFF = "\x1b[?1049l"
CURSOR_HIDE = "\x1b[?25l"
CURSOR_SHOW = "\x1b[?25h"
SYNC_ON = "\x1b[?2026h"
SYNC_OFF = "\x1b[?2026l"
CLEAR = "\x1b[2J\x1b[H"
RESET = "\x1b[0m"
HOME = "\x1b[H"


def fg_escape(color: ColorValue) -> str:
    if color is None:
        return "\x1b[39m"
    if isinstance(color, tuple):
        return "\x1b[38;2;%d;%d;%dm" % color
    return "\x1b[38;5;%dm" % color


def bg_escape(color: ColorValue) -> str:
    if color is None:
        return "\x1b[49m"
    if isinstance(color, tuple):
        return "\x1b[48;2;%d;%d;%dm" % color
    return "\x1b[48;5;%dm" % color


class AnsiPresenter:
    def __init__(self, out: Optional[TextIO] = None, color: bool = True) -> None:
        self.out = out or sys.stdout
        self.color = color
        self._prev_chars: Optional[List[List[str]]] = None
        self._prev_colors: Optional[List[List[ColorValue]]] = None
        self._prev_bgs: Optional[List[List[ColorValue]]] = None
        self._entered = False
        self._force_clear = False
        self._cursor_visible = False

    def enter(self) -> None:
        if self._entered:
            return
        self.out.write(ALT_ON + CURSOR_HIDE + SYNC_ON + CLEAR + SYNC_OFF)
        self.out.flush()
        self._entered = True
        self.invalidate()

    def invalidate(self) -> None:
        self._prev_chars = None
        self._prev_colors = None
        self._prev_bgs = None
        self._force_clear = True

    def render(self, buffer: CellBuffer, cursor=None) -> None:
        if not self._entered:
            self.enter()
        parts: List[str] = [SYNC_ON]
        if self._force_clear or self._prev_chars is None:
            parts.append(CLEAR)
            self._force_clear = False
            prev_chars: List[List[str]] = [["\x00"] * buffer.cols for _ in range(buffer.rows)]
            prev_colors: List[List[ColorValue]] = [[None] * buffer.cols for _ in range(buffer.rows)]
            prev_bgs: List[List[ColorValue]] = [[None] * buffer.cols for _ in range(buffer.rows)]
        else:
            prev_chars = self._prev_chars
            prev_colors = self._prev_colors  # type: ignore[assignment]
            prev_bgs = self._prev_bgs  # type: ignore[assignment]
        if len(prev_chars) != buffer.rows or (prev_chars and len(prev_chars[0]) != buffer.cols):
            parts.append(CLEAR)
            prev_chars = [["\x00"] * buffer.cols for _ in range(buffer.rows)]
            prev_colors = [[None] * buffer.cols for _ in range(buffer.rows)]
            prev_bgs = [[None] * buffer.cols for _ in range(buffer.rows)]

        for row in range(buffer.rows):
            row_chars = buffer.chars[row]
            row_colors = buffer.colors[row]
            row_bgs = buffer.bg_colors[row]
            prev_row = prev_chars[row]
            prev_col = prev_colors[row]
            prev_bg = prev_bgs[row]
            col = 0
            while col < buffer.cols:
                ch = row_chars[col]
                if ch == "":
                    col += 1
                    continue
                changed = (
                    (ch != prev_row[col])
                    or (row_colors[col] != prev_col[col])
                    or (row_bgs[col] != prev_bg[col])
                )
                if not changed:
                    col += 1
                    continue
                start = col
                col += 1
                while col < buffer.cols:
                    if ((row_chars[col] != prev_row[col])
                            or (row_colors[col] != prev_col[col])
                            or (row_bgs[col] != prev_bg[col])):
                        col += 1
                        continue
                    look = col
                    while look < buffer.cols and look - col < 3 and not (
                            (row_chars[look] != prev_row[look])
                            or (row_colors[look] != prev_col[look])
                            or (row_bgs[look] != prev_bg[look])):
                        look += 1
                    if look < buffer.cols and look - col < 3:
                        col = look
                    else:
                        break
                parts.append("\x1b[%d;%dH" % (row + 1, start + 1))
                current_fg: object = object()
                current_bg: object = None
                for index in range(start, min(col, buffer.cols)):
                    glyph = row_chars[index]
                    if glyph == "":
                        continue
                    if self.color:
                        fg = row_colors[index]
                        bg = row_bgs[index]
                        if fg != current_fg:
                            current_fg = fg
                            parts.append(fg_escape(fg))
                        if bg != current_bg:
                            current_bg = bg
                            parts.append(bg_escape(bg))
                    parts.append(glyph)
                if self.color:
                    if current_fg is not None:
                        parts.append("\x1b[39m")
                    if current_bg is not None:
                        parts.append("\x1b[49m")
        parts.append(SYNC_OFF)
        if cursor is not None:
            row, col = cursor
            parts.append(CURSOR_SHOW + "\x1b[%d;%dH" % (row + 1, col + 1))
            self._cursor_visible = True
        elif self._cursor_visible:
            parts.append(CURSOR_HIDE)
            self._cursor_visible = False
        self.out.write("".join(parts))
        self.out.flush()
        self._prev_chars = [row[:] for row in buffer.chars]
        self._prev_colors = [row[:] for row in buffer.colors]
        self._prev_bgs = [row[:] for row in buffer.bg_colors]

    def exit(self) -> None:
        if not self._entered:
            return
        try:
            self.out.write(SYNC_OFF + RESET + CURSOR_SHOW + ALT_OFF)
            self.out.flush()
        finally:
            self._entered = False
            self._prev_chars = None
            self._prev_colors = None
            self._prev_bgs = None

    def clear_screen(self) -> None:
        if self._entered:
            self.out.write(SYNC_ON + CLEAR + SYNC_OFF)
            self.out.flush()
            self.invalidate()
