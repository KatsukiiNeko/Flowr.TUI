"""Perspective camera used by the bouquet renderer.

The maths intentionally mirrors the reference project: yaw, then tilt about
the pivot, then a 1/(distance-z) perspective divide.  The horizontal scale is
doubled because a terminal cell is roughly twice as tall as it is wide.

Derived projection concepts from Ascii-Flower-Bouquet by Alish Sharma (MIT); see NOTICE.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

PIVOT_Y = 0.34
MIN_CAMERA_DISTANCE = 2.0
NEAR_EPSILON = 0.05


@dataclass(frozen=True)
class Camera:
    distance: float = 4.0
    tilt: float = 0.30

    def guarded_distance(self) -> float:
        return max(MIN_CAMERA_DISTANCE, self.distance)


@dataclass(frozen=True)
class Viewport:
    width: int
    height: int
    x: int = 0
    y: int = 0

    def scale(self) -> float:
        return max(1.0, min((self.height - 2) / 1.32, (self.width - 2) / 3.10))

    def center(self) -> Tuple[float, float]:
        scale = self.scale()
        return self.x + self.width / 2.0, self.y + 1.0 + 0.72 * scale


class Projector:
    """A projector with the frame's sine/cosine values pre-computed."""

    __slots__ = (
        "distance", "tilt", "scale", "cx", "cy", "ca", "sa", "ct", "st",
        "sx_scale",
    )

    def __init__(self, camera: Camera, viewport: Viewport, yaw: float) -> None:
        self.distance = camera.guarded_distance()
        self.tilt = camera.tilt
        self.scale = viewport.scale()
        self.cx, self.cy = viewport.center()
        self.sx_scale = self.scale * 2.0
        self.ca = math.cos(yaw)
        self.sa = math.sin(yaw)
        self.ct = math.cos(camera.tilt)
        self.st = math.sin(camera.tilt)

    def project_float(self, x: float, y: float, z: float):
        xr = x * self.ca - z * self.sa
        zr = x * self.sa + z * self.ca
        yp = y - PIVOT_Y
        yt = yp * self.ct - zr * self.st
        zt = yp * self.st + zr * self.ct
        denominator = self.distance - zt
        if denominator < NEAR_EPSILON:
            return None
        factor = self.distance / denominator
        return (
            self.cx + xr * factor * self.sx_scale,
            self.cy - yt * factor * self.scale,
            zt,
            factor,
        )

    def project(self, x: float, y: float, z: float):
        result = self.project_float(x, y, z)
        if result is None:
            return None
        px, py, zt, factor = result
        return int(px), int(py), zt, factor

    def rotate_normal(self, nx: float, ny: float, nz: float):
        nxr = nx * self.ca - nz * self.sa
        nzr = nx * self.sa + nz * self.ca
        nyt = ny * self.ct - nzr * self.st
        nzt = ny * self.st + nzr * self.ct
        return nxr, nyt, nzt

    def project_radius(self, radius: float, factor: float, aspect: float = 1.0):
        return (
            max(0.0, radius * factor * self.sx_scale * aspect),
            max(0.0, radius * factor * self.scale),
        )


def fit_scale(width: int, height: int) -> float:
    return max(1.0, min((height - 2) / 1.32, (width - 2) / 3.10))


def screen_bounds(projector: Projector, points) -> Optional[Tuple[int, int, int, int]]:
    """Debug helper: integer bounds of projected points."""
    xs = []
    ys = []
    for x, y, z in points:
        result = projector.project(x, y, z)
        if result is not None:
            xs.append(result[0])
            ys.append(result[1])
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)
