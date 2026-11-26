"""Help screen, generated from :data:`bouquet.tui.keymap.KEYMAP`."""

from __future__ import annotations

from ..render.buffer import CellBuffer
from ..text import fit, truncate
from .keymap import KEYMAP
from .widgets import draw_box


def _compact_keys(binding, ascii_mode: bool = False) -> str:
    if binding.action == "coarse":
        return "Shift+PgUp/PgDn"
    label = " / ".join(binding.keys)
    if ascii_mode:
        label = (label.replace("up", "Up").replace("down", "Down")
                 .replace("left", "Left").replace("right", "Right")
                 .replace("shift-pgup", "Shift+PgUp").replace("shift-pgdn", "PgDn")
                 .replace("pgup", "PgUp").replace("pgdn", "PgDn")
                 .replace("ctrl-c", "Ctrl+C").replace("backspace", "Bksp")
                 .replace("delete", "Del").replace("home", "Home").replace("end", "End")
                 .replace("space", "Space").replace("tab", "Tab")
                 .replace("enter", "Enter").replace("esc", "Esc"))
        return label
    return (label.replace("shift-pgup", "Shift+PgUp")
            .replace("shift-pgdn", "PgDn")
            .replace("pgup", "PgUp").replace("pgdn", "PgDn")
            .replace("ctrl-c", "Ctrl+C")
            .replace("backspace", "Bksp").replace("delete", "Del")
            .replace("home", "Home").replace("end", "End")
            .replace("space", "Space").replace("tab", "Tab")
            .replace("enter", "Enter").replace("esc", "Esc")
            .replace("up", "\u2191").replace("down", "\u2193")
            .replace("left", "\u2190").replace("right", "\u2192"))


def draw_help(buffer: CellBuffer, ascii_mode: bool = False) -> None:
    entries = [(_compact_keys(binding, ascii_mode), binding.action) for binding in KEYMAP]
    two_columns = buffer.cols >= 76
    if two_columns:
        per_column = (len(entries) + 1) // 2
        columns = [entries[:per_column], entries[per_column:]]
        column_width = 36
        width = min(buffer.cols - 2, column_width * 2 + 4)
        height = min(buffer.rows - 2, per_column + 4)
    else:
        per_column = len(entries)
        columns = [entries]
        column_width = min(buffer.cols - 6, 64)
        width = min(buffer.cols - 2, column_width + 4)
        height = min(buffer.rows - 2, per_column + 4)
    x = max(0, (buffer.cols - width) // 2)
    y = max(0, (buffer.rows - height) // 2)
    draw_box(buffer, x, y, width, height, "Keys")
    content_rows = max(1, height - 4)
    key_width = 17 if two_columns else min(22, column_width // 2)
    for column, items in enumerate(columns):
        offset = x + 2 + column * (column_width + 1)
        available = column_width - (1 if two_columns else 0)
        action_width = max(4, available - key_width - 1)
        for index, (keys, action) in enumerate(items):
            row = y + 2 + index
            if index >= content_rows:
                break
            buffer.put_text(row, offset, fit(truncate(keys, key_width), key_width), 205,
                            max_width=key_width)
            buffer.put_text(row, offset + key_width + 1,
                            truncate(action, action_width), 244,
                            max_width=action_width)
    footer = "After Ascii-Flower-Bouquet (MIT)  \u00b7  ?/Esc closes"
    if ascii_mode:
        footer = "After Ascii-Flower-Bouquet (MIT)  -  ?/Esc closes"
    buffer.put_text(y + height - 2, x + 2, fit(footer, max(0, width - 4)), 238,
                    max_width=max(0, width - 4))
