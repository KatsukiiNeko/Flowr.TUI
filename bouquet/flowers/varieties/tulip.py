"""Tulip: the reference closed cup with a notched, three-lobed rim."""

from __future__ import annotations

from .. import colorways as c
from ..primitives import cup
from ..registry import Colorway, VarietySpec

_COLORWAYS = (
    Colorway("Red", c.RED, c.DARK_CENTER),
    Colorway("Pink", c.PINK, c.GOLD_CENTER),
    Colorway("Yellow", c.YELLOW, c.DARK_CENTER),
    Colorway("Purple", c.PURPLE, c.GOLD_CENTER),
    Colorway("White", c.WHITE, c.GOLD_CENTER),
)

SPEC = VarietySpec(
    id="tulip",
    name="Tulip",
    size=0.85,
    aspect=1.0,
    colorways=_COLORWAYS,
    shape=cup(width=0.62),
    has_center=False,
    blob_glyph="|",
)
