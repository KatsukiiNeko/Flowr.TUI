"""Greenery filler registry and geometry generators (eucalyptus, fern, wheat).

Greenery is a separate filler system from flowers: it does not count toward the
flower cap, lives in its own registry, and frames the bouquet from behind and
between heads without burying them.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ..flowers import colorways as c
from ..geometry.vec import norm

Vec3 = Tuple[float, float, float]
# (x, y, z, nx, ny, nz, palette, tone, two_sided, override_glyph)
GreeneryPoint = Tuple[float, float, float, float, float, float, Sequence[int], float, bool, Optional[str]]
SprigFn = Callable[[List[GreeneryPoint], Vec3, float, float, float, random.Random, int, Sequence[int]], None]

GREENERY_TYPES: Tuple[str, ...] = ("eucalyptus", "fern", "wheat", "mixed", "off")


@dataclass(frozen=True)
class GreenerySpec:
    id: str
    name: str
    palette: Sequence[int]
    generator: SprigFn


_REGISTRY: List[GreenerySpec] = []
_BY_ID: Dict[str, GreenerySpec] = {}


def register_greenery(spec: GreenerySpec) -> GreenerySpec:
    if spec.id in _BY_ID:
        raise ValueError("duplicate greenery type: %s" % spec.id)
    _REGISTRY.append(spec)
    _BY_ID[spec.id] = spec
    return spec


def all_greenery() -> Tuple[GreenerySpec, ...]:
    return tuple(_REGISTRY)


def get_greenery(greenery_id: str) -> GreenerySpec:
    return _BY_ID[greenery_id]


def greenery_ids() -> Tuple[str, ...]:
    return tuple(spec.id for spec in _REGISTRY)


def _tint_palette(base: Sequence[int], tint: str) -> Sequence[int]:
    if tint == "silver":
        return c.SILVER if base == c.EUCALYPTUS else c.EUCALYPTUS
    if tint == "dusty":
        return c.EUCALYPTUS if base != c.WHEAT else c.WHEAT
    if tint == "deep":
        return c.FERN if base != c.WHEAT else c.WHEAT
    return base


def _eucalyptus_sprig(
    points: List[GreeneryPoint],
    neck: Vec3,
    azimuth: float,
    elevation: float,
    cap_radius: float,
    rnd: random.Random,
    detail: int,
    palette: Sequence[int],
) -> None:
    """Arching stem (0.35-0.7) with 8-14 alternate pairs of oval leaves."""
    ca, sa = math.cos(azimuth), math.sin(azimuth)
    ce, se = math.cos(elevation), math.sin(elevation)
    reach = max(0.35, min(0.70, cap_radius * rnd.uniform(1.10, 1.35)))
    # Keep stem tucked inside cone first, flaring out near outer rim to frame heads
    direction = norm((ca * ce, se, sa * ce))
    side_vec = (-sa, 0.0, ca)
    num_pairs = rnd.randint(8, 14)
    stem_steps = max(14, int(24 * (detail / 64.0) ** 0.5))
    arc = rnd.uniform(0.06, 0.14)

    def pos_at(t: float) -> Vec3:
        # Flare outward cleanly only after clearing the wrap/head base
        flare = t * t
        x = neck[0] + direction[0] * reach * (0.45 * t + 0.55 * flare) + ca * arc * math.sin(math.pi * t)
        y = neck[1] + direction[1] * reach * t + 0.06 * math.sin(math.pi * t)
        z = neck[2] + direction[2] * reach * (0.45 * t + 0.55 * flare) + sa * arc * math.sin(math.pi * t)
        return x, y, z

    for step in range(stem_steps):
        t = step / max(1, stem_steps - 1)
        px, py, pz = pos_at(t)
        points.append((px, py, pz, ca, 0.2, sa, palette, -0.15, True, "/"))

    leaf_steps = 2 if detail <= 32 else (3 if detail <= 64 else 4)
    for pair_idx in range(num_pairs):
        # Start leaves outside the wrap/inner head mass (t in 0.52..0.98)
        lt = 0.52 + 0.46 * (pair_idx / max(1, num_pairs - 1))
        bx, by, bz = pos_at(lt)
        leaf_r = rnd.uniform(0.032, 0.048) * (1.0 - 0.25 * lt)
        for side in (-1, 1):
            stagger = 0.02 if side < 0 else 0.0
            sx, sy, sz = pos_at(min(0.99, lt + stagger))
            for li in range(1, leaf_steps + 1):
                u = li / leaf_steps
                for wi in (-1, 0, 1):
                    v = wi * 0.65
                    w_scale = math.sqrt(max(0.0, 1.0 - v * v)) * math.sin(math.pi * u)
                    lx = sx + side_vec[0] * side * leaf_r * (0.6 + 1.2 * u) + direction[0] * leaf_r * 0.5 * v * w_scale
                    ly = sy + 0.008 * u + 0.005 * wi
                    lz = sz + side_vec[2] * side * leaf_r * (0.6 + 1.2 * u) + direction[2] * leaf_r * 0.5 * v * w_scale
                    glyph = "~" if wi == 0 else ","
                    points.append((lx, ly, lz, 0.0, 0.9, side * 0.3, palette, 0.05 * u, True, glyph))


def _fern_sprig(
    points: List[GreeneryPoint],
    neck: Vec3,
    azimuth: float,
    elevation: float,
    cap_radius: float,
    rnd: random.Random,
    detail: int,
    palette: Sequence[int],
) -> None:
    """Arching rachis with feathery tapered pinnae."""
    ca, sa = math.cos(azimuth), math.sin(azimuth)
    ce, se = math.cos(elevation), math.sin(elevation)
    reach = max(0.38, min(0.74, cap_radius * rnd.uniform(1.12, 1.35)))
    direction = norm((ca * ce, se, sa * ce))
    side_vec = (-sa, 0.0, ca)
    num_pinnae = rnd.randint(10, 16)
    stem_steps = max(14, int(24 * (detail / 64.0) ** 0.5))

    def pos_at(t: float) -> Vec3:
        x = neck[0] + direction[0] * reach * t + ca * 0.12 * t * t
        y = neck[1] + direction[1] * reach * t - 0.08 * t * t
        z = neck[2] + direction[2] * reach * t + sa * 0.12 * t * t
        return x, y, z

    for step in range(stem_steps):
        t = step / max(1, stem_steps - 1)
        px, py, pz = pos_at(t)
        points.append((px, py, pz, ca, 0.25, sa, palette, -0.10, True, ";"))

    pinna_steps = 2 if detail <= 32 else (3 if detail <= 64 else 4)
    for pi in range(num_pinnae):
        pt = 0.45 + 0.53 * (pi / max(1, num_pinnae - 1))
        bx, by, bz = pos_at(pt)
        pinna_len = 0.065 * (1.0 - 0.72 * ((pt - 0.45) / 0.55))
        for side in (-1, 1):
            for li in range(1, pinna_steps + 1):
                u = li / pinna_steps
                lx = bx + side_vec[0] * side * pinna_len * u + direction[0] * pinna_len * 0.35 * u
                ly = by - 0.008 * u * u
                lz = bz + side_vec[2] * side * pinna_len * u + direction[2] * pinna_len * 0.35 * u
                glyph = "," if u > 0.6 else "~"
                points.append((lx, ly, lz, 0.0, 0.95, side * 0.2, palette, 0.08 * (1.0 - u), True, glyph))


def _wheat_sprig(
    points: List[GreeneryPoint],
    neck: Vec3,
    azimuth: float,
    elevation: float,
    cap_radius: float,
    rnd: random.Random,
    detail: int,
    palette: Sequence[int],
) -> None:
    """Thin stalk with angled grain ticks in straw/gold."""
    ca, sa = math.cos(azimuth), math.sin(azimuth)
    ce, se = math.cos(elevation), math.sin(elevation)
    reach = max(0.45, min(0.80, cap_radius * rnd.uniform(1.15, 1.35)))
    direction = norm((ca * ce, se, sa * ce))
    side_vec = (-sa, 0.0, ca)
    stem_steps = max(16, int(28 * (detail / 64.0) ** 0.5))

    def pos_at(t: float) -> Vec3:
        x = neck[0] + direction[0] * reach * t + ca * 0.06 * t * t
        y = neck[1] + direction[1] * reach * t
        z = neck[2] + direction[2] * reach * t + sa * 0.06 * t * t
        return x, y, z

    for step in range(stem_steps):
        t = step / max(1, stem_steps - 1)
        px, py, pz = pos_at(t)
        points.append((px, py, pz, ca, 0.1, sa, palette, -0.05, True, "/"))

    grains = 8 if detail <= 64 else 12
    for gi in range(grains):
        gt = 0.70 + 0.28 * (gi / max(1, grains - 1))
        bx, by, bz = pos_at(gt)
        for side in (-1, 1):
            for step in (1, 2):
                u = step * 0.5
                gx = bx + side_vec[0] * side * 0.022 * u + direction[0] * 0.025 * u
                gy = by + 0.018 * u
                gz = bz + side_vec[2] * side * 0.022 * u + direction[2] * 0.025 * u
                points.append((gx, gy, gz, 0.0, 0.85, side * 0.3, palette, 0.12, True, "'" if side > 0 else "`"))


register_greenery(GreenerySpec("eucalyptus", "Eucalyptus", c.EUCALYPTUS, _eucalyptus_sprig))
register_greenery(GreenerySpec("fern", "Fern", c.FERN, _fern_sprig))
register_greenery(GreenerySpec("wheat", "Wheat", c.WHEAT, _wheat_sprig))


def build_greenery(
    greenery_type: str,
    amount: int,
    seed: int,
    cap_radius: float = 0.64,
    detail: int = 64,
    tint: str = "default",
    neck: Vec3 = (0.0, -0.05, 0.0),
) -> Tuple[GreeneryPoint, ...]:
    """Generate deterministic greenery sprigs framing the bouquet."""
    if greenery_type == "off" or amount <= 0:
        return ()
    registered = greenery_ids()
    if not registered:
        return ()
    rnd = random.Random((seed ^ 0x6EE7) & 0xFFFFFFFF)
    points: List[GreeneryPoint] = []
    # Golden-angle azimuthal spread around outer collar (elevation 18..42 deg)
    # so greenery frames between/behind heads without crossing front faces.
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(amount):
        if greenery_type == "mixed":
            kind = registered[i % len(registered)]
        elif greenery_type in _BY_ID:
            kind = greenery_type
        else:
            kind = registered[0]
        spec = get_greenery(kind)
        pal = _tint_palette(spec.palette, tint)
        azimuth = i * golden + rnd.uniform(-0.22, 0.22)
        elevation = math.radians(rnd.uniform(18.0, 42.0))
        spec.generator(points, neck, azimuth, elevation, cap_radius, rnd, detail, pal)
    return tuple(points)
