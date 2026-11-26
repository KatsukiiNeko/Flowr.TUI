"""One keymap table, used by the app, the panel footer and the help screen."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class KeyBinding:
    keys: Tuple[str, ...]
    label: str
    action: str
    group: str


KEYMAP = (
    KeyBinding(("space",), "Pause / resume", "pause", "Playback"),
    KeyBinding(("q", "ctrl-c"), "Quit", "quit", "Playback"),
    KeyBinding(("?",), "Help", "help", "Playback"),
    KeyBinding(("tab",), "Settings panel", "panel", "Playback"),
    KeyBinding(("v",), "Cycle detail", "detail", "Playback"),
    KeyBinding(("[", "]"), "Change tab", "tabs", "Panel"),
    KeyBinding(("1", "2", "3", "4", "5", "6"), "Select tab", "tab_numbers", "Panel"),
    KeyBinding(("up", "down"), "Select setting", "select", "Panel"),
    KeyBinding(("left", "right"), "Adjust value", "adjust", "Panel"),
    KeyBinding(("shift-up", "shift-down", "shift-left", "shift-right",
                "shift-pgup", "shift-pgdn", "pgup", "pgdn"),
               "Coarse adjust", "coarse", "Panel"),
    KeyBinding(("enter",), "Activate / edit", "activate", "Panel"),
    KeyBinding(("m",), "Edit message", "message", "Message"),
    KeyBinding(("s",), "Shuffle bouquet", "shuffle", "Message"),
    KeyBinding(("r",), "Reset animation", "reset", "Message"),
    KeyBinding(("D",), "Reset defaults", "defaults", "Message"),
    KeyBinding(("+", "-"), "Target FPS", "fps", "Playback"),
    KeyBinding(("left", "right", "home", "end"), "Move caret", "caret", "Message editor"),
    KeyBinding(("backspace", "delete"), "Delete char", "delete", "Message editor"),
    KeyBinding(("enter",), "Commit message", "commit", "Message editor"),
    KeyBinding(("esc",), "Cancel / close", "cancel", "Message editor"),
)

KEY_LABELS = {
    "space": "Space",
    "ctrl-c": "Ctrl+C",
    "tab": "Tab",
    "up": "\u2191",
    "down": "\u2193",
    "left": "\u2190",
    "right": "\u2192",
    "pgup": "PageUp",
    "pgdn": "PageDown",
    "shift-pgup": "Shift+PageUp",
    "shift-pgdn": "Shift+PageDown",
    "enter": "Enter",
    "esc": "Esc",
    "home": "Home",
    "end": "End",
    "backspace": "Backspace",
    "delete": "Delete",
}


def key_label(key: str) -> str:
    return KEY_LABELS.get(key, key)


def binding_keys(binding: KeyBinding, ascii_mode: bool = False) -> str:
    label = " / ".join(key_label(key) for key in binding.keys)
    if ascii_mode:
        return (label.replace("\u2191", "Up").replace("\u2193", "Down")
                .replace("\u2190", "Left").replace("\u2192", "Right"))
    return label


def footer_hint(ascii_mode: bool = False) -> str:
    short_labels = {"help": "help", "panel": "panel", "detail": "detail", "quit": "quit"}
    items = []
    for action in ("help", "panel", "detail", "quit"):
        binding = next(item for item in KEYMAP if item.action == action)
        key = binding.keys[0] if action in ("quit", "detail") else None
        keys = key_label(key) if key else binding_keys(binding, ascii_mode)
        items.append("%s %s" % (keys, short_labels[action]))
    return " ".join(items)
