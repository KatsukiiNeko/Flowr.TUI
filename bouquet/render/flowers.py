"""Flower rasterisation into SampleBuffer, sprite caching, and LOD selection.

The renderer projects each head into square sample coordinates, picks a LOD
from head size in samples (and detail level), samples or blits the unit-disc
shape sprite, applies tonal jitter and depth cueing, and writes into SampleBuffer.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from ..flowers import colorways as c
from ..flowers.registry import (
    LOD_BLOB,
    LOD_FULL,
    LOD_SIMPLIFIED,
    L_CENTER,
    L_INNER,
    L_PETAL,
    L_PISTIL,
    L_SEPAL,
    L_STAMEN,
    Sample,
)
from ..geometry.camera import Camera, Projector, Viewport
from .buffer import CellBuffer
from .samples import (
    FLAG_FULL_LOD,
    FLAG_HEAD,
    GC_CENTER,
    GC_DENSE,
    GC_PETAL,
    GC_SEPAL,
    GC_STAMEN,
    HAS_NUMPY,
    TOKEN_TO_GLYPH_CLASS,
    SampleBuffer,
    apply_head_outlines,
)

if HAS_NUMPY:
    import numpy as _np  # type: ignore[import-not-found]

Clip = Tuple[int, int, int, int]
TAU = 2.0 * math.pi
PHASE_STEPS = 48

# Sprite cache: (variety_id, variant, lod, petal_grad, phase_step, grid_dim) -> tuple
_SPRITE_CACHE: Dict[Tuple[str, int, int, bool, int, int], tuple] = {}
_SPRITE_CACHE_LIMIT = 2048


class SampleProjector(Projector):
    """Projector into square SampleBuffer coordinates (sx_scale == scale)."""

    def __init__(self, camera: Camera, sample_w: int, sample_h: int, yaw: float) -> None:
        self.distance = camera.guarded_distance()
        self.tilt = camera.tilt
        self.scale = max(1.0, min((sample_h - 2) / 1.32, (sample_w - 2) / 1.60))
        self.cx = sample_w / 2.0
        self.cy = 1.0 + 0.72 * self.scale
        self.sx_scale = self.scale  # Square samples: 1:1 x/y scale!
        self.ca = math.cos(yaw)
        self.sa = math.sin(yaw)
        self.ct = math.cos(camera.tilt)
        self.st = math.sin(camera.tilt)


def lod_for(rx: float, ry: float, detail: int = 64) -> int:
    """LOD keyed by head size in samples and detail tier (DET-3)."""
    if rx < 1.1 or ry < 1.1:
        return LOD_BLOB
    if detail <= 32:
        return LOD_SIMPLIFIED
    if rx * 2.0 >= 7.0 and ry * 2.0 >= 5.0:
        return LOD_FULL
    if rx * 2.0 >= 3.5 and ry * 2.0 >= 2.5:
        return LOD_SIMPLIFIED
    return LOD_BLOB


def _layer_palette_index(layer: int, flower, sample_buf: SampleBuffer) -> int:
    if layer == L_SEPAL:
        return sample_buf.register_palette(c.GREENS)
    if layer in (L_CENTER, L_PISTIL):
        return sample_buf.register_palette(flower.colorway.center)
    if layer == L_STAMEN:
        return sample_buf.register_palette(flower.colorway.accent)
    return sample_buf.register_palette(flower.colorway.petals)


def _sample_to_gc(sample: Sample) -> Tuple[int, int]:
    if sample.glyph in TOKEN_TO_GLYPH_CLASS:
        return TOKEN_TO_GLYPH_CLASS[sample.glyph], 0
    if sample.layer == L_SEPAL:
        return GC_SEPAL, 0
    if sample.layer in (L_CENTER, L_PISTIL):
        return GC_CENTER, ord(sample.glyph[0]) if sample.glyph else ord("o")
    if sample.layer == L_STAMEN:
        return GC_STAMEN, ord(sample.glyph[0]) if sample.glyph else ord("*")
    return GC_PETAL, ord(sample.glyph[0]) if len(sample.glyph) == 1 else 0


def _build_sprite(
    variety,
    colorway,
    lod: int,
    petal_gradient: bool,
    phase_step: int,
    grid_dim: int,
):
    key = (variety.id, colorway.variant, lod, petal_gradient, phase_step, grid_dim)
    cached = _SPRITE_CACHE.get(key)
    if cached is not None:
        return cached

    phase = (phase_step / float(PHASE_STEPS)) * TAU
    if HAS_NUMPY:
        cov = _np.zeros((grid_dim, grid_dim), dtype=bool)
        bright = _np.zeros((grid_dim, grid_dim), dtype=_np.float64)
        z_off = _np.zeros((grid_dim, grid_dim), dtype=_np.float64)
        gc_arr = _np.zeros((grid_dim, grid_dim), dtype=_np.uint8)
        cc_arr = _np.zeros((grid_dim, grid_dim), dtype=_np.uint8)
        layer_arr = _np.zeros((grid_dim, grid_dim), dtype=_np.uint8)
    else:
        n = grid_dim * grid_dim
        cov = [False] * n
        bright = [0.0] * n
        z_off = [0.0] * n
        gc_arr = [0] * n
        cc_arr = [0] * n
        layer_arr = [0] * n

    for sy in range(grid_dim):
        dy = (sy + 0.5) / grid_dim * 2.30 - 1.15
        for sx in range(grid_dim):
            dx = (sx + 0.5) / grid_dim * 2.30 - 1.15
            sample = variety.shape(dx, dy, phase, lod, colorway)
            if sample is None:
                continue
            r = math.hypot(dx, dy)
            if lod == LOD_SIMPLIFIED and variety.has_center and r <= 0.24:
                b = 0.62
                layer = L_CENTER
                gc, cc = GC_CENTER, ord("@")
                off = 0.06
            else:
                b = sample.base + sample.shade
                if petal_gradient and sample.layer in (L_PETAL, L_INNER):
                    b += (min(1.0, r) - 0.55) * 0.45
                b = min(0.999, max(0.05, b))
                layer = sample.layer
                gc, cc = _sample_to_gc(sample)
                if layer in (L_CENTER, L_PISTIL):
                    off = 0.06
                elif layer == L_STAMEN:
                    off = 0.05
                elif layer == L_SEPAL:
                    off = 0.02
                else:
                    off = 0.04 * (1.0 - min(1.0, r))
            if HAS_NUMPY:
                cov[sy, sx] = True
                bright[sy, sx] = b
                z_off[sy, sx] = off
                gc_arr[sy, sx] = gc
                cc_arr[sy, sx] = cc
                layer_arr[sy, sx] = layer
            else:
                idx = sy * grid_dim + sx
                cov[idx] = True
                bright[idx] = b
                z_off[idx] = off
                gc_arr[idx] = gc
                cc_arr[idx] = cc
                layer_arr[idx] = layer

    entry = (cov, bright, z_off, gc_arr, cc_arr, layer_arr, grid_dim)
    if len(_SPRITE_CACHE) >= _SPRITE_CACHE_LIMIT:
        _SPRITE_CACHE.clear()
    _SPRITE_CACHE[key] = entry
    return entry


def rasterise_flower_heads(
    sample_buf: SampleBuffer,
    projector: Projector,
    flowers: Sequence,
    t: float,
    yaw: float,
    scale: float,
    settings,
    detail: int = 64,
    phase_scale: float = 0.7,
    head_id_offset: int = 1,
) -> List[Tuple[float, float, Sequence[int]]]:
    """Rasterise all flower heads into *sample_buf*; returns normalized positions for petals."""
    if scale <= 0.02:
        return []
    sw, sh = sample_buf.width, sample_buf.height
    dc_scale = max(0.0, min(1.0, getattr(settings, "depth_cue", 60) / 100.0))
    petal_grad = bool(getattr(settings, "petal_gradient", True))
    projected_heads: List[Tuple[float, float, Sequence[int]]] = []

    for idx, flower in enumerate(flowers):
        obj_id = head_id_offset + idx
        bob = 0.0
        if settings.bob:
            bob = 0.012 * math.sin(t * 1.7 + flower.seed)
        result = projector.project_float(
            flower.position[0], flower.position[1] + bob, flower.position[2]
        )
        if result is None:
            continue
        fx, fy, zt, factor = result
        if 0.0 <= fx < sw and 0.0 <= fy < sh:
            projected_heads.append((fx / sw, fy / sh, flower.colorway.petals))

        radius = flower.radius * scale
        rx, ry = projector.project_radius(radius, factor, flower.variety.aspect)
        if rx < 0.45 or ry < 0.45:
            continue
        lod = lod_for(rx, ry, detail)

        # LEG-4 depth cue: lerp(1.0, 0.55, depth01) scaled by depth_cue/100
        depth01 = min(1.0, max(0.0, (0.55 - zt) / 1.10))
        depth_mult = 1.0 - 0.45 * dc_scale * depth01
        jitter = getattr(flower, "tone_jitter", 0.0)

        if lod == LOD_BLOB:
            pid = sample_buf.register_palette(flower.colorway.petals)
            b = min(0.999, max(0.0, (0.68 + jitter) * depth_mult))
            glyph = flower.variety.blob_glyph
            sample_buf.plot(
                int(fx), int(fy), zt + 0.06, b, pid, GC_PETAL,
                char_code=ord(glyph[0]), obj_id=obj_id, flags=FLAG_HEAD,
            )
            continue

        phase = flower.seed + yaw * phase_scale
        phase_step = int(round(((phase % TAU) / TAU) * PHASE_STEPS)) % PHASE_STEPS
        max_diam = max(rx, ry) * 2.30
        grid_dim = min(72, max(16, int(((max_diam + 7) // 8) * 8)))

        cov, s_bright, s_zoff, s_gc, s_cc, s_layer, gdim = _build_sprite(
            flower.variety, flower.colorway, lod, petal_grad, phase_step, grid_dim
        )

        pal_by_layer = {
            L_PETAL: _layer_palette_index(L_PETAL, flower, sample_buf),
            L_INNER: _layer_palette_index(L_INNER, flower, sample_buf),
            L_CENTER: _layer_palette_index(L_CENTER, flower, sample_buf),
            L_PISTIL: _layer_palette_index(L_PISTIL, flower, sample_buf),
            L_STAMEN: _layer_palette_index(L_STAMEN, flower, sample_buf),
            L_SEPAL: _layer_palette_index(L_SEPAL, flower, sample_buf),
        }
        head_flags = FLAG_HEAD | (FLAG_FULL_LOD if lod == LOD_FULL else 0)

        left = max(0, int(fx - rx * 1.15))
        right = min(sw - 1, int(fx + rx * 1.15))
        top = max(0, int(fy - ry * 1.15))
        bottom = min(sh - 1, int(fy + ry * 1.15))
        if left > right or top > bottom:
            continue

        if HAS_NUMPY:
            rows_idx = _np.arange(top, bottom + 1, dtype=_np.float64)
            cols_idx = _np.arange(left, right + 1, dtype=_np.float64)
            dy = (rows_idx + 0.5 - fy) / ry
            dx = (cols_idx + 0.5 - fx) / rx
            iy = _np.clip(((dy + 1.15) / 2.30 * gdim).astype(_np.int32), 0, gdim - 1)
            ix = _np.clip(((dx + 1.15) / 2.30 * gdim).astype(_np.int32), 0, gdim - 1)
            valid_y = (dy >= -1.15) & (dy <= 1.15)
            valid_x = (dx >= -1.15) & (dx <= 1.15)

            sub_cov = cov[iy[:, None], ix[None, :]] & valid_y[:, None] & valid_x[None, :]
            if not _np.any(sub_cov):
                continue
            sub_z = zt + s_zoff[iy[:, None], ix[None, :]]
            z_slice = sample_buf.z[top:bottom + 1, left:right + 1]
            win = sub_cov & (sub_z > z_slice)
            if not _np.any(win):
                continue

            sub_b = _np.clip((s_bright[iy[:, None], ix[None, :]] + jitter) * depth_mult, 0.0, 0.999)
            sub_layer = s_layer[iy[:, None], ix[None, :]]
            sub_gc = s_gc[iy[:, None], ix[None, :]]
            sub_cc = s_cc[iy[:, None], ix[None, :]]

            # Map layer -> palette_id vectorized via lookup array
            lut = _np.array([pal_by_layer.get(l, pal_by_layer[L_PETAL]) for l in range(6)], dtype=_np.int16)
            sub_pid = lut[_np.clip(sub_layer, 0, 5)]

            z_slice[win] = sub_z[win]
            sample_buf.brightness[top:bottom + 1, left:right + 1][win] = sub_b[win]
            sample_buf.palette_id[top:bottom + 1, left:right + 1][win] = sub_pid[win]
            sample_buf.glyph_class[top:bottom + 1, left:right + 1][win] = sub_gc[win]
            sample_buf.char_code[top:bottom + 1, left:right + 1][win] = sub_cc[win]
            sample_buf.obj_id[top:bottom + 1, left:right + 1][win] = obj_id
            sample_buf.flags[top:bottom + 1, left:right + 1][win] = head_flags
        else:
            for row in range(top, bottom + 1):
                dy = (row + 0.5 - fy) / ry
                if dy < -1.15 or dy > 1.15:
                    continue
                iy = min(gdim - 1, max(0, int((dy + 1.15) / 2.30 * gdim)))
                for col in range(left, right + 1):
                    dx = (col + 0.5 - fx) / rx
                    if dx < -1.15 or dx > 1.15:
                        continue
                    ix = min(gdim - 1, max(0, int((dx + 1.15) / 2.30 * gdim)))
                    sidx = iy * gdim + ix
                    if not cov[sidx]:
                        continue
                    b = min(0.999, max(0.0, (s_bright[sidx] + jitter) * depth_mult))
                    pid = pal_by_layer.get(s_layer[sidx], pal_by_layer[L_PETAL])
                    sample_buf.plot(
                        col, row, zt + s_zoff[sidx], b, pid,
                        s_gc[sidx], s_cc[sidx], obj_id, head_flags,
                    )

    return projected_heads


def draw_flower_heads(
    buffer: CellBuffer,
    projector: Projector,
    flowers: Sequence,
    t: float,
    yaw: float,
    scale: float,
    settings,
    clip: Clip,
    ascii_mode: bool = False,
    phase_scale: float = 0.7,
) -> None:
    """Compatibility wrapper drawing heads directly into a CellBuffer."""
    from .resolvers import resolve

    x0, y0, x1, y1 = clip
    view_w = max(1, x1 - x0)
    view_h = max(1, y1 - y0)
    # Build a 1:1 SampleProjector matching CellBuffer scale for test compatibility
    sb = SampleBuffer(view_w, view_h * 2)
    # Map cell projector coordinates into sb (2x vertical samples so samples are square)
    sp = _CellAdapterProjector(projector, x0, y0)
    rasterise_flower_heads(sb, sp, flowers, t, yaw, scale, settings, detail=view_h * 2, phase_scale=phase_scale)
    apply_head_outlines(sb, cell_samples_y=2.0, enabled=getattr(settings, "outlines", True))
    resolve(sb, buffer, clip, style="ascii", truecolor=False, color_enabled=True, ascii_mode=ascii_mode)


class _CellAdapterProjector(Projector):
    """Projects into a 2x-vertical SampleBuffer matching a cell Projector."""

    def __init__(self, base: Projector, x0: int, y0: int) -> None:
        self.distance = base.distance
        self.tilt = base.tilt
        self.scale = base.scale * 2.0
        self.cx = base.cx - x0
        self.cy = (base.cy - y0) * 2.0
        self.sx_scale = base.sx_scale
        self.ca = base.ca
        self.sa = base.sa
        self.ct = base.ct
        self.st = base.st


def flower_bounds(projector: Projector, flower, scale: float):
    result = projector.project_float(*flower.position)
    if result is None:
        return None
    fx, fy, zt, factor = result
    rx, ry = projector.project_radius(flower.radius * scale, factor, flower.variety.aspect)
    return fx - rx, fy - ry, fx + rx, fy + ry, zt
