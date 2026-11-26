"""Daisy: the reference disc family, including its six colourways."""

from __future__ import annotations

from .. import colorways as c
from ..primitives import center_disc, compose, petal_ring
from ..registry import Colorway, VarietySpec

_COLORWAYS = (
    Colorway("White", c.WHITE, c.GOLD_CENTER, variant=13),
    Colorway("Pink", c.PINK, c.GOLD_CENTER, variant=8),
    Colorway("Red", c.RED, c.DARK_CENTER, variant=6),
    Colorway("Purple", c.PURPLE, c.GOLD_CENTER, variant=7),
    Colorway("Yellow", c.YELLOW, c.DARK_CENTER, variant=12),
    Colorway("Orange", c.ORANGE, c.DARK_CENTER, variant=9),
)

_SHAPE = compose(
    petal_ring(
        count=lambda colorway: colorway.variant,
        base=0.32,
        outer=1.0,
        power=0.70,
        radial_shade=0.12,
        edge_shade=-0.22,
        edge_width=0.14,
        base_brightness=0.62,
    ),
    center_disc(
        radius=0.30,
        outer_glyph="o",
        inner_glyph="@",
        inner_radius=0.57,
        base_brightness=0.55,
    ),
)

SPEC = VarietySpec(
    id="daisy",
    name="Daisy",
    size=1.0,
    aspect=1.0,
    colorways=_COLORWAYS,
    shape=_SHAPE,
    has_center=True,
    blob_glyph="o",
)
