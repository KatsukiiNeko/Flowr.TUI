"""Shared shape primitives used by the flower varieties.

All primitives work in a head-local unit disc where x,y are already scaled for
the terminal cell aspect.  Each returns a Sample or None.  Varieties are built
by composing a handful of these pieces, not by bespoke per-pixel drawing
functions.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Callable, Optional, Sequence

from .registry import (
    L_CENTER,
    L_INNER,
    L_PETAL,
    L_PISTIL,
    L_SEPAL,
    L_STAMEN,
    Colorway,
    Sample,
)

TAU = 2.0 * math.pi


def wrap_angle(value: float) -> float:
    value = (value + math.pi) % TAU - math.pi
    return value


def polar(x: float, y: float):
    return math.hypot(x, y), math.atan2(y, x)


def compose(*shapes: Callable) -> Callable:
    """Return the topmost non-empty sample from left to right."""

    def sample(x, y, phase, lod, colorway):
        for shape in shapes:
            result = shape(x, y, phase, lod, colorway)
            if result is not None:
                return result
        return None

    return sample


def _petal_count(count, colorway: Colorway) -> int:
    if callable(count):
        return max(1, int(count(colorway)))
    return max(1, int(count))


def petal_ring(
    count,
    base: float = 0.32,
    outer: float = 1.0,
    power: float = 0.7,
    inner: float = 0.0,
    ruffle: float = 0.0,
    ruffle_freq: float = 7.0,
    cleft: float = 0.0,
    cleft_width: float = 0.16,
    teeth: int = 0,
    teeth_depth: float = 0.0,
    layer: int = L_PETAL,
    glyph: str = "petal",
    base_brightness: float = 0.62,
    radial_shade: float = 0.12,
    edge_shade: float = -0.22,
    edge_width: float = 0.14,
    ridge: float = 0.0,
) -> Callable:
    """A radial ring of petals.

    Petal tips reach *outer*, gaps fall back to *base*.  *cleft* cuts a small
    notch in the tip of each petal, *teeth* serrates the outside edge, *ruffle*
    waves the outline.  Daisies in the reference are ``base=0.32, power=0.7``.
    """

    def sample(x, y, phase, lod, colorway):
        r = math.hypot(x, y)
        if r > 1.0:
            return None
        phi = math.atan2(y, x)
        petals = _petal_count(count, colorway)
        t = (((phi + phase) * petals / TAU) % 1.0)
        wave = abs(math.cos(math.pi * t))
        reach = base + (outer - base) * (wave ** power)
        if ruffle:
            reach += ruffle * math.sin(ruffle_freq * phi + phase * 1.7)
        if ruffle_freq and teeth:
            tooth = (0.5 - 0.5 * math.cos(TAU * teeth * t + phase * 2.0)) ** 1.5
            reach -= teeth_depth * tooth * max(0.0, min(1.0, (r - 0.45) / 0.55))
        if r < inner or r > reach:
            return None
        if cleft and r > 0.55:
            distance = min(t, 1.0 - t)
            if distance < cleft_width:
                depth = cleft * (1.0 - distance / max(1e-6, cleft_width))
                if r > reach - depth:
                    return None
        edge = edge_shade if r > reach - edge_width * max(0.15, reach) else 0.0
        shade = radial_shade * r + edge
        if ridge:
            shade += ridge * math.cos(TAU * t)
        return Sample(1.0, shade, layer, glyph, base=base_brightness)

    return sample


def cup(
    width: float = 0.62,
    base_brightness: float = 0.55,
    lobes: float = 1.5,
    seam_pos: float = 0.33,
    seam_width: float = 0.12,
    seam_shade: float = -0.25,
    rim_shade: float = -0.08,
    glyph: str = "cup",
) -> Callable:
    """The reference tulip cup: a narrow base, wide top and notched rim."""

    def sample(x, y, phase, lod, colorway):
        v = (1.0 - y) / 2.0
        if v < 0.0 or v > 1.0:
            return None
        half_width = width * math.sin(math.pi * 0.5 * min(1.0, v * 1.5 + 0.05))
        if half_width <= 0.0 or abs(x) > half_width:
            return None
        xn = x / half_width
        if v > 0.72 + 0.28 * math.cos(lobes * math.pi * xn) ** 2:
            return None
        seam = seam_shade if abs(abs(xn) - seam_pos) < seam_width and v > 0.3 else 0.0
        rim = rim_shade if v > 0.9 else 0.0
        shade = -0.3 * xn + 0.1 * v + seam + rim
        return Sample(1.0, shade, L_PETAL, glyph, base=base_brightness)

    return sample


def center_disc(
    radius: float,
    outer_glyph: str = "o",
    inner_glyph: str = "@",
    inner_radius: float = 0.55,
    style: str = "smooth",
    base_brightness: float = 0.55,
    layer: int = L_CENTER,
) -> Callable:
    """A solid or textured centre.

    Styles: ``smooth`` (daisy), ``swirl`` (rose) and ``seed`` (sunflower).
    """

    def sample(x, y, phase, lod, colorway):
        r = math.hypot(x, y)
        if r > radius:
            return None
        phi = math.atan2(y, x)
        t = r / max(1e-6, radius)
        if style == "seed" and lod == 2:
            texture = math.sin(17.0 * phi + 31.0 * t * t + phase * 1.3)
            if r < radius * 0.09:
                glyph = "@"
                shade = 0.12
            elif texture > 0.68:
                glyph = "%"
                shade = 0.10
            elif texture > 0.05:
                glyph = ":"
                shade = -0.02
            else:
                glyph = "."
                shade = -0.10
            shade += 0.05 * math.sin(23.0 * phi + 7.0 * t)
            if t > 0.88:
                shade -= 0.16
            return Sample(1.0, shade, layer, glyph, base=0.42)
        if style == "swirl":
            swirl = math.sin(6.0 * phi + 13.0 * t + phase * 2.0)
            if r < radius * 0.18:
                glyph = inner_glyph
            elif swirl > 0.35:
                glyph = "%"
            else:
                glyph = "#"
            shade = 0.17 * swirl - 0.10 * t
            return Sample(1.0, shade, layer, glyph, base=0.56)
        if style == "seed":
            texture = math.sin(9.0 * phi + 15.0 * t + phase)
            glyph = ":" if texture > 0.3 else "."
            shade = 0.06 * texture - 0.12 * (t > 0.82)
            return Sample(1.0, shade, layer, glyph, base=base_brightness)
        if r < radius * inner_radius:
            return Sample(1.0, 0.0, layer, inner_glyph, base=base_brightness)
        shade = -0.10 if t > 0.82 else -0.04 * (0.5 + 0.5 * math.sin(5.0 * phi + phase))
        return Sample(1.0, shade, layer, outer_glyph, base=base_brightness)

    return sample


def radial_ticks(
    count: int,
    inner: float,
    outer: float,
    width: float = 0.055,
    dot_radius: float = 0.0,
    phase_offset: float = 0.0,
    dots_only: bool = False,
    layer: int = L_STAMEN,
    base_brightness: float = 0.58,
) -> Callable:
    """Thin stamens radiating from the centre, optionally ending in a dot."""

    def sample(x, y, phase, lod, colorway):
        r = math.hypot(x, y)
        if r < inner or r > outer:
            return None
        phi = math.atan2(y, x)
        step = TAU / max(1, count)
        nearest = int(round((phi - phase - phase_offset) / step))
        angle = nearest * step + phase + phase_offset
        distance = abs(wrap_angle(phi - angle))
        if dots_only:
            if r < outer - max(dot_radius, 0.045):
                return None
            if distance > width * 1.6:
                return None
            return Sample(1.0, 0.12, layer, "*", base=base_brightness)
        if distance > width:
            return None
        if dot_radius and r > outer - dot_radius:
            return Sample(1.0, 0.16, layer, "*", base=base_brightness)
        glyph = "." if r < outer - 0.05 else "'"
        return Sample(1.0, -0.06, layer, glyph, base=base_brightness)

    return sample


def star_petals(
    count: int = 6,
    long_every: int = 2,
    short_scale: float = 0.72,
    half_width: float = 0.30,
    curve: float = 0.07,
    midrib: bool = True,
    speckles: float = 0.0,
    glyph: str = "sparse",
) -> Callable:
    """Alternating long and short pointed tepals, as in a lily."""

    step = TAU / max(1, count)

    def sample(x, y, phase, lod, colorway):
        r = math.hypot(x, y)
        if r > 1.0:
            return None
        phi = math.atan2(y, x)
        index = int(round((phi - phase) / step))
        angle = index * step + phase
        length = 1.0 if index % max(1, long_every) == 0 else short_scale
        normalized = r / length
        if normalized > 1.0:
            return None
        distance = wrap_angle(phi - angle - curve * normalized * normalized)
        half = half_width * (1.0 - normalized ** 1.35) + 0.012
        if abs(distance) > half:
            return None
        shade = -0.10 if abs(distance) > half * 0.72 else 0.02
        if midrib and abs(distance) < 0.045:
            shade += 0.13
        if speckles > 0.0:
            pattern = math.sin(37.0 * x + 23.0 * y + phase * 3.0)
            if pattern > 1.0 - speckles:
                shade -= 0.18
        return Sample(1.0, shade, L_PETAL, glyph, base=0.65)

    return sample


def layered_disc(
    layers: int = 4,
    bumps: int = 6,
    bump_depth: float = 0.035,
    irregular: float = 0.0,
    irregular_freq: float = 11.0,
    dome: float = 0.0,
    fringe: int = 0,
    fringe_depth: float = 0.0,
    glyph: str = "dense",
    shade_alt: float = 0.075,
    seam_shade: float = 0.12,
    spiral: float = 0.0,
    base_brightness: float = 0.62,
) -> Callable:
    """Concentric ruffled petals.

    Rose, peony and carnation all use this primitive with different numbers of
    layers, outline frequencies and shading.
    """

    def sample(x, y, phase, lod, colorway):
        r = math.hypot(x, y)
        if r > 1.0:
            return None
        phi = math.atan2(y, x)
        rmax = (
            0.985
            - bump_depth * (0.5 + 0.5 * math.cos(bumps * (phi + phase)))
            - irregular * (0.5 + 0.5 * math.sin(irregular_freq * phi + phase * 1.7))
            - dome * max(0.0, y)
        )
        if fringe:
            rmax -= fringe_depth * (0.5 + 0.5 * math.cos(fringe * (phi + phase * 2.0))) ** 1.5
        if r > rmax:
            return None
        q = r + 0.05 * math.sin(4.0 * phi + phase * 1.5)
        ring = min(layers - 1, max(0, int(q * layers)))
        shade = shade_alt if ring % 2 else -shade_alt
        shade += 0.05 * math.sin(bumps * phi + ring * 1.7 + phase * 2.0)
        fraction = q * layers - int(q * layers)
        if fraction > 0.82:
            shade -= seam_shade
        if r > rmax - 0.055:
            shade -= seam_shade
        if fringe:
            shade += 0.07 * math.cos(fringe * phi + 16.0 * r + phase * 2.0)
        if spiral:
            shade += spiral * math.sin(5.0 * phi + 9.0 * r + phase * 1.3)
        layer = L_PETAL if ring == 0 else L_INNER
        cell_glyph = glyph
        if r < 0.18 and ring == layers - 1:
            cell_glyph = "%"
        return Sample(1.0, shade, layer, cell_glyph, base=base_brightness)

    return sample


def tint(sample_fn: Callable, shade_delta: float = 0.0, glyph: Optional[str] = None) -> Callable:
    """Small adapter for adding papery noise or a pair-specific tint."""

    def sample(x, y, phase, lod, colorway):
        result = sample_fn(x, y, phase, lod, colorway)
        if result is None:
            return None
        return replace(
            result,
            shade=result.shade + shade_delta,
            glyph=glyph if glyph is not None else result.glyph,
        )

    return sample


def sepal_ring(count: int, outer: float = 1.0, base: float = 0.62,
               power: float = 1.1, glyph: str = "sparse") -> Callable:
    return petal_ring(
        count,
        base=base,
        outer=outer,
        power=power,
        layer=L_SEPAL,
        glyph=glyph,
        base_brightness=0.48,
        radial_shade=0.04,
        edge_shade=-0.12,
        edge_width=0.10,
    )
