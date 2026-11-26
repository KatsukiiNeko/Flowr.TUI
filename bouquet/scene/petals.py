"""Falling petals shed from visible flower heads (FX-6).

Follows the same lifecycle rules as Hearts: dt-based, frame-rate independent,
lowering the count only marks surplus petals as retiring so none vanish mid-air,
and drawn behind the bouquet so heads are never obscured.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from ..flowers import colorways as c
from ..flowers.colorways import ColorValue, sample_palette

PETAL_GLYPHS = (",", "'", "~", "*")


@dataclass
class FallingPetal:
    x: float          # normalized [0, 1] viewport x
    y: float          # normalized [0, 1] viewport y
    vy: float         # downward speed (fraction of viewport per second)
    wobble_amp: float
    wobble_freq: float
    phase: float
    spin_speed: float
    palette: Sequence[int]
    retiring: bool = False


class PetalFall:
    def __init__(self, target: int = 8, seed: int = 21) -> None:
        self.target = max(0, min(40, int(target)))
        self._rng = random.Random((seed ^ 0x5E7A1) & 0xFFFFFFFF)
        self.items: List[FallingPetal] = []
        self._spawn_pool: List[Tuple[float, float, Sequence[int]]] = []
        self._spawn(self.target, initial=True)

    @property
    def active(self) -> int:
        return sum(1 for item in self.items if not item.retiring)

    def set_spawn_sources(self, sources: Sequence[Tuple[float, float, Sequence[int]]]) -> None:
        """Record normalized (nx, ny, palette) positions of visible heads from last frame."""
        if sources:
            self._spawn_pool = list(sources)

    def set_target(self, target: int) -> None:
        self.target = max(0, min(40, int(target)))
        surplus = max(0, self.active - self.target)
        for item in self.items:
            if surplus == 0:
                break
            if not item.retiring:
                item.retiring = True
                surplus -= 1
        self._spawn(max(0, self.target - self.active), initial=False)

    def _pick_source(self, initial: bool) -> Tuple[float, float, Sequence[int]]:
        if self._spawn_pool:
            nx, ny, pal = self._rng.choice(self._spawn_pool)
            return (
                max(0.05, min(0.95, nx + self._rng.uniform(-0.04, 0.04))),
                ny if not initial else self._rng.uniform(ny, 0.95),
                pal,
            )
        return (
            self._rng.uniform(0.25, 0.75),
            self._rng.uniform(0.10, 0.90) if initial else self._rng.uniform(0.05, 0.35),
            c.PINK,
        )

    def _new_petal(self, initial: bool = False) -> FallingPetal:
        nx, ny, pal = self._pick_source(initial)
        return FallingPetal(
            x=nx,
            y=ny,
            vy=self._rng.uniform(0.045, 0.095),
            wobble_amp=self._rng.uniform(0.012, 0.030),
            wobble_freq=self._rng.uniform(1.4, 2.8),
            phase=self._rng.uniform(0.0, 6.283),
            spin_speed=self._rng.uniform(1.5, 3.5),
            palette=pal,
        )

    def _spawn(self, count: int, initial: bool = False) -> None:
        for _ in range(max(0, count)):
            self.items.append(self._new_petal(initial=initial))

    def update(self, dt: float, t: float) -> None:
        if dt <= 0:
            return
        for item in self.items:
            item.y += item.vy * dt
        kept: List[FallingPetal] = []
        for item in self.items:
            if item.y <= 1.0:
                kept.append(item)
                continue
            if item.retiring:
                continue
            kept.append(self._new_petal(initial=False))
        self.items = kept
        self.set_target(self.target)

    def positions(
        self,
        cols: int,
        rows: int,
        t: float,
        truecolor: bool = False,
    ):
        for item in self.items:
            if item.y < 0.0 or item.y >= 1.0:
                continue
            x_norm = item.x + item.wobble_amp * math.sin(t * item.wobble_freq + item.phase)
            col = int(x_norm * cols)
            row = int(item.y * rows)
            if not (0 <= col < cols and 0 <= row < rows):
                continue
            # Fade brightness near the bottom edge (y > 0.78)
            fade = 1.0 if item.y <= 0.78 else max(0.08, 1.0 - (item.y - 0.78) / 0.22)
            brightness = 0.72 * fade
            color: ColorValue = sample_palette(item.palette, brightness, truecolor=truecolor)
            glyph_idx = int(t * item.spin_speed + item.phase) % len(PETAL_GLYPHS)
            yield col, row, PETAL_GLYPHS[glyph_idx], color

    def advance(self, seconds: float, steps_per_second: int = 24) -> None:
        if seconds <= 0:
            return
        dt = 1.0 / max(1, steps_per_second)
        steps = int(round(seconds * steps_per_second))
        t = 0.0
        for _ in range(steps):
            t += dt
            self.update(dt, t)
