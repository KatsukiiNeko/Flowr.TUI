"""Inline single-line message editor."""

from __future__ import annotations

from typing import Optional, Tuple

from ..config.settings import MAX_MESSAGE, sanitize_message
from ..text import char_width, cells, display_width, truncate


class MessageEditor:
    def __init__(self, text: str) -> None:
        self.text = text
        self.cursor = len(text)

    def handle(self, key: str) -> Optional[str]:
        """Returns 'commit', 'cancel' or None."""
        if key == "enter":
            return "commit"
        if key == "esc":
            return "cancel"
        if key in ("left",):
            self.cursor = self._prev(self.cursor)
        elif key in ("right",):
            self.cursor = self._next(self.cursor)
        elif key == "home":
            self.cursor = 0
        elif key == "end":
            self.cursor = len(self.text)
        elif key == "backspace":
            if self.cursor > 0:
                previous = self._prev(self.cursor)
                self.text = self.text[:previous] + self.text[self.cursor:]
                self.cursor = previous
        elif key == "delete":
            if self.cursor < len(self.text):
                following = self._next(self.cursor)
                self.text = self.text[:self.cursor] + self.text[following:]
        elif key == "space":
            self._insert(" ")
        elif len(key) == 1 and key >= " ":
            self._insert(key)
        return None

    def _insert(self, text: str) -> None:
        if len(self.text) >= MAX_MESSAGE:
            return
        self.text = self.text[:self.cursor] + text + self.text[self.cursor:]
        self.cursor += len(text)

    def _prev(self, index: int) -> int:
        if index <= 0:
            return 0
        index -= 1
        while index > 0 and char_width(self.text[index]) == 0:
            index -= 1
        return index

    def _next(self, index: int) -> int:
        if index >= len(self.text):
            return len(self.text)
        index += 1
        while index < len(self.text) and char_width(self.text[index]) == 0:
            index += 1
        return min(index, len(self.text))

    def result(self) -> str:
        return sanitize_message(self.text)

    def layout(self, width: int) -> Tuple[str, int]:
        """Returns (visible text, cursor column) inside *width* cells."""
        if width <= 0:
            return "", 0
        start = 0
        while start < self.cursor and display_width(self.text[start:self.cursor]) >= width:
            start = self._next(start)
        visible = self.text[start:]
        if display_width(visible) > width:
            visible = truncate(visible, width, ellipsis="")
        cursor = display_width(self.text[start:self.cursor])
        cursor = min(max(0, cursor), width)
        return visible, cursor
