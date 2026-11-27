"""Style resolvers: transform a SampleBuffer into a CellBuffer (DET-2, DET-7).

Resolvers operate purely on SampleBuffer + Viewport with no terminal I/O and
no knowledge of 3D geometry.
"""

from __future__ import annotations

import math
import os
from typing import Optional, Sequence, Tuple

from ..flowers.colorways import ColorValue, RGB, nearest_xterm256, sample_palette
from ..geometry.shading import GLYPH_RAMPS, SHADE, ramp_char, sample_ramp_char
from ..text import ascii_text
from .buffer import CellBuffer
from .samples import (
    EMPTY_Z,
    FLAG_FULL_LOD,
    FLAG_RIM,
    GC_BABY,
    GC_GREENERY,
    GC_OVERRIDE,
    GC_PAPER,
    GC_SPARKLE,
    GLYPH_CLASS_TO_TOKEN,
    HAS_NUMPY,
    SampleBuffer,
)

if HAS_NUMPY:
    import numpy as _np  # type: ignore[import-not-found]
    _POP8_NP = _np.array([bin(value).count("1") for value in range(256)], dtype=_np.uint16)

# 2x3 ordered Bayer threshold matrix for sextant dot density
_BAYER_2X3 = (
    (0.06, 0.39),
    (0.28, 0.11),
    (0.44, 0.22),
)

_SEXTANT_BITS = (
    (0x01, 0x02),
    (0x04, 0x08),
    (0x10, 0x20),
)


def _sextant_char(bits: int) -> str:
    if bits == 0:
        return " "
    # Unicode omits the two full columns and the full block.
    if bits in (0x15, 0x2A):
        bits &= ~0x01
    elif bits == 0x3F:
        bits &= ~0x01
    query = 0x1FB00 + bits - 1 - (bits > 0x15) - (bits > 0x2A)
    return chr(query)

# 2x4 ordered Bayer threshold matrix (normalized to modulate braille dot density)
_BAYER_2X4 = (
    (0.04, 0.28),
    (0.40, 0.16),
    (0.10, 0.34),
    (0.46, 0.22),
)

_BRAILLE_BITS = (
    (0x01, 0x08),
    (0x02, 0x10),
    (0x04, 0x20),
    (0x40, 0x80),
)

# Shape-aware ASCII glyph masks on a 4x8 grid (cell aspect is roughly 1:2).
# A mask is one 32-bit integer, row-major, low bit first.  Matching is only
# used for partial cells; fully covered interiors keep the brightness ramp.
MASK_W, MASK_H = 4, 8
MASK_BITS = MASK_W * MASK_H


def _mask_points(points) -> int:
    bits = 0
    for x, y in points:
        if 0 <= x < MASK_W and 0 <= y < MASK_H:
            bits |= 1 << (y * MASK_W + x)
    return bits


def _line_mask(x0: int, y0: int, x1: int, y1: int) -> int:
    points = []
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        points.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        err2 = 2 * err
        if err2 > -dy:
            err -= dy
            x0 += sx
        if err2 < dx:
            err += dx
            y0 += sy
    return _mask_points(points)


def _ring_mask(rx: float, ry: float, cy: float = 3.5) -> int:
    points = set()
    for step in range(96):
        angle = 2.0 * math.pi * step / 96
        points.add((int(round(1.5 + rx * math.cos(angle))),
                    int(round(cy + ry * math.sin(angle)))))
    return _mask_points(points)


_BAYER_4X8 = (
    (0, 16, 4, 20),
    (24, 8, 28, 12),
    (6, 22, 2, 18),
    (30, 14, 26, 10),
    (1, 17, 5, 21),
    (25, 9, 29, 13),
    (7, 23, 3, 19),
    (31, 15, 27, 11),
)


def _stipple(n: int) -> int:
    return _mask_points(
        (x, y) for y in range(MASK_H) for x in range(MASK_W)
        if _BAYER_4X8[y][x] < n
    )


GLYPH_MASKS = {
    " ": 0,
    ".": _mask_points({(1, 7)}),
    ",": _mask_points({(0, 7), (1, 6)}),
    "'": _mask_points({(1, 0), (2, 1)}),
    "`": _mask_points({(1, 0), (0, 1)}),
    '"': _mask_points({(1, 0), (3, 0)}),
    "^": _mask_points({(0, 2), (1, 1), (2, 1), (3, 2), (1, 2), (2, 2)}),
    ":": _mask_points({(1, 2), (1, 5)}),
    ";": _mask_points({(1, 2), (0, 5), (1, 6)}),
    "-": _line_mask(0, 4, 3, 4),
    "_": _line_mask(0, 7, 3, 7),
    "=": _line_mask(0, 2, 3, 2) | _line_mask(0, 5, 3, 5),
    "~": _mask_points({(0, 2), (1, 3), (2, 2), (3, 3),
                       (0, 5), (1, 6), (2, 5), (3, 6)}),
    "+": _line_mask(1, 1, 1, 6) | _line_mask(0, 3, 3, 3),
    "*": (_line_mask(1, 1, 1, 6) | _line_mask(0, 3, 3, 3)
          | _mask_points({(0, 1), (2, 1), (0, 5), (2, 5)})),
    "x": _line_mask(0, 1, 3, 6) | _line_mask(3, 1, 0, 6),
    "X": _line_mask(0, 0, 3, 7) | _line_mask(3, 0, 0, 7),
    "/": _line_mask(3, 0, 0, 7),
    "\\": _line_mask(0, 0, 3, 7),
    "|": _line_mask(1, 0, 1, 7),
    "(": _mask_points({(3, 0), (2, 1), (1, 2), (1, 3),
                       (1, 4), (1, 5), (2, 6), (3, 7)}),
    ")": _mask_points({(0, 0), (1, 1), (2, 2), (2, 3),
                       (2, 4), (2, 5), (1, 6), (0, 7)}),
    "o": _ring_mask(1.2, 2.1),
    "O": _ring_mask(1.7, 3.3),
    "0": _ring_mask(1.5, 3.7),
    "8": _ring_mask(1.2, 1.4, 2.0) | _ring_mask(1.2, 1.4, 5.2),
    "&": _ring_mask(1.4, 1.7, 2.4) | _mask_points({(2, 5), (3, 6), (2, 6)}),
    "@": _ring_mask(1.9, 3.8) | _stipple(4),
    "#": _line_mask(0, 1, 0, 7) | _line_mask(2, 1, 2, 7)
         | _line_mask(0, 2, 3, 2) | _line_mask(0, 5, 3, 5),
    "%": _line_mask(0, 0, 3, 7) | _mask_points({(0, 5), (1, 6), (2, 1), (3, 2)}),
    "v": _mask_points({(0, 1), (1, 2), (2, 3), (3, 4), (2, 5), (1, 6), (0, 7)}),
}

# Class-restricted candidate sets: petal-like classes never reach for #/@/%
# so dense cores stay reserved for centres and accents (ASC-8).
TOKEN_GLYPHS = {
    "petal": ("|", "-", "_", "/", "\\", "(", ")", "o", "O", ".",
              ",", ":", ";", "'", "`", "~", "=", "+", "*", "x"),
    "soft": (".", "'", "`", '"', ",", ":", ";", "~", "-", "+", "*", "o"),
    "cup": (",", ":", ";", "-", "=", "+", "*", "(", ")", "o"),
    "star": (".", "'", ":", "-", "^", "~", "=", "+", "*", "x", "X", "o"),
    "dense": (",", ":", ";", "~", "=", "+", "*", "o", "O", "8", "&"),
    "poppy": (".", "'", ":", "~", "=", "+", "*", "o", "O"),
    "sepal": (".", ":", "-", "=", "+", "*"),
    "greenery": ("|", "/", "\\", "_", "-", ",", ";", "~", "'", "`", "v"),
    "center": ("@", "O", "o", "0", "*", "&", "%", "8", "x"),
    "stamen": ("*", "+", "x", ".", "'"),
    "shade": ("|", "/", "\\", "-", "_", "=", "+", "*", "#", "%", "8"),
}
_TOKEN_ORDER = tuple(TOKEN_GLYPHS)
_TOKEN_INDEX = {name: index for index, name in enumerate(_TOKEN_ORDER)}
_GC_TOKEN = tuple(
    GLYPH_CLASS_TO_TOKEN.get(gc, "petal") for gc in range(18)
)
_GC_TOKEN_INDEX = tuple(_TOKEN_INDEX[token] for token in _GC_TOKEN)

_POP8 = tuple(bin(value).count("1") for value in range(256))


def _popcount(value: int) -> int:
    return (_POP8[value & 0xFF] + _POP8[(value >> 8) & 0xFF]
            + _POP8[(value >> 16) & 0xFF] + _POP8[(value >> 24) & 0xFF])


def samples_per_cell(style: str) -> Tuple[int, int]:
    if style == "half":
        return 1, 2
    if style == "braille":
        return 2, 4
    if style == "sextant":
        return 2, 3
    return 1, 1


def effective_resolution(detail: int, terminal_rows: int, style: str) -> int:
    """3.1 formula: min(detail, max(1, terminal_rows - 4) * samples_per_cell_y)."""
    _, sy = samples_per_cell(style)
    bouquet_rows = max(1, terminal_rows - 4)
    return min(detail, bouquet_rows * sy)


def auto_detail_target(terminal_rows: int, style: str, has_numpy: bool) -> int:
    """Smallest level >= what current style & terminal can display, clamped if no NumPy."""
    _, sy = samples_per_cell(style)
    needed = max(1, terminal_rows - 4) * sy
    levels = (32, 64) if not has_numpy else (32, 64, 128, 256)
    for level in levels:
        if level >= needed:
            return level
    return levels[-1]


def effective_style(
    requested: str,
    ascii_mode: bool = False,
    color_enabled: bool = True,
) -> str:
    """Fall back to ascii for --ascii or terminals without block/dot glyph support.

    ``color_enabled`` is accepted for call-site compatibility; style choice is
    independent of colour so plain snapshots and galleries still honour it.
    """
    del color_enabled
    if ascii_mode:
        return "ascii"
    if requested not in ("ascii", "half", "braille", "sextant"):
        return "ascii"
    if requested != "ascii":
        term = os.environ.get("TERM", "").lower()
        if term in ("dumb", "linux", "vt100", "vt220"):
            return "ascii"
    return requested


def resolve_truecolor(color_mode: str, color_enabled: bool) -> bool:
    if not color_enabled or color_mode == "mono":
        return False
    if color_mode == "truecolor":
        return True
    if color_mode == "256":
        return False
    colorterm = os.environ.get("COLORTERM", "").lower()
    return colorterm in ("truecolor", "24bit")


def _sample_color(
    sample_buf: SampleBuffer,
    pid: int,
    bright: float,
    truecolor: bool,
    color_enabled: bool,
) -> ColorValue:
    if not color_enabled:
        return None
    pal, rgb_ramp = sample_buf.palettes[pid]
    return sample_palette(pal, bright, truecolor=truecolor, rgb_ramp=rgb_ramp)


def _sample_glyph(
    gc: int,
    char_code: int,
    bright: float,
    ascii_mode: bool,
) -> str:
    if char_code:
        ch = chr(char_code)
        return ascii_text(ch) if ascii_mode else ch
    token = GLYPH_CLASS_TO_TOKEN.get(gc, "petal")
    if token == "shade":
        return ramp_char(bright, SHADE)
    if token == "center":
        return "@" if bright > 0.65 else "o"
    if token == "stamen":
        return "*" if bright > 0.5 else "."
    if token == "greenery":
        return ramp_char(bright, GLYPH_RAMPS["greenery"])
    return sample_ramp_char(token, bright, is_sepal=(gc == 7))


def _edge_direction_glyph(
    sample_buf: SampleBuffer,
    cx: int,
    cy: int,
    my_oid: int,
) -> Optional[str]:
    """Pick directional ASCII edge glyph from local 3x3 silhouette gradient."""
    w, h = sample_buf.width, sample_buf.height
    if HAS_NUMPY:
        def covered(x: int, y: int) -> float:
            if 0 <= x < w and 0 <= y < h:
                return 1.0 if sample_buf.obj_id[y, x] == my_oid else 0.0
            return 0.0
    else:
        def covered(x: int, y: int) -> float:
            if 0 <= x < w and 0 <= y < h:
                return 1.0 if sample_buf.obj_id[y * w + x] == my_oid else 0.0
            return 0.0

    # Sobel-like gradient pointing outward from shape (empty minus filled)
    gx = (
        (covered(cx + 1, cy - 1) + 2.0 * covered(cx + 1, cy) + covered(cx + 1, cy + 1))
        - (covered(cx - 1, cy - 1) + 2.0 * covered(cx - 1, cy) + covered(cx - 1, cy + 1))
    )
    gy = (
        (covered(cx - 1, cy + 1) + 2.0 * covered(cx, cy + 1) + covered(cx + 1, cy + 1))
        - (covered(cx - 1, cy - 1) + 2.0 * covered(cx, cy - 1) + covered(cx + 1, cy - 1))
    )
    mag2 = gx * gx + gy * gy
    if mag2 < 0.5:
        return None
    agx, agy = abs(gx), abs(gy)
    if agx > 2.2 * agy:
        return "(" if gx > 0 else ")" if gx < 0 else "|"
    if agy > 2.2 * agx:
        return "_" if gy < 0 else "-"
    if gx * gy < 0:
        return "/"
    return "\\"


def resolve(
    sample_buf: SampleBuffer,
    cell_buf: CellBuffer,
    clip: Tuple[int, int, int, int],
    style: str = "ascii",
    truecolor: bool = False,
    color_enabled: bool = True,
    ascii_mode: bool = False,
    stats: Optional[dict] = None,
    glyph_history: Optional[dict] = None,
) -> None:
    """Resolve *sample_buf* into *cell_buf* inside *clip* = (x0, y0, x1, y1)."""
    style = effective_style(style, ascii_mode=ascii_mode, color_enabled=color_enabled)
    if style == "half":
        _resolve_half(sample_buf, cell_buf, clip, truecolor, color_enabled)
    elif style == "braille":
        _resolve_braille(sample_buf, cell_buf, clip, truecolor, color_enabled)
    elif style == "sextant":
        _resolve_sextant(sample_buf, cell_buf, clip, truecolor, color_enabled)
    else:
        _resolve_ascii(
            sample_buf, cell_buf, clip, truecolor, color_enabled, ascii_mode,
            stats=stats, glyph_history=glyph_history,
        )


def _resolve_ascii(
    sb: SampleBuffer,
    cb: CellBuffer,
    clip: Tuple[int, int, int, int],
    truecolor: bool,
    color_enabled: bool,
    ascii_mode: bool,
    stats: Optional[dict] = None,
    glyph_history: Optional[dict] = None,
) -> None:
    # Below ~32 samples the cell patch is too coarse to carry a shape; keep the
    # old per-sample ramp so low detail stays cheap and legible.
    if sb.height <= 32:
        _resolve_ascii_legacy(sb, cb, clip, truecolor, color_enabled, ascii_mode)
        return
    if HAS_NUMPY:
        _resolve_ascii_masked_numpy(
            sb, cb, clip, truecolor, color_enabled, ascii_mode, stats, glyph_history,
        )
    else:
        _resolve_ascii_masked_python(
            sb, cb, clip, truecolor, color_enabled, ascii_mode, stats, glyph_history,
        )


def _resolve_ascii_legacy(
    sb: SampleBuffer,
    cb: CellBuffer,
    clip: Tuple[int, int, int, int],
    truecolor: bool,
    color_enabled: bool,
    ascii_mode: bool,
) -> None:
    x0, y0, x1, y1 = clip
    view_w = max(1, x1 - x0)
    view_h = max(1, y1 - y0)
    sw, sh = sb.width, sb.height
    supersampled = sh > view_h

    if HAS_NUMPY:
        # Cover every sample that falls in a cell; a fixed k left gaps when the
        # sample canvas was more than k times taller than the cell grid.
        k = max(1, math.ceil(sh / view_h), math.ceil(sw / view_w))
        if k == 1:
            sy_idx = _np.clip(((_np.arange(view_h) + 0.5) * sh / view_h).astype(_np.int32), 0, sh - 1)
            sx_idx = _np.clip(((_np.arange(view_w) + 0.5) * sw / view_w).astype(_np.int32), 0, sw - 1)
            zs = sb.z[sy_idx[:, None], sx_idx[None, :]]
            covered_rows, covered_cols = _np.where(zs > EMPTY_Z * 0.5)
            brs = sb.brightness[sy_idx[:, None], sx_idx[None, :]]
            pids = sb.palette_id[sy_idx[:, None], sx_idx[None, :]]
            gcs = sb.glyph_class[sy_idx[:, None], sx_idx[None, :]]
            ccs = sb.char_code[sy_idx[:, None], sx_idx[None, :]]
            for r_off, c_off in zip(covered_rows.tolist(), covered_cols.tolist()):
                zv = float(zs[r_off, c_off])
                bv = float(brs[r_off, c_off])
                ch = _sample_glyph(int(gcs[r_off, c_off]), int(ccs[r_off, c_off]), bv, ascii_mode)
                col_val = _sample_color(sb, int(pids[r_off, c_off]), bv, truecolor, color_enabled)
                cb.plot(x0 + c_off, y0 + r_off, zv, ch, col_val)
            return

        offs = (_np.arange(k, dtype=_np.float32) + 0.5) / k
        sy_sub = _np.clip(((_np.arange(view_h)[:, None] + offs[None, :]) * sh / view_h).astype(_np.int32), 0, sh - 1)
        sx_sub = _np.clip(((_np.arange(view_w)[:, None] + offs[None, :]) * sw / view_w).astype(_np.int32), 0, sw - 1)
        # Shape: (view_h, k, view_w, k) -> (view_h, view_w, k*k)
        sy_grid = _np.broadcast_to(sy_sub[:, :, None, None], (view_h, k, view_w, k)).transpose(0, 2, 1, 3).reshape(view_h, view_w, k * k)
        sx_grid = _np.broadcast_to(sx_sub[None, None, :, :], (view_h, k, view_w, k)).transpose(0, 2, 1, 3).reshape(view_h, view_w, k * k)
        z_sub = sb.z[sy_grid, sx_grid]
        best_idx = _np.argmax(z_sub, axis=2)
        best_z = _np.take_along_axis(z_sub, best_idx[:, :, None], axis=2)[:, :, 0]
        cov_count = _np.count_nonzero(z_sub > EMPTY_Z * 0.5, axis=2)
        covered_rows, covered_cols = _np.where(best_z > EMPTY_Z * 0.5)
        if covered_rows.size == 0:
            return
        wy_arr = _np.take_along_axis(sy_grid, best_idx[:, :, None], axis=2)[:, :, 0]
        wx_arr = _np.take_along_axis(sx_grid, best_idx[:, :, None], axis=2)[:, :, 0]
        wys = wy_arr[covered_rows, covered_cols]
        wxs = wx_arr[covered_rows, covered_cols]
        zs_c = best_z[covered_rows, covered_cols].tolist()
        bvs_c = sb.brightness[wys, wxs].tolist()
        gcs_c = sb.glyph_class[wys, wxs].tolist()
        ccs_c = sb.char_code[wys, wxs].tolist()
        pids_c = sb.palette_id[wys, wxs].tolist()
        oids_c = sb.obj_id[wys, wxs].tolist()
        fls_c = sb.flags[wys, wxs].tolist()
        covs_c = (cov_count[covered_rows, covered_cols] / float(k * k)).tolist()
        wys_l = wys.tolist()
        wxs_l = wxs.tolist()
        for idx, (r_off, c_off) in enumerate(zip(covered_rows.tolist(), covered_cols.tolist())):
            bv = bvs_c[idx]
            cc = ccs_c[idx]
            fl = fls_c[idx]
            ch = ""
            if cc == 0 and (fl & FLAG_FULL_LOD) and ((fl & FLAG_RIM) or covs_c[idx] < 0.72):
                edge_ch = _edge_direction_glyph(sb, wxs_l[idx], wys_l[idx], oids_c[idx])
                if edge_ch is not None:
                    ch = edge_ch
            if not ch:
                ch = _sample_glyph(gcs_c[idx], cc, bv, ascii_mode)
            col_val = _sample_color(sb, pids_c[idx], bv, truecolor, color_enabled)
            cb.plot(x0 + c_off, y0 + r_off, zs_c[idx], ch, col_val)
        return

    for r_off in range(view_h):
        sy0 = int(r_off * sh / view_h)
        sy1 = max(sy0 + 1, int((r_off + 1) * sh / view_h))
        if not supersampled:
            sy0 = min(sh - 1, int((r_off + 0.5) * sh / view_h))
            sy1 = sy0 + 1
        for c_off in range(view_w):
            sx0 = int(c_off * sw / view_w)
            sx1 = max(sx0 + 1, int((c_off + 1) * sw / view_w))
            if not supersampled:
                sx0 = min(sw - 1, int((c_off + 0.5) * sw / view_w))
                sx1 = sx0 + 1

            if HAS_NUMPY:
                patch_z = sb.z[sy0:sy1, sx0:sx1]
                mask = patch_z > EMPTY_Z * 0.5
                cov_count = int(_np.count_nonzero(mask))
                if cov_count == 0:
                    continue
                flat_idx = int(_np.argmax(patch_z))
                py_rel, px_rel = divmod(flat_idx, sx1 - sx0)
                wy, wx = sy0 + py_rel, sx0 + px_rel
                zv = float(sb.z[wy, wx])
                bv = float(sb.brightness[wy, wx])
                gc = int(sb.glyph_class[wy, wx])
                cc = int(sb.char_code[wy, wx])
                pid = int(sb.palette_id[wy, wx])
                oid = int(sb.obj_id[wy, wx])
                fl = int(sb.flags[wy, wx])
            else:
                best_z = EMPTY_Z
                best_idx = -1
                cov_count = 0
                for sy in range(sy0, min(sh, sy1)):
                    base = sy * sw
                    for sx in range(sx0, min(sw, sx1)):
                        idx = base + sx
                        zv = sb.z[idx]
                        if zv > EMPTY_Z * 0.5:
                            cov_count += 1
                            if zv > best_z:
                                best_z = zv
                                best_idx = idx
                if best_idx < 0:
                    continue
                wy, wx = divmod(best_idx, sw)
                zv = best_z
                bv = sb.brightness[best_idx]
                gc = sb.glyph_class[best_idx]
                cc = sb.char_code[best_idx]
                pid = sb.palette_id[best_idx]
                oid = sb.obj_id[best_idx]
                fl = sb.flags[best_idx]

            total_patch = max(1, (min(sh, sy1) - sy0) * (min(sw, sx1) - sx0))
            coverage = cov_count / total_patch

            ch = ""
            if supersampled and cc == 0 and (fl & FLAG_FULL_LOD) and ((fl & FLAG_RIM) or coverage < 0.72):
                edge_ch = _edge_direction_glyph(sb, wx, wy, oid)
                if edge_ch is not None:
                    ch = edge_ch
            if not ch:
                ch = _sample_glyph(gc, cc, bv, ascii_mode)
            col_val = _sample_color(sb, pid, bv, truecolor, color_enabled)
            cb.plot(x0 + c_off, y0 + r_off, zv, ch, col_val)


def _bin_y(row: int, by: int, sh: int, view_h: int) -> int:
    return min(sh - 1, ((16 * row + 2 * by + 1) * sh) // (16 * view_h))


def _bin_x(col: int, bx: int, sw: int, view_w: int) -> int:
    return min(sw - 1, ((8 * col + 2 * bx + 1) * sw) // (8 * view_w))


def _bin_y_array(rows, by: int, sh: int, view_h: int):
    return _np.minimum((rows * 16 + (2 * by + 1)) * sh // (16 * view_h), sh - 1)


def _bin_x_array(cols, bx: int, sw: int, view_w: int):
    return _np.minimum((cols * 8 + (2 * bx + 1)) * sw // (8 * view_w), sw - 1)


def _resolve_ascii_masked_numpy(
    sb: SampleBuffer,
    cb: CellBuffer,
    clip: Tuple[int, int, int, int],
    truecolor: bool,
    color_enabled: bool,
    ascii_mode: bool,
    stats: Optional[dict],
    glyph_history: Optional[dict],
) -> None:
    x0, y0, x1, y1 = clip
    view_w = max(1, x1 - x0)
    view_h = max(1, y1 - y0)
    sw, sh = sb.width, sb.height
    ncells = view_w * view_h
    np = _np

    covered = sb.z > EMPTY_Z * 0.5
    if not np.any(covered):
        return

    rows = np.arange(view_h)
    cols = np.arange(view_w)
    sy_by = [_bin_y_array(rows, by, sh, view_h) for by in range(MASK_H)]
    sx_by = [_bin_x_array(cols, bx, sw, view_w) for bx in range(MASK_W)]
    flat = np.arange(ncells)

    target = np.zeros(ncells, dtype=np.uint32)
    cover_count = np.zeros(ncells, dtype=np.int16)
    bsum = np.zeros(ncells, dtype=np.float64)
    zmax = np.full(ncells, EMPTY_Z)
    rim_count = np.zeros(ncells, dtype=np.int16)
    npal = len(sb.palettes)
    ngc = len(_GC_TOKEN)
    pid_index: list = []
    pid_weight: list = []
    gc_index: list = []
    gc_weight: list = []
    cc_cell = np.zeros(ncells, dtype=np.uint8)
    cc_pid = np.zeros(ncells, dtype=np.int16)
    cc_bright = np.zeros(ncells, dtype=np.float64)
    cc_z = np.full(ncells, EMPTY_Z)

    for by in range(MASK_H):
        sy = sy_by[by]
        for bx in range(MASK_W):
            sx = sx_by[bx]
            z = sb.z[sy[:, None], sx[None, :]]
            cov = z > EMPTY_Z * 0.5
            bit = by * MASK_W + bx
            target |= cov.astype(np.uint32).ravel() << bit
            cover_count += cov.ravel()
            bright = sb.brightness[sy[:, None], sx[None, :]]
            bsum += np.where(cov, bright, 0.0).ravel()
            zmax = np.maximum(zmax, np.where(cov, z, EMPTY_Z).ravel())
            flags = sb.flags[sy[:, None], sx[None, :]]
            rim_count += (cov & ((flags & FLAG_RIM) != 0)).ravel()
            weight = np.where(cov, np.maximum(0.05, bright), 0.0).ravel()
            pid_flat = sb.palette_id[sy[:, None], sx[None, :]].ravel()
            pid_index.append(flat * npal + pid_flat)
            pid_weight.append(weight)
            gc_flat = sb.glyph_class[sy[:, None], sx[None, :]].ravel()
            gc_index.append(flat * ngc + gc_flat)
            gc_weight.append(weight)
            code = sb.char_code[sy[:, None], sx[None, :]].ravel()
            take = cov.ravel() & (code != 0) & (z.ravel() > cc_z)
            cc_cell[take] = code[take]
            cc_pid[take] = sb.palette_id[sy[:, None], sx[None, :]].ravel()[take]
            cc_bright[take] = bright.ravel()[take]
            cc_z[take] = z.ravel()[take]

    # An override glyph only wins when it is also the frontmost sample in the cell.
    cc_cell[cc_z < zmax] = 0

    covered_cells = np.nonzero(cover_count > 0)[0]
    if covered_cells.size == 0:
        return
    mean_bright = bsum / np.maximum(1, cover_count).astype(np.float64)
    pid_score = np.bincount(
        np.concatenate(pid_index), weights=np.concatenate(pid_weight),
        minlength=ncells * npal,
    ).reshape(ncells, npal)
    gc_score = np.bincount(
        np.concatenate(gc_index), weights=np.concatenate(gc_weight),
        minlength=ncells * ngc,
    ).reshape(ncells, ngc)
    dom_pid = pid_score.argmax(axis=1)
    dom_gc = gc_score.argmax(axis=1)
    token_ids = np.array(_GC_TOKEN_INDEX, dtype=np.int16)[dom_gc]

    full = cover_count >= 27
    partial = (cover_count > 0) & (~full | (rim_count > 0)) & (cc_cell == 0)
    chosen_char = np.full(ncells, " ", dtype="<U2")
    best_dist = np.full(ncells, 99, dtype=np.int16)

    for token_id, token in enumerate(_TOKEN_ORDER):
        cell_ids = np.nonzero(partial & (token_ids == token_id))[0]
        if not cell_ids.size:
            continue
        candidate_chars = TOKEN_GLYPHS[token]
        candidates = np.array([GLYPH_MASKS[ch] for ch in candidate_chars], dtype=np.uint32)
        xor = target[cell_ids, None] ^ candidates[None, :]
        dist = (_POP8_NP[xor & 0xFF] + _POP8_NP[(xor >> 8) & 0xFF]
                + _POP8_NP[(xor >> 16) & 0xFF] + _POP8_NP[(xor >> 24) & 0xFF])
        best = dist.argmin(axis=1)
        chosen_char[cell_ids] = np.array(candidate_chars, dtype="<U2")[best]
        best_dist[cell_ids] = dist[np.arange(cell_ids.size), best]

    matched = 0
    residual = 0
    used_glyphs = set()

    for cidx in covered_cells.tolist():
        r_off, c_off = divmod(cidx, view_w)
        if cc_cell[cidx]:
            ch = chr(int(cc_cell[cidx]))
            if ascii_mode:
                ch = ascii_text(ch)
            col_val = _sample_color(
                sb, int(cc_pid[cidx]), float(cc_bright[cidx]), truecolor, color_enabled,
            )
        else:
            bv = float(mean_bright[cidx])
            if partial[cidx]:
                ch = str(chosen_char[cidx])
                token = _TOKEN_ORDER[int(token_ids[cidx])]
                if glyph_history is not None:
                    key = (x0 + c_off, y0 + r_off)
                    previous = glyph_history.get(key)
                    if (previous and previous != ch and previous in TOKEN_GLYPHS[token]
                            and _popcount(int(target[cidx]) ^ GLYPH_MASKS[previous])
                            <= int(best_dist[cidx]) + 1):
                        ch = previous
                    glyph_history[key] = ch
                matched += 1
                residual += int(best_dist[cidx])
                used_glyphs.add(ch)
            else:
                ch = _sample_glyph(int(dom_gc[cidx]), 0, bv, ascii_mode)
            col_val = _sample_color(
                sb, int(dom_pid[cidx]), bv, truecolor, color_enabled,
            )
        cb.plot(x0 + c_off, y0 + r_off, float(zmax[cidx]), ch, col_val)

    if stats is not None:
        stats["ascii_partial_cells"] = int(partial.sum())
        stats["ascii_matched_cells"] = matched
        stats["ascii_mask_residual"] = float(residual)
        stats["ascii_glyphs"] = used_glyphs


def _resolve_ascii_masked_python(
    sb: SampleBuffer,
    cb: CellBuffer,
    clip: Tuple[int, int, int, int],
    truecolor: bool,
    color_enabled: bool,
    ascii_mode: bool,
    stats: Optional[dict],
    glyph_history: Optional[dict],
) -> None:
    x0, y0, x1, y1 = clip
    view_w = max(1, x1 - x0)
    view_h = max(1, y1 - y0)
    sw, sh = sb.width, sb.height

    def at(field, y: int, x: int):
        return field[y, x] if HAS_NUMPY else field[y * sw + x]

    matched = 0
    residual = 0
    partial_count = 0
    used_glyphs = set()
    for row in range(view_h):
        sy = [_bin_y(row, by, sh, view_h) for by in range(MASK_H)]
        for col in range(view_w):
            sx = [_bin_x(col, bx, sw, view_w) for bx in range(MASK_W)]
            target = 0
            cover_count = 0
            bsum = 0.0
            zmax = EMPTY_Z
            has_rim = False
            pid_votes = {}
            gc_votes = {}
            cc_code = 0
            cc_pid = 0
            cc_bright = 0.0
            cc_z = EMPTY_Z
            for by in range(MASK_H):
                yy = sy[by]
                for bx in range(MASK_W):
                    xx = sx[bx]
                    depth = at(sb.z, yy, xx)
                    if depth <= EMPTY_Z * 0.5:
                        continue
                    bit = by * MASK_W + bx
                    target |= 1 << bit
                    cover_count += 1
                    bright = at(sb.brightness, yy, xx)
                    bsum += bright
                    if depth > zmax:
                        zmax = depth
                    if at(sb.flags, yy, xx) & FLAG_RIM:
                        has_rim = True
                    weight = max(0.05, bright)
                    pid = at(sb.palette_id, yy, xx)
                    pid_votes[pid] = pid_votes.get(pid, 0.0) + weight
                    gc = at(sb.glyph_class, yy, xx)
                    gc_votes[gc] = gc_votes.get(gc, 0.0) + weight
                    code = at(sb.char_code, yy, xx)
                    if code and depth > cc_z:
                        cc_code = code
                        cc_pid = pid
                        cc_bright = bright
                        cc_z = depth
            if cover_count == 0:
                continue
            if cc_z < zmax:
                cc_code = 0
            mean_bright = bsum / cover_count
            dom_pid = min(pid_votes.items(), key=lambda item: (-item[1], item[0]))[0]
            dom_gc = min(gc_votes.items(), key=lambda item: (-item[1], item[0]))[0]

            if cc_code:
                ch = chr(cc_code)
                if ascii_mode:
                    ch = ascii_text(ch)
                col_val = _sample_color(sb, cc_pid, cc_bright, truecolor, color_enabled)
            else:
                if cover_count >= 27 and not has_rim:
                    ch = _sample_glyph(dom_gc, 0, mean_bright, ascii_mode)
                else:
                    token = _GC_TOKEN[dom_gc] if dom_gc < len(_GC_TOKEN) else "petal"
                    candidates = TOKEN_GLYPHS.get(token, TOKEN_GLYPHS["petal"])
                    best_ch = ""
                    best = None
                    for candidate in candidates:
                        dist = _popcount(target ^ GLYPH_MASKS[candidate])
                        if best is None or dist < best:
                            best = dist
                            best_ch = candidate
                    ch = best_ch
                    if glyph_history is not None:
                        key = (x0 + col, y0 + row)
                        previous = glyph_history.get(key)
                        if (previous and previous != ch and previous in candidates
                                and _popcount(target ^ GLYPH_MASKS[previous]) <= best + 1):
                            ch = previous
                        glyph_history[key] = ch
                    partial_count += 1
                    matched += 1
                    residual += best
                    used_glyphs.add(ch)
                col_val = _sample_color(sb, dom_pid, mean_bright, truecolor, color_enabled)
            cb.plot(x0 + col, y0 + row, zmax, ch, col_val)

    if stats is not None:
        stats["ascii_partial_cells"] = partial_count
        stats["ascii_matched_cells"] = matched
        stats["ascii_mask_residual"] = float(residual)
        stats["ascii_glyphs"] = used_glyphs


def _patch_dominant(
    sb: SampleBuffer,
    sy0: int,
    sy1: int,
    sx0: int,
    sx1: int,
):
    sw, sh = sb.width, sb.height
    if HAS_NUMPY:
        patch_z = sb.z[sy0:sy1, sx0:sx1]
        if not _np.any(patch_z > EMPTY_Z * 0.5):
            return None
        flat_idx = int(_np.argmax(patch_z))
        py_rel, px_rel = divmod(flat_idx, sx1 - sx0)
        wy, wx = sy0 + py_rel, sx0 + px_rel
        return (
            float(sb.z[wy, wx]),
            float(sb.brightness[wy, wx]),
            int(sb.palette_id[wy, wx]),
            int(sb.flags[wy, wx]),
        )
    best_z = EMPTY_Z
    best_idx = -1
    for sy in range(sy0, min(sh, sy1)):
        base = sy * sw
        for sx in range(sx0, min(sw, sx1)):
            idx = base + sx
            if sb.z[idx] > best_z and sb.z[idx] > EMPTY_Z * 0.5:
                best_z = sb.z[idx]
                best_idx = idx
    if best_idx < 0:
        return None
    return best_z, sb.brightness[best_idx], sb.palette_id[best_idx], sb.flags[best_idx]


def _resolve_half(
    sb: SampleBuffer,
    cb: CellBuffer,
    clip: Tuple[int, int, int, int],
    truecolor: bool,
    color_enabled: bool,
) -> None:
    x0, y0, x1, y1 = clip
    view_w = max(1, x1 - x0)
    view_h = max(1, y1 - y0)
    sw, sh = sb.width, sb.height
    if HAS_NUMPY:
        sy_top = _np.clip(((_np.arange(view_h) + 0.25) * sh / view_h).astype(_np.int32), 0, sh - 1)
        sy_bot = _np.clip(((_np.arange(view_h) + 0.75) * sh / view_h).astype(_np.int32), 0, sh - 1)
        sx_mid = _np.clip(((_np.arange(view_w) + 0.5) * sw / view_w).astype(_np.int32), 0, sw - 1)
        zt = sb.z[sy_top[:, None], sx_mid[None, :]]
        zb = sb.z[sy_bot[:, None], sx_mid[None, :]]
        ht = zt > EMPTY_Z * 0.5
        hb = zb > EMPTY_Z * 0.5
        any_cov = ht | hb
        rows_c, cols_c = _np.where(any_cov)
        if rows_c.size == 0:
            return
        bt = sb.brightness[sy_top[rows_c], sx_mid[cols_c]].tolist()
        bb = sb.brightness[sy_bot[rows_c], sx_mid[cols_c]].tolist()
        pt = sb.palette_id[sy_top[rows_c], sx_mid[cols_c]].tolist()
        pb = sb.palette_id[sy_bot[rows_c], sx_mid[cols_c]].tolist()
        zt_l = zt[rows_c, cols_c].tolist()
        zb_l = zb[rows_c, cols_c].tolist()
        ht_l = ht[rows_c, cols_c].tolist()
        hb_l = hb[rows_c, cols_c].tolist()
        for idx, (r_off, c_off) in enumerate(zip(rows_c.tolist(), cols_c.tolist())):
            t_on, b_on = ht_l[idx], hb_l[idx]
            if t_on and not b_on:
                fg = _sample_color(sb, pt[idx], bt[idx], truecolor, color_enabled)
                cb.plot(x0 + c_off, y0 + r_off, zt_l[idx], "\u2580", fg, bg=None)
            elif b_on and not t_on:
                fg = _sample_color(sb, pb[idx], bb[idx], truecolor, color_enabled)
                cb.plot(x0 + c_off, y0 + r_off, zb_l[idx], "\u2584", fg, bg=None)
            else:
                fg = _sample_color(sb, pt[idx], bt[idx], truecolor, color_enabled)
                bg = _sample_color(sb, pb[idx], bb[idx], truecolor, color_enabled)
                zmax = max(zt_l[idx], zb_l[idx])
                if fg == bg:
                    cb.plot(x0 + c_off, y0 + r_off, zmax, "\u2588", fg, bg=None)
                else:
                    cb.plot(x0 + c_off, y0 + r_off, zmax, "\u2580", fg, bg=bg)
        return
    for r_off in range(view_h):
        sy_top0 = min(sh - 1, int((r_off + 0.0) * sh / view_h))
        sy_mid = min(sh, max(sy_top0 + 1, int((r_off + 0.5) * sh / view_h)))
        sy_bot0 = min(sh - 1, int((r_off + 0.5) * sh / view_h))
        sy_bot1 = min(sh, max(sy_bot0 + 1, int((r_off + 1.0) * sh / view_h)))
        for c_off in range(view_w):
            sx0 = min(sw - 1, int(c_off * sw / view_w))
            sx1 = min(sw, max(sx0 + 1, int((c_off + 1) * sw / view_w)))
            top = _patch_dominant(sb, sy_top0, sy_mid, sx0, sx1)
            bot = _patch_dominant(sb, sy_bot0, sy_bot1, sx0, sx1)
            if top is None and bot is None:
                continue
            if top is not None and bot is None:
                fg = _sample_color(sb, top[2], top[1], truecolor, color_enabled)
                cb.plot(x0 + c_off, y0 + r_off, top[0], "\u2580", fg, bg=None)
            elif bot is not None and top is None:
                fg = _sample_color(sb, bot[2], bot[1], truecolor, color_enabled)
                cb.plot(x0 + c_off, y0 + r_off, bot[0], "\u2584", fg, bg=None)
            else:
                assert top is not None and bot is not None
                fg = _sample_color(sb, top[2], top[1], truecolor, color_enabled)
                bg = _sample_color(sb, bot[2], bot[1], truecolor, color_enabled)
                zmax = max(top[0], bot[0])
                if fg == bg:
                    cb.plot(x0 + c_off, y0 + r_off, zmax, "\u2588", fg, bg=None)
                else:
                    cb.plot(x0 + c_off, y0 + r_off, zmax, "\u2580", fg, bg=bg)


def _resolve_braille(
    sb: SampleBuffer,
    cb: CellBuffer,
    clip: Tuple[int, int, int, int],
    truecolor: bool,
    color_enabled: bool,
) -> None:
    x0, y0, x1, y1 = clip
    view_w = max(1, x1 - x0)
    view_h = max(1, y1 - y0)
    sw, sh = sb.width, sb.height
    if HAS_NUMPY:
        dy_offs = (_np.arange(4, dtype=_np.float32) + 0.5) * 0.25
        dx_offs = (_np.arange(2, dtype=_np.float32) + 0.5) * 0.5
        sy_d = _np.clip(((_np.arange(view_h)[:, None] + dy_offs[None, :]) * sh / view_h).astype(_np.int32), 0, sh - 1)
        sx_d = _np.clip(((_np.arange(view_w)[:, None] + dx_offs[None, :]) * sw / view_w).astype(_np.int32), 0, sw - 1)
        # Shape: (view_h, 4, view_w, 2) -> (view_h, view_w, 4, 2)
        sy_g = _np.broadcast_to(sy_d[:, :, None, None], (view_h, 4, view_w, 2)).transpose(0, 2, 1, 3)
        sx_g = _np.broadcast_to(sx_d[None, None, :, :], (view_h, 4, view_w, 2)).transpose(0, 2, 1, 3)
        zd = sb.z[sy_g, sx_g]
        cov = zd > EMPTY_Z * 0.5
        any_cov = _np.any(cov, axis=(2, 3))
        rows_c, cols_c = _np.where(any_cov)
        if rows_c.size == 0:
            return
        bayer = _np.array(_BAYER_2X4, dtype=_np.float32)
        b_bits = _np.array(_BRAILLE_BITS, dtype=_np.int32)
        zd_c = zd[rows_c, cols_c]              # (M, 4, 2)
        cov_c = cov[rows_c, cols_c]            # (M, 4, 2)
        bd_c = sb.brightness[sy_g[rows_c, cols_c], sx_g[rows_c, cols_c]]
        pd_c = sb.palette_id[sy_g[rows_c, cols_c], sx_g[rows_c, cols_c]]
        fd_c = sb.flags[sy_g[rows_c, cols_c], sx_g[rows_c, cols_c]]
        on_c = cov_c & ((bd_c >= bayer[None, :, :]) | ((fd_c & FLAG_RIM) != 0))
        bits_arr = _np.sum(_np.where(on_c, b_bits[None, :, :], 0), axis=(1, 2))
        zmax_arr = _np.max(zd_c, axis=(1, 2))

        rows_l = rows_c.tolist()
        cols_l = cols_c.tolist()
        bits_l = bits_arr.tolist()
        zmax_l = zmax_arr.tolist()
        on_l = on_c.tolist()
        cov_l = cov_c.tolist()
        bd_l = bd_c.tolist()
        pd_l = pd_c.tolist()
        for idx, (r_off, c_off) in enumerate(zip(rows_l, cols_l)):
            bits = bits_l[idx]
            set_dots = []
            if bits == 0:
                best = None
                for dy in range(4):
                    for dx in range(2):
                        if cov_l[idx][dy][dx]:
                            bv = bd_l[idx][dy][dx]
                            if best is None or bv > best[2]:
                                best = (dy, dx, bv, pd_l[idx][dy][dx])
                assert best is not None
                bits = _BRAILLE_BITS[best[0]][best[1]]
                set_dots.append((best[2], best[3]))
            else:
                for dy in range(4):
                    for dx in range(2):
                        if on_l[idx][dy][dx]:
                            set_dots.append((bd_l[idx][dy][dx], pd_l[idx][dy][dx]))
            if not color_enabled:
                cell_color: ColorValue = None
            elif truecolor:
                wr = wg = wb = wsum = 0.0
                for bv, pid in set_dots:
                    col = _sample_color(sb, pid, bv, truecolor=True, color_enabled=True)
                    assert isinstance(col, tuple)
                    w = max(0.05, bv)
                    wr += col[0] * w; wg += col[1] * w; wb += col[2] * w; wsum += w
                cell_color = (min(255, int(round(wr / wsum))), min(255, int(round(wg / wsum))), min(255, int(round(wb / wsum))))
            else:
                best_b, best_pid = max(set_dots, key=lambda d: d[0])
                cell_color = _sample_color(sb, best_pid, best_b, truecolor=False, color_enabled=True)
            cb.plot(x0 + c_off, y0 + r_off, zmax_l[idx], chr(0x2800 + bits), cell_color, bg=None)
        return
    for r_off in range(view_h):
        for c_off in range(view_w):
            bits = 0
            zmax = EMPTY_Z
            covered_dots = []
            set_dots = []
            for dy in range(4):
                sy0 = min(sh - 1, int((r_off + dy * 0.25) * sh / view_h))
                sy1 = min(sh, max(sy0 + 1, int((r_off + (dy + 1) * 0.25) * sh / view_h)))
                for dx in range(2):
                    sx0 = min(sw - 1, int((c_off + dx * 0.5) * sw / view_w))
                    sx1 = min(sw, max(sx0 + 1, int((c_off + (dx + 1) * 0.5) * sw / view_w)))
                    hit = _patch_dominant(sb, sy0, sy1, sx0, sx1)
                    if hit is None:
                        continue
                    zv, bv, pid, fl = hit
                    zmax = max(zmax, zv)
                    covered_dots.append((dy, dx, bv, pid))
                    threshold = _BAYER_2X4[dy][dx]
                    if bv >= threshold or (fl & FLAG_RIM):
                        bits |= _BRAILLE_BITS[dy][dx]
                        set_dots.append((bv, pid))
            if not covered_dots:
                continue
            if bits == 0:
                # Ensure silhouette/very dim covered cells still render at least one dot
                best_dy, best_dx, best_b, best_pid = max(covered_dots, key=lambda d: d[2])
                bits = _BRAILLE_BITS[best_dy][best_dx]
                set_dots.append((best_b, best_pid))

            if not color_enabled:
                cell_color: ColorValue = None
            else:
                # Brightness-weighted dominant colour of set dots
                wr = wg = wb = wsum = 0.0
                for bv, pid in set_dots:
                    col = _sample_color(sb, pid, bv, truecolor=True, color_enabled=True)
                    assert isinstance(col, tuple)
                    w = max(0.05, bv)
                    wr += col[0] * w
                    wg += col[1] * w
                    wb += col[2] * w
                    wsum += w
                if truecolor:
                    cell_color = (
                        min(255, int(round(wr / wsum))),
                        min(255, int(round(wg / wsum))),
                        min(255, int(round(wb / wsum))),
                    )
                else:
                    # Pick the set dot with highest brightness weight in 256 mode
                    best_b, best_pid = max(set_dots, key=lambda d: d[0])
                    cell_color = _sample_color(sb, best_pid, best_b, truecolor=False, color_enabled=True)

            cb.plot(x0 + c_off, y0 + r_off, zmax, chr(0x2800 + bits), cell_color, bg=None)


def _sextant_color(
    sb: SampleBuffer,
    dots,
    truecolor: bool,
    color_enabled: bool,
):
    if not color_enabled:
        return None
    if not truecolor:
        best_b, best_pid = max(dots, key=lambda dot: dot[0])
        return _sample_color(sb, best_pid, best_b, truecolor=False, color_enabled=True)
    wr = wg = wb = wsum = 0.0
    for bright, pid in dots:
        col = _sample_color(sb, pid, bright, truecolor=True, color_enabled=True)
        assert isinstance(col, tuple)
        weight = max(0.05, bright)
        wr += col[0] * weight
        wg += col[1] * weight
        wb += col[2] * weight
        wsum += weight
    return (min(255, int(round(wr / wsum))),
            min(255, int(round(wg / wsum))),
            min(255, int(round(wb / wsum))))


def _resolve_sextant(
    sb: SampleBuffer,
    cb: CellBuffer,
    clip: Tuple[int, int, int, int],
    truecolor: bool,
    color_enabled: bool,
) -> None:
    x0, y0, x1, y1 = clip
    view_w = max(1, x1 - x0)
    view_h = max(1, y1 - y0)
    sw, sh = sb.width, sb.height
    if HAS_NUMPY:
        dy_offs = (_np.arange(3, dtype=_np.float32) + 0.5) / 3.0
        dx_offs = (_np.arange(2, dtype=_np.float32) + 0.5) / 2.0
        sy_d = _np.clip(((_np.arange(view_h)[:, None] + dy_offs[None, :]) * sh / view_h).astype(_np.int32), 0, sh - 1)
        sx_d = _np.clip(((_np.arange(view_w)[:, None] + dx_offs[None, :]) * sw / view_w).astype(_np.int32), 0, sw - 1)
        sy_g = _np.broadcast_to(sy_d[:, :, None, None], (view_h, 3, view_w, 2)).transpose(0, 2, 1, 3)
        sx_g = _np.broadcast_to(sx_d[None, None, :, :], (view_h, 3, view_w, 2)).transpose(0, 2, 1, 3)
        zd = sb.z[sy_g, sx_g]
        cov = zd > EMPTY_Z * 0.5
        any_cov = _np.any(cov, axis=(2, 3))
        rows_c, cols_c = _np.where(any_cov)
        if rows_c.size == 0:
            return
        bayer = _np.array(_BAYER_2X3, dtype=_np.float32)
        bits_arr = _np.array(_SEXTANT_BITS, dtype=_np.int32)
        zd_c = zd[rows_c, cols_c]
        cov_c = cov[rows_c, cols_c]
        bd_c = sb.brightness[sy_g[rows_c, cols_c], sx_g[rows_c, cols_c]]
        pd_c = sb.palette_id[sy_g[rows_c, cols_c], sx_g[rows_c, cols_c]]
        fd_c = sb.flags[sy_g[rows_c, cols_c], sx_g[rows_c, cols_c]]
        on_c = cov_c & ((bd_c >= bayer[None, :, :]) | ((fd_c & FLAG_RIM) != 0))
        bits_set = _np.sum(_np.where(on_c, bits_arr[None, :, :], 0), axis=(1, 2))
        zmax_arr = _np.max(zd_c, axis=(1, 2))

        rows_l = rows_c.tolist()
        cols_l = cols_c.tolist()
        bits_l = bits_set.tolist()
        zmax_l = zmax_arr.tolist()
        on_l = on_c.tolist()
        cov_l = cov_c.tolist()
        bd_l = bd_c.tolist()
        pd_l = pd_c.tolist()
        for idx, (r_off, c_off) in enumerate(zip(rows_l, cols_l)):
            bits = bits_l[idx]
            dots = []
            if bits == 0:
                best = None
                for dy in range(3):
                    for dx in range(2):
                        if cov_l[idx][dy][dx]:
                            bv = bd_l[idx][dy][dx]
                            if best is None or bv > best[2]:
                                best = (dy, dx, bv, pd_l[idx][dy][dx])
                bits = _SEXTANT_BITS[best[0]][best[1]]
                dots.append((best[2], best[3]))
            else:
                for dy in range(3):
                    for dx in range(2):
                        if on_l[idx][dy][dx]:
                            dots.append((bd_l[idx][dy][dx], pd_l[idx][dy][dx]))
            cell_color = _sextant_color(sb, dots, truecolor, color_enabled)
            cb.plot(x0 + c_off, y0 + r_off, zmax_l[idx], _sextant_char(bits), cell_color, bg=None)
        return

    for r_off in range(view_h):
        for c_off in range(view_w):
            bits = 0
            zmax = EMPTY_Z
            covered_dots = []
            dots = []
            for dy in range(3):
                sy0 = min(sh - 1, int((r_off + dy / 3.0) * sh / view_h))
                sy1 = min(sh, max(sy0 + 1, int((r_off + (dy + 1) / 3.0) * sh / view_h)))
                for dx in range(2):
                    sx0 = min(sw - 1, int((c_off + dx * 0.5) * sw / view_w))
                    sx1 = min(sw, max(sx0 + 1, int((c_off + (dx + 1) * 0.5) * sw / view_w)))
                    hit = _patch_dominant(sb, sy0, sy1, sx0, sx1)
                    if hit is None:
                        continue
                    zv, bv, pid, fl = hit
                    zmax = max(zmax, zv)
                    covered_dots.append((dy, dx, bv, pid))
                    if bv >= _BAYER_2X3[dy][dx] or (fl & FLAG_RIM):
                        bits |= _SEXTANT_BITS[dy][dx]
                        dots.append((bv, pid))
            if not covered_dots:
                continue
            if bits == 0:
                best_dy, best_dx, best_b, best_pid = max(covered_dots, key=lambda dot: dot[2])
                bits = _SEXTANT_BITS[best_dy][best_dx]
                dots.append((best_b, best_pid))
            cell_color = _sextant_color(sb, dots, truecolor, color_enabled)
            cb.plot(x0 + c_off, y0 + r_off, zmax, _sextant_char(bits), cell_color, bg=None)
