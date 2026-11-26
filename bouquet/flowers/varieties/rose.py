"""Rose: compact scalloped layers around a dense swirl centre."""

from __future__ import annotations

import math

from .. import colorways as c
from ..primitives import TAU, center_disc, compose, layered_disc
from ..registry import Colorway, VarietySpec

_COLORWAYS = (
    Colorway("Red", c.RED, c.RED),
    Colorway("Pink", c.PINK, c.PINK),
    Colorway("White", c.WHITE, c.GOLD_CENTER),
    Colorway("Peach", c.PEACH, c.PEACH),
)

_BASE = layered_disc(
    layers=4,
    bumps=6,
    bump_depth=0.055,
    irregular=0.012,
    irregular_freq=17,
    glyph="dense",
    shade_alt=0.09,
    seam_shade=0.16,
    spiral=0.10,
)


def _rose_layers(x, y, phase, lod, colorway):
    sample = _BASE(x, y, phase, lod, colorway)
    if sample is None:
        return None
    r = math.hypot(x, y)
    phi = math.atan2(y, x)
    # A thin carved spiral reads as the dark separation between curled petals.
    if abs((((5.0 * phi / TAU + 7.0 * r + phase * 0.8) % 1.0) - 0.5)) < 0.045:
        return None
    return sample


_SHAPE = compose(
    _rose_layers,
    center_disc(
        radius=0.21,
        style="swirl",
        outer_glyph="%",
        inner_glyph="@",
        base_brightness=0.50,
    ),
)

SPEC = VarietySpec(
    id="rose",
    name="Rose",
    size=0.90,
    aspect=1.0,
    colorways=_COLORWAYS,
    shape=_SHAPE,
    has_center=True,
    blob_glyph="@",
)
