"""Falling hearts.

Hearts are born above the viewport, fall slowly, and are retired only after
they leave the bottom, so lowering the count never makes a heart pop out on
screen. All randomness comes from one seeded generator for reproducible
snapshots. The rising screen-space particle concept derives from Ascii-Flower-Bouquet
by Alish Sharma (MIT); see NOTICE.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List

from ..flowers import colorways as c


@dataclass
class Heart:
    x: float
    y: float
    speed: float
    phase: float
    color: int
    retiring: bool = False


class Hearts:
    def __init__(self, target: int = 18, seed: int = 21) -> None:
        self.target = max(0, min(60, int(target)))
        self._rng = random.Random((seed ^ 0x48E417) & 0xFFFFFFFF)
        self.items: List[Heart] = []
        self._spawn(self.target)

    @property
    def active(self) -> int:
        return sum(1 for heart in self.items if not heart.retiring)

    def set_target(self, target: int) -> None:
        self.target = max(0, min(60, int(target)))
        surplus = max(0, self.active - self.target)
        for heart in self.items:
            if surplus == 0:
                break
            if not heart.retiring:
                heart.retiring = True
                surplus -= 1
        self._spawn(max(0, self.target - self.active))

    def _spawn(self, count: int) -> None:
        for _ in range(max(0, count)):
            self.items.append(Heart(
                x=self._rng.random(),
                y=1.0 + self._rng.random(),
                speed=self._rng.uniform(0.03, 0.08),
                phase=self._rng.uniform(0.0, 6.28),
                color=self._rng.choice(c.HEART_COLORS),
            ))

    def _new_heart(self) -> Heart:
        return Heart(
            x=self._rng.random(),
            y=1.0 + self._rng.random() * 0.4,
            speed=self._rng.uniform(0.03, 0.08),
            phase=self._rng.uniform(0.0, 6.28),
            color=self._rng.choice(c.HEART_COLORS),
        )

    def update(self, dt: float, t: float) -> None:
        if dt <= 0:
            return
        for heart in self.items:
            heart.y -= heart.speed * dt
        kept: List[Heart] = []
        for heart in self.items:
            if heart.y >= 0.0:
                kept.append(heart)
                continue
            if heart.retiring:
                continue
            kept.append(self._new_heart())
        self.items = kept
        self.set_target(self.target)

    def positions(self, cols: int, rows: int, t: float):
        for heart in self.items:
            col = int((heart.x + 0.015 * math.sin(t * 1.2 + heart.phase)) * cols) % max(1, cols)
            row = int(heart.y * rows)
            yield col, row, heart.color

    def advance(self, seconds: float, steps_per_second: int = 24) -> None:
        """Deterministic stepping used by snapshots and tests."""
        if seconds <= 0:
            return
        dt = 1.0 / max(1, steps_per_second)
        steps = int(round(seconds * steps_per_second))
        t = 0.0
        for _ in range(steps):
            t += dt
            self.update(dt, t)
