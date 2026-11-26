"""Escape-sequence parser.

The TUI consumes key *names* (``up``, ``shift-pgup``, ``ctrl-c``, ``a``,
``space``) rather than raw bytes.  Keeping the translation in one pure function
makes it directly testable without a terminal.
"""

from __future__ import annotations

import codecs
import re
from typing import List

CSI_RE = re.compile(r"\x1b\[([0-9;?]*)([A-Za-z~])")
SS3_RE = re.compile(r"\x1bO([A-Za-z])")

_CSI_FINAL = {
    "A": "up",
    "B": "down",
    "C": "right",
    "D": "left",
    "H": "home",
    "F": "end",
    "Z": "shift-tab",
}
_TILDE = {
    "1": "home",
    "2": "insert",
    "3": "delete",
    "4": "end",
    "5": "pgup",
    "6": "pgdn",
    "7": "home",
    "8": "end",
}


class KeyParser:
    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")("ignore")
        self._buffer = ""

    def feed(self, data: bytes) -> List[str]:
        self._buffer += self._decoder.decode(data)
        return self._drain(final=False)

    def flush(self) -> List[str]:
        return self._drain(final=True)

    def _drain(self, final: bool) -> List[str]:
        keys: List[str] = []
        while self._buffer:
            if self._buffer[0] == "\x1b":
                consumed, key = _escape(self._buffer)
                if consumed == 0:
                    if not final and (len(self._buffer) == 1
                                      or self._buffer.startswith(("\x1b[", "\x1bO"))):
                        break
                    if final and self._buffer.startswith(("\x1b[", "\x1bO")):
                        keys.append("unknown")
                        self._buffer = ""
                        continue
                    keys.append("esc")
                    self._buffer = self._buffer[1:]
                    continue
                keys.append(key)
                self._buffer = self._buffer[consumed:]
                continue
            char = self._buffer[0]
            self._buffer = self._buffer[1:]
            keys.append(_control(char))
        return keys


def _control(char: str) -> str:
    code = ord(char)
    if char in ("\r", "\n"):
        return "enter"
    if char == "\t":
        return "tab"
    if char in ("\x7f", "\x08"):
        return "backspace"
    if code == 3:
        return "ctrl-c"
    if code == 4:
        return "ctrl-d"
    if char == " ":
        return "space"
    if code < 32:
        return "ctrl-%s" % chr(code + 96)
    return char


def _escape(text: str):
    if text in ("\x1b[", "\x1bO"):
        return 0, ""
    match = CSI_RE.match(text)
    if match:
        params, final = match.group(1), match.group(2)
        modifier = _modifier(params)
        if final == "~":
            base = _TILDE.get(params.split(";")[0])
            if base:
                return match.end(), _prefix(modifier, base)
            return match.end(), "unknown"
        base = _CSI_FINAL.get(final)
        if base:
            return match.end(), _prefix(modifier, base)
        return match.end(), "unknown"
    match = SS3_RE.match(text)
    if match:
        base = {"A": "up", "B": "down", "C": "right", "D": "left",
                "H": "home", "F": "end"}.get(match.group(1))
        if base:
            return match.end(), base
        return match.end(), "unknown"
    if text.startswith("\x1b[") or text.startswith("\x1bO"):
        # Incomplete CSI/SS3 sequence: wait for the next read.
        return 0, ""
    if text.startswith("\x1b\x1b"):
        return 1, "esc"
    if len(text) >= 2:
        # Alt+<char>.
        return 2, "alt-" + text[1]
    return 0, ""


def _modifier(params: str) -> int:
    parts = params.split(";")
    if len(parts) >= 2:
        try:
            return int(parts[1])
        except ValueError:
            return 1
    return 1


def _prefix(modifier: int, key: str) -> str:
    if modifier in (2,):
        return "shift-" + key
    if modifier in (5,):
        return "ctrl-" + key
    if modifier in (6,):
        return "ctrl-shift-" + key
    if modifier in (3,):
        return "alt-" + key
    return key
