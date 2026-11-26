"""Lambert shading, glyph ramps and palette lookup.

The light direction, glyph ramps and brightness formula are derived from
Ascii-Flower-Bouquet by Alish Sharma (MIT).  See NOTICE.
"""

from __future__ import annotations

import math
from typing import Dict, Sequence

SHADE = ".:-=+*%@"
PETAL_SHADE = ".:-=+*"

# Per-glyph-class ramps (LEG-5): #, @ and % are reserved for centres/accents/dense cores.
GLYPH_RAMPS: Dict[str, str] = {
    "petal": ".:-=+*",
    "soft": ".':~+*",
    "cup": ",:-=+*",
    "star": ".'-~=+*",
    "dense": ",:;~=+",
    "poppy": ".':~=+*",
    "sepal": ".:-=+",
    "sparse": ".:-=+*",
    "greenery": ",~;'",
}

_L = (-0.45, 0.6, 0.66)
_length = math.sqrt(sum(value * value for value in _L))
LX, LY, LZ = (value / _length for value in _L)


def brightness(nx: float, ny: float, nz: float, tone: float = 0.0,
               two_sided: bool = False) -> float:
    dot = nx * LX + ny * LY + nz * LZ
    if two_sided and dot < 0.0:
        dot = -dot * 0.55
    return min(0.999, max(0.0, 0.25 + 0.75 * max(0.0, dot) + tone))


def ramp_char(value: float, ramp: str = SHADE) -> str:
    index = min(len(ramp) - 1, max(0, int(value * len(ramp))))
    return ramp[index]


def sample_ramp_char(glyph_token: str, value: float, is_sepal: bool = False) -> str:
    if is_sepal:
        ramp = GLYPH_RAMPS["sepal"]
        return ramp_char(value, ramp)
    ramp = GLYPH_RAMPS.get(glyph_token)
    if ramp is not None:
        # Stretch mid-range petal brightness across the full glyph ramp for crisp texture
        stretched = min(0.999, max(0.0, (value - 0.22) / 0.66))
        return ramp_char(stretched, ramp)
    return glyph_token


def palette_color(value: float, palette: Sequence[int]) -> int:
    if not palette:
        return 245
    index = min(len(palette) - 1, max(0, int(value * len(palette))))
    return palette[index]


def mix_brightness(base: float, delta: float) -> float:
    return min(0.999, max(0.0, base + delta))
