"""Cherry blossom: five broad cleft petals and short stamen ticks."""

from __future__ import annotations

from .. import colorways as c
from ..primitives import TAU, center_disc, compose, petal_ring, radial_ticks
from ..registry import Colorway, VarietySpec

_COLORWAYS = (
    Colorway("Blush", c.BLUSH, c.PINK),
    Colorway("Pink", c.PINK, c.RED),
    Colorway("White", c.WHITE, c.PINK),
)

_SHAPE = compose(
    petal_ring(
        count=5,
        base=0.34,
        outer=0.95,
        power=0.50,
        cleft=0.24,
        cleft_width=0.15,
        radial_shade=0.08,
        edge_shade=-0.16,
        edge_width=0.12,
        base_brightness=0.68,
        glyph="soft",
    ),
    center_disc(radius=0.22, outer_glyph="o", inner_glyph="@", inner_radius=0.42,
                base_brightness=0.55),
    radial_ticks(
        count=9,
        inner=0.20,
        outer=0.42,
        width=0.04,
        dot_radius=0.035,
        phase_offset=TAU / 18.0,
    ),
)

SPEC = VarietySpec(
    id="cherry",
    name="Cherry blossom",
    size=0.80,
    aspect=1.0,
    colorways=_COLORWAYS,
    shape=_SHAPE,
    has_center=True,
    blob_glyph="o",
)
