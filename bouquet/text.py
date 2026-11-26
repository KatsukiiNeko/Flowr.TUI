"""Display-width helpers for terminal text.

Terminals do not measure text in code points: CJK characters and most emoji
occupy two cells, combining marks occupy none.  Every piece of UI text goes
through these helpers so a wide character can never shift the layout.
"""

from __future__ import annotations

import unicodedata
from typing import Iterable, List, Tuple

ELLIPSIS = "\u2026"


def char_width(ch: str) -> int:
    if not ch:
        return 0
    if unicodedata.combining(ch):
        return 0
    category = unicodedata.category(ch)
    if category in ("Mn", "Me", "Cf"):
        return 0
    if category.startswith("C"):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    return 1


def display_width(text: str) -> int:
    return sum(char_width(ch) for ch in text)


def cells(text: str) -> List[Tuple[str, int]]:
    """Split text into (cluster, width) pairs.

    Zero-width marks join the preceding cluster.  A lone zero-width mark is
    kept as a zero-width cluster so it is not silently lost.
    """
    out: List[Tuple[str, int]] = []
    for ch in text:
        width = char_width(ch)
        if width == 0 and out:
            cluster, old_width = out[-1]
            out[-1] = (cluster + ch, old_width)
        else:
            out.append((ch, width))
    return out


def truncate(text: str, width: int, ellipsis: str = ELLIPSIS) -> str:
    """Fit text into *width* display cells, adding an ellipsis when cut."""
    if width <= 0:
        return ""
    if display_width(text) <= width:
        return text
    marker = ellipsis if display_width(ellipsis) <= width else ""
    budget = width - display_width(marker)
    used = 0
    parts: List[str] = []
    for cluster, cluster_width in cells(text):
        if used + cluster_width > budget:
            break
        parts.append(cluster)
        used += cluster_width
    return "".join(parts) + marker


def fit(text: str, width: int) -> str:
    """Pad or truncate to exactly *width* display cells."""
    if width <= 0:
        return ""
    text = truncate(text, width, ellipsis="")
    pad = width - display_width(text)
    return text + (" " * pad if pad > 0 else "")


def cursor_width(text: str, index: int) -> int:
    """Display width of the first *index* code points of text."""
    return display_width(text[:max(0, min(index, len(text)))])


def ascii_text(text: str) -> str:
    """Substitute glyphs whose width is unreliable in some terminals."""
    return (
        text.replace("\u2665", "<3")
        .replace("\u00b7", ".")
        .replace("\u2026", "...")
        .replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u25b6", ">")
        .replace("\u2016", "||")
    )


def join_columns(columns: Iterable[str], width: int, gap: int = 1) -> str:
    """Lay strings out side by side, clipped to *width* display cells."""
    parts: List[str] = []
    used = 0
    for index, column in enumerate(columns):
        if index:
            if used + gap > width:
                break
            parts.append(" " * gap)
            used += gap
        remaining = width - used
        if remaining <= 0:
            break
        clipped = truncate(column, remaining, ellipsis="")
        parts.append(clipped)
        used += display_width(clipped)
    return "".join(parts)
