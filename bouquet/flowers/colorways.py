"""Reference, extended xterm-256 and interpolated truecolor palettes.

Palettes are ordered dark to light and indexed by brightness, exactly like
the reference bouquet.  Values are derived from Ascii-Flower-Bouquet by Alish
Sharma (MIT); see NOTICE.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Dict, Optional, Sequence, Tuple, Union

RGB = Tuple[int, int, int]
ColorValue = Union[None, int, RGB]

# Reference v1 xterm-256 tuples (kept exact for classic theme regression)
WHITE = (244, 248, 251, 254, 255, 231)
PINK = (125, 162, 168, 205, 211, 218, 225)
RED = (52, 88, 124, 160, 196, 203)
PURPLE = (54, 91, 97, 134, 140, 183)
YELLOW = (136, 178, 214, 220, 226, 229)
ORANGE = (130, 166, 202, 208, 214, 216)
GOLD_CENTER = (94, 136, 178, 214, 220)
DARK_CENTER = (52, 58, 94, 130, 136)
GREENS = (22, 28, 28, 34, 35, 71, 77, 114)
PAPER = (101, 144, 187, 223, 230, 231)
RIBBON = (88, 125, 161, 197, 204, 211)
HEART_COLORS = (161, 197, 204, 205, 211, 218)
MSG_COLORS = (161, 168, 205, 211, 218, 225, 218, 211, 205, 168)

# Extensions used by the v1 varieties
PEACH = (173, 180, 216, 223, 230, 231)
BLUSH = (174, 181, 218, 224, 225)
MAGENTA = (89, 90, 125, 162, 169, 205)
LILY_ORANGE = (130, 166, 202, 208, 214, 216)
PISTIL = (34, 35, 71, 77, 114)

# v2 extended xterm-256 palettes
BLUE = (17, 24, 67, 110, 153, 195)
SILVER = (240, 244, 247, 250, 253, 255)
ICE_BLUE = (67, 110, 153, 189, 195, 231)
RUST = (88, 124, 130, 166, 173, 180)
BURGUNDY = (52, 88, 89, 125, 131, 167)
GOLD = (94, 136, 172, 178, 214, 220)
CORAL = (167, 173, 174, 209, 210, 216)
LILAC = (97, 134, 140, 176, 183, 189)
CREAM = (180, 187, 223, 229, 230, 231)
EUCALYPTUS = (23, 29, 30, 66, 72, 108, 151)
FERN = (22, 28, 29, 34, 35, 71, 77)
WHEAT = (136, 143, 179, 186, 222, 229)

SOLID_MESSAGE_COLORS = (
    ("Pink", 205),
    ("Rose", 211),
    ("Blush", 218),
    ("Paper", 231),
    ("Gold", 220),
    ("Amber", 214),
    ("Crimson", 196),
    ("Violet", 183),
    ("Mist", 244),
    ("Ice", 153),
)

# ---------------------------------------------------------------------------
# Truecolor RGB anchor ramps & xterm-256 LUT
# ---------------------------------------------------------------------------

_CUBE_LEVELS = (0, 95, 135, 175, 215, 255)


def _xterm_palette() -> Tuple[RGB, ...]:
    table = []
    # Indices 0..15: approximate standard ANSI colors (only indices 16..255 used by LUT)
    ansi16 = (
        (0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0),
        (0, 0, 128), (128, 0, 128), (0, 128, 128), (192, 192, 192),
        (128, 128, 128), (255, 0, 0), (0, 255, 0), (255, 255, 0),
        (0, 0, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255),
    )
    table.extend(ansi16)
    for r in _CUBE_LEVELS:
        for g in _CUBE_LEVELS:
            for b in _CUBE_LEVELS:
                table.append((r, g, b))
    for i in range(24):
        v = 8 + i * 10
        table.append((v, v, v))
    return tuple(table)


XTERM_256_RGB: Tuple[RGB, ...] = _xterm_palette()


def hex_to_rgb(value: str) -> RGB:
    h = value.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


@lru_cache(maxsize=4096)
def nearest_xterm256(rgb: RGB) -> int:
    """Nearest xterm-256 index (from 16..255) for an RGB tuple."""
    r, g, b = rgb
    best_idx = 16
    best_dist = 1e12
    for idx in range(16, 256):
        pr, pg, pb = XTERM_256_RGB[idx]
        dr = r - pr
        dg = g - pg
        db = b - pb
        # Perceptual weighting (redmean-like)
        dist = 2.0 * dr * dr + 4.0 * dg * dg + 3.0 * db * db
        if dist < best_dist:
            best_dist = dist
            best_idx = idx
    return best_idx


def interpolate_anchors(anchors: Sequence[Union[str, RGB]], steps: int = 32) -> Tuple[RGB, ...]:
    """Interpolate hex or RGB anchors into *steps* smooth RGB stops."""
    pts = [hex_to_rgb(a) if isinstance(a, str) else a for a in anchors]
    if not pts:
        return ((255, 255, 255),) * steps
    if len(pts) == 1 or steps <= 1:
        return (pts[0],) * max(1, steps)
    out = []
    segs = len(pts) - 1
    for i in range(steps):
        pos = (i / (steps - 1)) * segs
        idx = min(segs - 1, int(pos))
        frac = pos - idx
        r0, g0, b0 = pts[idx]
        r1, g1, b1 = pts[idx + 1]
        out.append((
            int(round(r0 + (r1 - r0) * frac)),
            int(round(g0 + (g1 - g0) * frac)),
            int(round(b0 + (b1 - b0) * frac)),
        ))
    return tuple(out)


def _ramp_from_256(indices: Sequence[int], steps: int = 32) -> Tuple[RGB, ...]:
    return interpolate_anchors([XTERM_256_RGB[i] for i in indices], steps)


# Wrap style anchor ramps (WRP-3)
WRAP_ANCHORS: Dict[str, Tuple[str, ...]] = {
    "kraft": ("#6b5338", "#a98963", "#cdb08a", "#efe0c4"),
    "cream": ("#8a7f6a", "#c9bda3", "#ece3d0", "#fffaf0"),
    "blush": ("#7d565e", "#b5838d", "#e5b8c0", "#fbe6ea"),
    "sage": ("#4d5e52", "#7a9180", "#a8bfb0", "#d8e6dc"),
    "black": ("#1c1c20", "#36363d", "#54545e", "#7a7a86"),
}

WRAP_STYLES: Tuple[str, ...] = tuple(WRAP_ANCHORS.keys())
WRAP_RAMPS_RGB: Dict[str, Tuple[RGB, ...]] = {
    name: interpolate_anchors(stops, 32) for name, stops in WRAP_ANCHORS.items()
}
WRAP_PALETTES_256: Dict[str, Tuple[int, ...]] = {
    name: tuple(nearest_xterm256(rgb) for rgb in ramp[::5])
    for name, ramp in WRAP_RAMPS_RGB.items()
}
# Ensure paper classic compatibility when wrap == "classic_paper"
WRAP_PALETTES_256["classic_paper"] = PAPER
WRAP_RAMPS_RGB["classic_paper"] = _ramp_from_256(PAPER, 32)

# Named RGB anchor ramps for flower palettes & components
PALETTE_ANCHORS: Dict[str, Tuple[str, ...]] = {
    "BLUE": ("#1f3a5f", "#4f7cac", "#8fb8de", "#dbeaf7"),
    "ICE_BLUE": ("#42638a", "#78a6d4", "#b4d6f4", "#eaf5ff"),
    "SILVER": ("#626872", "#959ca6", "#c6ccd4", "#f0f3f7"),
    "EUCALYPTUS": ("#2f4f45", "#5f8a7a", "#8fb5a3", "#c5ddd0"),
    "FERN": ("#1b3b24", "#2e6338", "#488f50", "#7cc27e"),
    "WHEAT": ("#8a6d2f", "#b89648", "#dbc078", "#f3e3b0"),
    "RUST": ("#6b2416", "#a64024", "#cf6b42", "#e89d76"),
    "BURGUNDY": ("#4a1222", "#7a1e38", "#a83652", "#d46a82"),
    "GOLD": ("#755110", "#b07d1e", "#e0ad38", "#fae078"),
    "CORAL": ("#9c3b36", "#d15e54", "#f08a7a", "#ffc2b5"),
    "LILAC": ("#5c4375", "#8c6aa8", "#ba9bd4", "#e3d1f5"),
    "CREAM": ("#998e7a", "#c9bda3", "#ece3d0", "#fffaf0"),
}

# Precomputed 32-step RGB ramps keyed by id(tuple) or palette name
_RGB_RAMP_CACHE: Dict[Tuple[int, ...], Tuple[RGB, ...]] = {}
_LUT_256_CACHE: Dict[Tuple[RGB, ...], Tuple[int, ...]] = {}

for _name, _stops in PALETTE_ANCHORS.items():
    _rgb = interpolate_anchors(_stops, 32)
    _pal = globals().get(_name)
    if _pal is not None:
        _RGB_RAMP_CACHE[tuple(_pal)] = _rgb


def rgb_ramp_for(palette: Sequence[int]) -> Tuple[RGB, ...]:
    """Return a 32-step RGB ramp for any xterm-256 palette tuple."""
    key = tuple(palette)
    cached = _RGB_RAMP_CACHE.get(key)
    if cached is not None:
        return cached
    ramp = _ramp_from_256(key, 32)
    _RGB_RAMP_CACHE[key] = ramp
    return ramp


def lut256_for_rgb_ramp(ramp: Tuple[RGB, ...]) -> Tuple[int, ...]:
    """Cached nearest xterm-256 index LUT for an RGB ramp."""
    cached = _LUT_256_CACHE.get(ramp)
    if cached is not None:
        return cached
    lut = tuple(nearest_xterm256(rgb) for rgb in ramp)
    _LUT_256_CACHE[ramp] = lut
    return lut


def sample_palette(
    palette: Sequence[int],
    brightness: float,
    truecolor: bool = False,
    rgb_ramp: Optional[Tuple[RGB, ...]] = None,
) -> ColorValue:
    """Resolve brightness in [0, 1) to an xterm-256 index or RGB tuple."""
    b = min(0.999, max(0.0, brightness))
    if truecolor:
        ramp = rgb_ramp if rgb_ramp is not None else rgb_ramp_for(palette)
        return ramp[min(len(ramp) - 1, int(b * len(ramp)))]
    if not palette:
        return 245
    return palette[min(len(palette) - 1, int(b * len(palette)))]
