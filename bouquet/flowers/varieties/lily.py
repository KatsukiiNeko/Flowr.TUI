"""Lily: six pointed tepals, midribs and thin dotted stamens."""

from __future__ import annotations

import math
from dataclasses import replace

from .. import colorways as c
from ..primitives import TAU, center_disc, compose, radial_ticks, star_petals
from ..registry import Colorway, VarietySpec

_COLORWAYS = (
    Colorway("White", c.WHITE, c.GOLD_CENTER, variant=0),
    Colorway("Pink", c.PINK, c.GOLD_CENTER, variant=1),
    Colorway("Orange", c.ORANGE, c.DARK_CENTER, variant=2),
)

_BASE = star_petals(
    count=6,
    long_every=2,
    short_scale=0.72,
    half_width=0.30,
    curve=0.07,
    midrib=True,
    glyph="star",
)


def _lily_shape(x, y, phase, lod, colorway):
    sample = _BASE(x, y, phase, lod, colorway)
    if sample is None:
        return None
    if colorway.variant == 2 and lod >= 1:
        if math.sin(37.0 * x + 23.0 * y + phase * 3.0) > 0.82:
            sample = replace(sample, shade=sample.shade - 0.18)
    return sample


_SHAPE = compose(
    _lily_shape,
    center_disc(radius=0.12, outer_glyph="o", inner_glyph="@", inner_radius=0.4,
                base_brightness=0.55),
    radial_ticks(
        count=6,
        inner=0.10,
        outer=0.56,
        width=0.045,
        dot_radius=0.05,
        phase_offset=TAU / 12.0,
    ),
)

SPEC = VarietySpec(
    id="lily",
    name="Lily",
    size=1.05,
    aspect=1.0,
    colorways=_COLORWAYS,
    shape=_SHAPE,
    has_center=True,
    blob_glyph="*",
)
