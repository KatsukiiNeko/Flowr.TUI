"""Sunflower: the largest head, with a seed-textured disc and pointed rays."""

from __future__ import annotations

from .. import colorways as c
from ..primitives import center_disc, compose, petal_ring, sepal_ring
from ..registry import Colorway, VarietySpec

_COLORWAYS = (
    Colorway("Sunny", c.YELLOW, c.DARK_CENTER, variant=24),
    Colorway("Amber", c.ORANGE, c.DARK_CENTER, variant=28),
    Colorway("Burgundy", c.BURGUNDY, c.DARK_CENTER, variant=24),
    Colorway("Cream", c.CREAM, c.DARK_CENTER, variant=22),
)

_SHAPE = compose(
    petal_ring(
        count=lambda colorway: colorway.variant,
        base=0.30,
        outer=1.0,
        power=1.5,
        radial_shade=0.05,
        edge_shade=-0.16,
        edge_width=0.18,
        base_brightness=0.66,
    ),
    center_disc(
        radius=0.45,
        style="seed",
        outer_glyph=":",
        inner_glyph="@",
        base_brightness=0.42,
    ),
    sepal_ring(12, base=0.34, outer=0.58, power=1.0),
)

SPEC = VarietySpec(
    id="sunflower",
    name="Sunflower",
    size=1.30,
    aspect=1.0,
    colorways=_COLORWAYS,
    shape=_SHAPE,
    has_center=True,
    blob_glyph="@",
)
