"""Small vector helpers used by the scene and camera."""

from __future__ import annotations

import math
from typing import Tuple

Vec3 = Tuple[float, float, float]


def norm(v: Vec3) -> Vec3:
    length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / length, v[1] / length, v[2] / length)


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def add_scaled(p: Vec3, d: Vec3, k: float) -> Vec3:
    return (p[0] + d[0] * k, p[1] + d[1] * k, p[2] + d[2] * k)


def basis(axis: Vec3) -> Tuple[Vec3, Vec3]:
    helper = (0.0, 1.0, 0.0) if abs(axis[1]) < 0.9 else (1.0, 0.0, 0.0)
    u = norm(cross(helper, axis))
    return u, cross(axis, u)


def clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value
