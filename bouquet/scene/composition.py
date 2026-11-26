"""Composition: which flower goes where, recommended density, and cap layout.

Classic preserves the registry-order interleaved sequence (8 daisy, 2 tulip).
For general counts, a wider Fibonacci-sphere cap spreads heads across elevation
rings so individual varieties remain identifiable inside full bouquets.
"""

from __future__ import annotations

import math
import random
from typing import List, Sequence, Tuple

from ..config.settings import MAX_FLOWERS, VARIETY_IDS, Settings
from ..geometry.camera import Viewport

Vec3 = Tuple[float, float, float]
GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))
CENTER = (0.0, 0.22, 0.0)
BASE_DISTANCE = 0.68


def recommended_flower_count(
    viewport: Viewport,
    detail: str = "auto",
    style: str = "ascii",
) -> int:
    """Recommended head count for readable spacing at the given viewport/detail/style."""
    scale = viewport.scale()
    # Base count scales smoothly with viewport size: ~10 at 80x24, ~12 at 120x40, ~16 at 200x60
    rec = 6.5 + 0.22 * scale
    if detail == "32" and style == "ascii":
        rec -= 1.0
    elif style in ("half", "braille"):
        rec += 1.0
    return max(6, min(MAX_FLOWERS, int(round(rec))))


def flower_sequence(settings: Settings) -> List[str]:
    counts = {variety_id: max(0, settings.count(variety_id)) for variety_id in VARIETY_IDS}
    total = sum(counts.values())
    if total <= 0:
        return ["daisy"]
    layout = settings.layout
    if layout == "clustered":
        return [variety_id for variety_id in VARIETY_IDS for _ in range(counts[variety_id])]
    if layout == "random":
        sequence = [variety_id for variety_id in VARIETY_IDS for _ in range(counts[variety_id])]
        random.Random(settings.seed ^ 0x5EED).shuffle(sequence)
        return sequence
    # Interleaved: evenly spread each variety, in registry order.
    slots: List[str] = [""] * total
    for variety_id in VARIETY_IDS:
        count = counts[variety_id]
        if not count:
            continue
        for k in range(count):
            preferred = min(total - 1, int(math.ceil((k + 0.5) * total / count)))
            index = _nearest_free(slots, preferred)
            slots[index] = variety_id
    return slots


def _nearest_free(slots: Sequence[str], preferred: int) -> int:
    if not slots[preferred]:
        return preferred
    total = len(slots)
    for distance in range(1, total + 1):
        for candidate in (preferred - distance, preferred + distance):
            if 0 <= candidate < total and not slots[candidate]:
                return candidate
    return preferred


def head_distance(total: int) -> float:
    if total == 10:
        return BASE_DISTANCE
    return BASE_DISTANCE * min(1.26, max(0.84, (total / 10.0) ** 0.20))


def head_scale(total: int) -> float:
    return min(1.08, max(0.50, (10.0 / max(1, total)) ** 0.28))


def head_positions(total: int, rnd: random.Random) -> List[Tuple[Vec3, Vec3]]:
    """Fibonacci-sphere cap positions, consuming exactly one RNG draw per head."""
    distance = head_distance(total)
    heads: List[Tuple[Vec3, Vec3]] = []
    for index in range(total):
        if total == 1:
            elevation = math.radians(88.0)
            azimuth = 0.0
        else:
            # Spread down to ~18 deg elevation for clear separation across rings
            frac = (index + 0.25) / (total - 0.5)
            elevation = math.radians(87.0 - 69.0 * math.sqrt(min(1.0, max(0.0, frac))))
            azimuth = index * GOLDEN_ANGLE
        direction = (
            math.cos(elevation) * math.cos(azimuth),
            math.sin(elevation),
            math.cos(elevation) * math.sin(azimuth),
        )
        reach = distance * rnd.uniform(0.94, 1.06)
        position = (
            CENTER[0] + direction[0] * reach,
            CENTER[1] + direction[1] * reach,
            CENTER[2] + direction[2] * reach,
        )
        length = math.sqrt(sum(value * value for value in direction)) or 1.0
        heads.append((position, tuple(value / length for value in direction)))  # type: ignore[arg-type]
    return heads


def flower_plan(settings: Settings) -> List[Tuple[str, int]]:
    """Expand the sequence into (variety, colourway index) pairs."""
    from ..flowers import get_variety

    sequence = flower_sequence(settings)
    used = {variety_id: 0 for variety_id in VARIETY_IDS}
    plan: List[Tuple[str, int]] = []
    for variety_id in sequence:
        chosen = settings.colorway(variety_id)
        if chosen < 0:
            chosen = used.get(variety_id, 0)
            used[variety_id] = chosen + 1
        spec = get_variety(variety_id)
        chosen %= len(spec.colorways)
        plan.append((variety_id, chosen))
    return plan


def themed_shuffle_counts(theme_name: str, rec_count: int, seed: int) -> dict[str, int]:
    """Build a theme-aware random flower composition within *rec_count*."""
    from ..config.themes import get_theme, preferred_varieties_for_theme

    theme = get_theme(theme_name)
    preferred = list(preferred_varieties_for_theme(theme))
    rng = random.Random(seed ^ 0xB007)
    target = max(4, min(MAX_FLOWERS, rng.randint(max(4, rec_count - 3), rec_count)))
    counts = {vid: 0 for vid in VARIETY_IDS}
    n_types = min(len(preferred), rng.randint(3, min(6, len(preferred))))
    chosen_types = rng.sample(preferred, n_types)
    for i in range(target):
        vid = chosen_types[i % len(chosen_types)] if i < len(chosen_types) else rng.choice(chosen_types)
        counts[vid] += 1
    return counts


def total_flowers(settings: Settings) -> int:
    return settings.total_flowers()
