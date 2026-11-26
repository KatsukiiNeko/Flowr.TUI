"""Internal square-sample canvas (SampleBuffer) and post-processing.

The renderer projects scene geometry and flower heads into a resolution-
independent SampleBuffer (height = detail in {32, 64, 128, 256}), applies
object-id outlines (contact shadow + rim), and passes the buffer to a style
resolver.  Uses NumPy when installed and falls back cleanly to pure Python.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

try:
    import numpy as _np  # type: ignore[import-not-found]
    HAS_NUMPY = True
except ImportError:
    _np = None
    HAS_NUMPY = False

from ..flowers.colorways import RGB, rgb_ramp_for

# Glyph classes stored per sample
GC_EMPTY = 0
GC_PETAL = 1
GC_SOFT = 2
GC_CUP = 3
GC_STAR = 4
GC_DENSE = 5
GC_POPPY = 6
GC_SEPAL = 7
GC_STEM = 8
GC_LEAF = 9
GC_PAPER = 10
GC_RIBBON = 11
GC_GREENERY = 12
GC_BABY = 13
GC_SPARKLE = 14
GC_CENTER = 15
GC_STAMEN = 16
GC_OVERRIDE = 17

GLYPH_CLASS_TO_TOKEN: Dict[int, str] = {
    GC_PETAL: "petal",
    GC_SOFT: "soft",
    GC_CUP: "cup",
    GC_STAR: "star",
    GC_DENSE: "dense",
    GC_POPPY: "poppy",
    GC_SEPAL: "sepal",
    GC_STEM: "shade",
    GC_LEAF: "shade",
    GC_PAPER: "shade",
    GC_RIBBON: "shade",
    GC_GREENERY: "greenery",
    GC_CENTER: "center",
    GC_STAMEN: "stamen",
}

TOKEN_TO_GLYPH_CLASS: Dict[str, int] = {
    "petal": GC_PETAL,
    "soft": GC_SOFT,
    "cup": GC_CUP,
    "star": GC_STAR,
    "dense": GC_DENSE,
    "poppy": GC_POPPY,
    "sparse": GC_STAR,
    "sepal": GC_SEPAL,
    "greenery": GC_GREENERY,
}

# Sample flags
FLAG_HEAD = 1
FLAG_RIM = 2
FLAG_CONTACT = 4
FLAG_FULL_LOD = 8

EMPTY_Z = -1e9


class SampleBuffer:
    """Square-sample z-buffer with palette, glyph class, object id and flags."""

    __slots__ = (
        "width", "height", "palettes", "_pal_lookup",
        "z", "brightness", "palette_id", "glyph_class", "char_code", "obj_id", "flags",
    )

    def __init__(self, width: int, height: int) -> None:
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.palettes: List[Tuple[Sequence[int], Optional[Tuple[RGB, ...]]]] = [((245,), None)]
        self._pal_lookup: Dict[Tuple[int, ...], int] = {(245,): 0}
        if HAS_NUMPY:
            shape = (self.height, self.width)
            # float64 matches the pure-Python z list, keeping tie-breaking and
            # therefore the rendered glyph/colour identical with or without NumPy.
            self.z = _np.full(shape, EMPTY_Z, dtype=_np.float64)
            self.brightness = _np.zeros(shape, dtype=_np.float64)
            self.palette_id = _np.zeros(shape, dtype=_np.int16)
            self.glyph_class = _np.zeros(shape, dtype=_np.uint8)
            self.char_code = _np.zeros(shape, dtype=_np.uint8)
            self.obj_id = _np.zeros(shape, dtype=_np.int32)
            self.flags = _np.zeros(shape, dtype=_np.uint8)
        else:
            n = self.width * self.height
            self.z = [EMPTY_Z] * n
            self.brightness = [0.0] * n
            self.palette_id = [0] * n
            self.glyph_class = [0] * n
            self.char_code = [0] * n
            self.obj_id = [0] * n
            self.flags = [0] * n

    def register_palette(
        self,
        palette: Sequence[int],
        rgb_ramp: Optional[Tuple[RGB, ...]] = None,
    ) -> int:
        key = tuple(palette)
        existing = self._pal_lookup.get(key)
        if existing is not None and rgb_ramp is None:
            return existing
        pid = len(self.palettes)
        self.palettes.append((key, rgb_ramp if rgb_ramp is not None else rgb_ramp_for(key)))
        if rgb_ramp is None:
            self._pal_lookup[key] = pid
        return pid

    def plot(
        self,
        sx: int,
        sy: int,
        z: float,
        brightness: float,
        palette_id: int,
        glyph_class: int,
        char_code: int = 0,
        obj_id: int = 0,
        flags: int = 0,
    ) -> None:
        if not (0 <= sx < self.width and 0 <= sy < self.height):
            return
        if HAS_NUMPY:
            if z > self.z[sy, sx]:
                self.z[sy, sx] = z
                self.brightness[sy, sx] = brightness
                self.palette_id[sy, sx] = palette_id
                self.glyph_class[sy, sx] = glyph_class
                self.char_code[sy, sx] = char_code
                self.obj_id[sy, sx] = obj_id
                self.flags[sy, sx] = flags
        else:
            idx = sy * self.width + sx
            if z > self.z[idx]:
                self.z[idx] = z
                self.brightness[idx] = brightness
                self.palette_id[idx] = palette_id
                self.glyph_class[idx] = glyph_class
                self.char_code[idx] = char_code
                self.obj_id[idx] = obj_id
                self.flags[idx] = flags


def apply_head_outlines(
    buf: SampleBuffer,
    cell_samples_y: float = 1.0,
    enabled: bool = True,
) -> None:
    """LEG-3: contact shadow on farther overlapping head + 1-step silhouette rim."""
    if not enabled or buf.width < 2 or buf.height < 2:
        return
    step = max(1, int(round(cell_samples_y)))
    if HAS_NUMPY:
        _apply_outlines_numpy(buf, step)
    else:
        _apply_outlines_python(buf, step)


def _apply_outlines_numpy(buf: SampleBuffer, step: int) -> None:
    np = _np
    oid = buf.obj_id
    z = buf.z
    is_head = (buf.flags & FLAG_HEAD) != 0
    if not np.any(is_head):
        return
    h, w = oid.shape

    # 1. Silhouette rim: any 4-neighbor (at step 1) has different obj_id and is not nearer
    rim = np.zeros((h, w), dtype=bool)
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        ys = slice(max(0, -dy), h - max(0, dy))
        xs = slice(max(0, -dx), w - max(0, dx))
        ny = slice(max(0, dy), h - max(0, -dy))
        nx = slice(max(0, dx), w - max(0, -dx))
        diff = oid[ys, xs] != oid[ny, nx]
        not_nearer = z[ny, nx] <= z[ys, xs]
        rim[ys, xs] |= is_head[ys, xs] & diff & not_nearer
    # Border samples of canvas also count if head reaches edge
    if h >= 1:
        rim[0, :] |= is_head[0, :]
        rim[-1, :] |= is_head[-1, :]
    if w >= 1:
        rim[:, 0] |= is_head[:, 0]
        rim[:, -1] |= is_head[:, -1]

    # 2. Contact shadow: neighbor within *step* is another nearer head
    contact = np.zeros((h, w), dtype=bool)
    offsets = []
    for dy in (-step, 0, step):
        for dx in (-step, 0, step):
            if dy != 0 or dx != 0:
                offsets.append((dy, dx))
    for dy, dx in offsets:
        if abs(dy) >= h or abs(dx) >= w:
            continue
        ys = slice(max(0, -dy), h - max(0, dy))
        xs = slice(max(0, -dx), w - max(0, dx))
        ny = slice(max(0, dy), h - max(0, -dy))
        nx = slice(max(0, dx), w - max(0, -dx))
        other_head = is_head[ny, nx] & (oid[ny, nx] != oid[ys, xs]) & (z[ny, nx] > z[ys, xs])
        contact[ys, xs] |= is_head[ys, xs] & other_head

    # Darken contact shadow (~2 palette steps) and rim (~1 palette step)
    buf.brightness[rim] = np.maximum(0.0, buf.brightness[rim] - 0.14)
    buf.flags[rim] |= FLAG_RIM
    buf.brightness[contact] = np.maximum(0.0, buf.brightness[contact] - 0.28)
    buf.flags[contact] |= FLAG_CONTACT


def _apply_outlines_python(buf: SampleBuffer, step: int) -> None:
    w, h = buf.width, buf.height
    oid = buf.obj_id
    z = buf.z
    flags = buf.flags
    bright = buf.brightness
    rim_mask = [False] * (w * h)
    contact_mask = [False] * (w * h)

    for row in range(h):
        base = row * w
        for col in range(w):
            idx = base + col
            if not (flags[idx] & FLAG_HEAD):
                continue
            my_id = oid[idx]
            my_z = z[idx]
            is_rim = row == 0 or row == h - 1 or col == 0 or col == w - 1
            if not is_rim:
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nidx = (row + dy) * w + (col + dx)
                    if oid[nidx] != my_id and z[nidx] <= my_z:
                        is_rim = True
                        break
            rim_mask[idx] = is_rim

            in_shadow = False
            for dy in (-step, 0, step):
                nr = row + dy
                if not (0 <= nr < h):
                    continue
                for dx in (-step, 0, step):
                    if dy == 0 and dx == 0:
                        continue
                    nc = col + dx
                    if not (0 <= nc < w):
                        continue
                    nidx = nr * w + nc
                    if (flags[nidx] & FLAG_HEAD) and oid[nidx] != my_id and z[nidx] > my_z:
                        in_shadow = True
                        break
                if in_shadow:
                    break
            contact_mask[idx] = in_shadow

    for idx in range(w * h):
        if rim_mask[idx]:
            bright[idx] = max(0.0, bright[idx] - 0.14)
            flags[idx] |= FLAG_RIM
        if contact_mask[idx]:
            bright[idx] = max(0.0, bright[idx] - 0.28)
            flags[idx] |= FLAG_CONTACT
