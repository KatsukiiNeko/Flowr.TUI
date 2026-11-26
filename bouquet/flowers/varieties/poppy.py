"""Poppy: four broad crinkled petals around a dark stamen ring."""

from __future__ import annotations

import math
from dataclasses import replace

from .. import colorways as c
from ..primitives import (
    L_PISTIL,
    center_disc,
    compose,
    petal_ring,
    radial_ticks,
)
from ..registry import Colorway, VarietySpec

_COLORWAYS = (
    Colorway("Red", c.RED, c.DARK_CENTER),
    Colorway("Orange", c.ORANGE, c.DARK_CENTER),
    Colorway("Pink", c.PINK, c.DARK_CENTER),
    Colorway("White", c.WHITE, c.DARK_CENTER),
)

_PETALS = petal_ring(
    count=4,
    base=0.05,
    outer=1.0,
    power=1.0,
    ruffle=0.018,
    ruffle_freq=9,
    radial_shade=0.06,
    edge_shade=-0.12,
    edge_width=0.15,
    base_brightness=0.64,
    glyph="poppy",
)


def _poppy_petals(x, y, phase, lod, colorway):
    sample = _PETALS(x, y, phase, lod, colorway)
    if sample is None:
        return None
    noise = 0.10 * math.sin(37.0 * x + 23.0 * y + phase * 2.0)
    pairs = 0.05 * math.sin(2.0 * math.atan2(y, x) + phase)
    return replace(sample, shade=sample.shade + noise + pairs)


_SHAPE = compose(
    _poppy_petals,
    center_disc(radius=0.22, outer_glyph="o", inner_glyph=":", inner_radius=0.3,
                base_brightness=0.30),
    radial_ticks(
        count=12,
        inner=0.22,
        outer=0.34,
        width=0.08,
        dot_radius=0.03,
        dots_only=True,
        base_brightness=0.34,
    ),
    center_disc(radius=0.07, outer_glyph="@", inner_glyph="@", inner_radius=1.0,
                layer=L_PISTIL, base_brightness=0.50),
)

SPEC = VarietySpec(
    id="poppy",
    name="Poppy",
    size=1.10,
    aspect=1.0,
    colorways=_COLORWAYS,
    shape=_SHAPE,
    has_center=True,
    blob_glyph="o",
)
