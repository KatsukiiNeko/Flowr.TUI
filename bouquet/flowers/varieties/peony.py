"""Peony: a large, full pom-pom with no visible centre."""

from __future__ import annotations

from .. import colorways as c
from ..primitives import layered_disc
from ..registry import Colorway, VarietySpec

_COLORWAYS = (
    Colorway("Pink", c.PINK, c.PINK),
    Colorway("Magenta", c.MAGENTA, c.MAGENTA),
    Colorway("White", c.WHITE, c.WHITE),
    Colorway("Coral", c.ORANGE, c.ORANGE),
)

_SHAPE = layered_disc(
    layers=4,
    bumps=9,
    bump_depth=0.24,
    irregular=0.08,
    irregular_freq=13,
    glyph="dense",
    shade_alt=0.095,
    seam_shade=0.17,
    spiral=0.035,
)

SPEC = VarietySpec(
    id="peony",
    name="Peony",
    size=1.15,
    aspect=1.05,
    colorways=_COLORWAYS,
    shape=_SHAPE,
    has_center=False,
    blob_glyph="%",
)
