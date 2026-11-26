"""Cosmos: eight wide wedge petals with three-toothed tips."""

from __future__ import annotations

from .. import colorways as c
from ..primitives import center_disc, compose, petal_ring
from ..registry import Colorway, VarietySpec

_COLORWAYS = (
    Colorway("Pink", c.PINK, c.GOLD_CENTER),
    Colorway("Magenta", c.MAGENTA, c.GOLD_CENTER),
    Colorway("White", c.WHITE, c.YELLOW),
)

_SHAPE = compose(
    petal_ring(
        count=8,
        base=0.42,
        outer=1.0,
        power=1.0,
        teeth=3,
        teeth_depth=0.12,
        radial_shade=0.10,
        edge_shade=-0.18,
        edge_width=0.12,
        base_brightness=0.66,
        glyph="soft",
    ),
    center_disc(radius=0.18, outer_glyph="o", inner_glyph="@", inner_radius=0.5,
                base_brightness=0.55),
)

SPEC = VarietySpec(
    id="cosmos",
    name="Cosmos",
    size=0.95,
    aspect=1.15,
    colorways=_COLORWAYS,
    shape=_SHAPE,
    has_center=True,
    blob_glyph="o",
)
