"""Carnation: a dome with a fringed edge and many frilly layers."""

from __future__ import annotations

from .. import colorways as c
from ..primitives import layered_disc
from ..registry import Colorway, VarietySpec

_COLORWAYS = (
    Colorway("Red", c.RED, c.RED),
    Colorway("Pink", c.PINK, c.PINK),
    Colorway("White", c.WHITE, c.WHITE),
)

_SHAPE = layered_disc(
    layers=5,
    bumps=5,
    bump_depth=0.02,
    irregular=0.012,
    irregular_freq=19,
    dome=0.40,
    fringe=16,
    fringe_depth=0.32,
    glyph="dense",
    shade_alt=0.075,
    seam_shade=0.16,
)

SPEC = VarietySpec(
    id="carnation",
    name="Carnation",
    size=1.0,
    aspect=1.0,
    colorways=_COLORWAYS,
    shape=_SHAPE,
    has_center=False,
    blob_glyph="%",
)
