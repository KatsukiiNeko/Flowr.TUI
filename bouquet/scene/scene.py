"""The static bouquet geometry.

Stems, leaves, paper, ribbon, baby's breath and sparkles are derived from
Ascii-Flower-Bouquet by Alish Sharma (MIT); see NOTICE.

In v2, geometry point density scales with ``detail`` (32/64/128/256), stems
tuck cleanly inside the wrap cone, wrap shading stays in the warm paper range,
stem tails are rebalanced for the vertical budget, and greenery frames the cap.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from ..config.settings import Settings
from ..config.themes import (
    assign_themed_hues,
    get_theme,
    resolve_themed_colorway,
)
from ..flowers import Colorway, VarietySpec, get_variety
from ..flowers import colorways as c
from ..geometry.vec import cross, norm
from .composition import flower_plan, head_distance, head_positions, head_scale
from .greenery import build_greenery

Vec3 = Tuple[float, float, float]
# x, y, z, nx, ny, nz, palette, tone, two_sided, override
Point = Tuple[float, float, float, float, float, float, Sequence[int], float, bool, Optional[str]]

WRAP_Y0 = -0.08
WRAP_Y1 = 0.20
WRAP_R0 = 0.055
WRAP_R1 = 0.33
STEM_NECK = (0.0, -0.02, 0.0)


@dataclass(frozen=True)
class FlowerHead:
    position: Vec3
    axis: Vec3
    variety: VarietySpec
    colorway: Colorway
    radius: float
    seed: float
    tone_jitter: float = 0.0
    hue_family: str = ""


@dataclass(frozen=True)
class Scene:
    points: Tuple[Point, ...]
    flowers: Tuple[FlowerHead, ...]
    babies: Tuple[Tuple[float, float, float, float], ...]
    sparkles: Tuple[Tuple[float, float, float, float, float], ...]
    head_scale: float
    total: int
    greenery: Tuple[Point, ...] = ()
    detail: int = 64
    stem_steps: int = 70
    theme_name: str = "classic"
    wrap_style: str = "kraft"

    @property
    def sequence(self) -> Tuple[str, ...]:
        return tuple(flower.variety.id for flower in self.flowers)


def _wrap_palette(settings: Settings) -> Sequence[int]:
    if settings.theme == "classic" and settings.wrap == "kraft":
        return c.PAPER
    return c.WRAP_PALETTES_256.get(settings.wrap, c.PAPER)


def _ribbon_palette(settings: Settings) -> Sequence[int]:
    return get_theme(settings.theme).ribbon_palette


def build_scene(
    settings: Settings,
    static_scene: Optional[Scene] = None,
    detail: int = 64,
) -> Scene:
    detail = max(32, min(256, int(detail)))
    rnd = random.Random(settings.seed)
    neck = STEM_NECK
    plan = flower_plan(settings)
    heads = head_positions(len(plan), rnd)
    stem_steps = 70 if detail == 64 else max(28, int(round(70 * detail / 64.0)))
    points: List[Point] = []
    slope = (WRAP_R1 - WRAP_R0) / (WRAP_Y1 - WRAP_Y0)

    for position, axis in heads:
        base = (
            position[0] - axis[0] * 0.03,
            position[1] - axis[1] * 0.03,
            position[2] - axis[2] * 0.03,
        )
        for step in range(stem_steps):
            t = step / max(1, stem_steps - 1)
            sx = base[0] + (neck[0] - base[0]) * t
            sy = base[1] + (neck[1] - base[1]) * t
            sz = base[2] + (neck[2] - base[2]) * t
            # Tuck stems inside the wrap cone opening so none pierce the paper wall
            if sy < WRAP_Y1 + 0.03:
                cone_r = max(0.02, WRAP_R0 + slope * max(0.0, sy - WRAP_Y0) - 0.025)
                r_xz = math.hypot(sx, sz)
                if r_xz > cone_r and r_xz > 1e-6:
                    scale_in = cone_r / r_xz
                    sx *= scale_in
                    sz *= scale_in
            points.append((
                sx, sy, sz,
                axis[0], 0.0, axis[2],
                c.GREENS, -0.15, True, None,
            ))

    theme = get_theme(settings.theme)
    themed_hues = (
        assign_themed_hues(theme, len(plan), settings.seed)
        if settings.theme not in ("classic", "rainbow")
        else None
    )

    flowers: List[FlowerHead] = []
    for idx, ((position, axis), (variety_id, colorway_index)) in enumerate(zip(heads, plan)):
        spec = get_variety(variety_id)
        if settings.colorway(variety_id) >= 0 or themed_hues is None:
            colorway = spec.colorways[colorway_index % len(spec.colorways)]
            hue = colorway.hue_family
        else:
            target_hue = themed_hues[idx]
            colorway = resolve_themed_colorway(spec, target_hue, theme)
            hue = target_hue
        if variety_id == "daisy":
            radius = rnd.uniform(0.12, 0.14)
        elif variety_id == "tulip":
            radius = 0.11
        else:
            radius = 0.13 * spec.size * rnd.uniform(0.92, 1.08)
        seed = rnd.uniform(0.0, 6.28)
        # Seeded +/-1 palette step tonal jitter (CLR-3)
        tone_jitter = rnd.uniform(-0.08, 0.08)
        flowers.append(FlowerHead(position, axis, spec, colorway, radius, seed, tone_jitter, hue))

    can_reuse_static = (
        static_scene is not None
        and static_scene.detail == detail
        and static_scene.theme_name == settings.theme
        and static_scene.wrap_style == settings.wrap
    )

    if not can_reuse_static:
        wrap_pal = _wrap_palette(settings)
        rib_pal = _ribbon_palette(settings)
        _add_leaves(points, detail)
        _add_wrap(points, rnd, detail, wrap_pal)
        _add_back_stems(points, detail)
        _add_ribbon(points, detail, rib_pal)
        babies = _baby_breath(settings, rnd)
        sparkles = _sparkles(settings, rnd)
        greenery = build_greenery(
            settings.greenery_type,
            settings.greenery_amount,
            settings.seed,
            cap_radius=head_distance(len(flowers)),
            detail=detail,
            tint=theme.greenery_tint,
            neck=neck,
        )
    else:
        assert static_scene is not None
        points.extend(static_scene.points[static_scene.total * static_scene.stem_steps:])
        babies = static_scene.babies
        sparkles = static_scene.sparkles
        greenery = static_scene.greenery

    return Scene(
        tuple(points),
        tuple(flowers),
        tuple(babies),
        tuple(sparkles),
        head_scale(len(flowers)),
        len(flowers),
        greenery=greenery,
        detail=detail,
        stem_steps=stem_steps,
        theme_name=settings.theme,
        wrap_style=settings.wrap,
    )


def _add_leaves(points: List[Point], detail: int = 64) -> None:
    ti_count = max(18, int(round(28 * (detail / 64.0) ** 0.7)))
    wi_half = max(3, int(round(4 * (detail / 64.0) ** 0.5)))
    for index in range(8):
        angle = (index + 0.4) / 8.0 * 2.0 * math.pi
        cosine, sine = math.cos(angle), math.sin(angle)
        # Base sits at the wrap rim, angled outward & upward so leaves frame without draping over paper
        base = (0.30 * cosine, WRAP_Y1, 0.30 * sine)
        direction = norm((cosine, 0.48, sine))
        side = (-sine, 0.0, cosine)
        normal = norm(cross(side, direction))
        length, width = 0.23, 0.065
        for ti in range(ti_count):
            t = ti / max(1, ti_count - 1)
            for wi in range(-wi_half, wi_half + 1):
                w = wi / float(wi_half)
                curl = 0.02 * w * w
                points.append((
                    base[0] + direction[0] * length * t
                    + side[0] * width * math.sin(math.pi * t) * w + normal[0] * curl,
                    base[1] + direction[1] * length * t + 0.02 * t * t + normal[1] * curl,
                    base[2] + direction[2] * length * t
                    + side[2] * width * math.sin(math.pi * t) * w + normal[2] * curl,
                    normal[0], normal[1], normal[2],
                    c.GREENS, -0.22 if wi == 0 else 0.0, True, None,
                ))


def _add_wrap(
    points: List[Point],
    rnd: random.Random,
    detail: int = 64,
    palette: Sequence[int] = c.PAPER,
) -> None:
    y0, y1, r0, r1 = WRAP_Y0, WRAP_Y1, WRAP_R0, WRAP_R1
    slope = (r1 - r0) / (y1 - y0)
    scale_d = detail / 64.0
    rings = max(28, int(round(36 * scale_d)))
    for ring in range(rings):
        t = ring / max(1, rings - 1)
        radius = r0 + (r1 - r0) * t
        count = max(16, int(190 * scale_d * radius))
        for index in range(count):
            phase = (index + 0.35 * rnd.random()) / count * 2.0 * math.pi
            cosine, sine = math.cos(phase), math.sin(phase)
            y = y0 + (y1 - y0) * t
            if t > 0.88:
                y += 0.024 * math.sin(9 * phase)
            # Symmetric fold ripple + warm paper lift so wrap reads clearly as paper
            fold = 0.22 + 0.14 * math.sin(5 * phase)
            normal = norm((cosine, -0.18 * slope, sine))
            points.append((
                radius * cosine, y, radius * sine,
                normal[0], normal[1], normal[2],
                palette, fold, False, None,
            ))


def _add_back_stems(points: List[Point], detail: int = 64) -> None:
    steps = max(12, int(round(18 * (detail / 64.0) ** 0.7)))
    for index in range(7):
        angle = index / 7.0 * 2.0 * math.pi
        sx, sz = 0.022 * math.cos(angle), 0.022 * math.sin(angle)
        for step in range(steps):
            t = step / max(1, steps - 1)
            # ~40% of v1 tail length (-0.12 vs -0.30) while staying >= 2 rows visible
            points.append((
                sx * (1.0 + 1.1 * t), WRAP_Y0 - 0.14 * t, sz * (1.0 + 1.1 * t),
                math.cos(angle), 0.0, math.sin(angle),
                c.GREENS, -0.1, True, None,
            ))


def _add_ribbon(
    points: List[Point],
    detail: int = 64,
    palette: Sequence[int] = c.RIBBON,
) -> None:
    y0, y1, r0, r1 = WRAP_Y0, WRAP_Y1, WRAP_R0, WRAP_R1
    slope = (r1 - r0) / (y1 - y0)
    by = -0.02
    radius = r0 + slope * (by - y0) + 0.012
    ring_steps = max(72, int(round(90 * (detail / 64.0) ** 0.7)))
    for index in range(ring_steps):
        phase = index / float(ring_steps) * 2.0 * math.pi
        for dy in (-0.010, 0.0, 0.010):
            points.append((
                radius * math.cos(phase), by + dy, radius * math.sin(phase),
                math.cos(phase), 0.0, math.sin(phase),
                palette, 0.05, False, None,
            ))
    knot = (0.0, by, radius + 0.012)
    loop_steps = max(48, int(round(70 * (detail / 64.0) ** 0.7)))
    tail_steps = max(18, int(round(24 * (detail / 64.0) ** 0.7)))
    for side in (-1, 1):
        for index in range(loop_steps):
            angle = index / float(loop_steps) * 2.0 * math.pi
            lx = side * (0.055 + 0.055 * math.cos(angle))
            ly = 0.030 * math.sin(angle) + 0.016 * (0.055 + 0.055 * math.cos(angle)) / 0.11
            for fill in (1.0, 0.65):
                points.append((
                    knot[0] + lx * fill, knot[1] + ly * fill, knot[2] + 0.01,
                    side * 0.3, 0.2, 0.93,
                    palette, 0.12, True, None,
                ))
        for index in range(tail_steps):
            t = index / max(1, tail_steps - 1)
            points.append((
                knot[0] + side * 0.048 * t, knot[1] - 0.095 * t, knot[2] + 0.015,
                side * 0.2, 0.0, 0.98,
                palette, -0.02 + 0.05 * math.sin(t * 9.0), True, None,
            ))
    for dx in (-0.01, 0.0, 0.01):
        points.append((dx, by, knot[2] + 0.02, 0.0, 0.0, 1.0, palette, 0.22, True, "@"))


def _baby_breath(settings: Settings, rnd: random.Random):
    babies = []
    for _ in range(max(0, int(settings.baby_density))):
        angle = rnd.random() * 2.0 * math.pi
        elevation = rnd.uniform(0.35, 1.4)
        reach = rnd.uniform(0.45, 0.64)
        babies.append((
            reach * math.cos(angle) * math.cos(elevation),
            0.22 + reach * math.sin(elevation),
            reach * math.sin(angle) * math.cos(elevation),
            rnd.uniform(0.0, 6.28),
        ))
    return babies


def _sparkles(settings: Settings, rnd: random.Random):
    sparkles = []
    for _ in range(max(0, int(settings.sparkle_density))):
        angle = rnd.random() * 2.0 * math.pi
        reach = rnd.uniform(0.75, 0.95)
        sparkles.append((
            reach * math.cos(angle),
            rnd.uniform(-0.15, 1.05),
            reach * math.sin(angle),
            rnd.uniform(0.0, 6.28),
            rnd.uniform(1.5, 4.0),
        ))
    return sparkles
