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


def samples_per_cell(style: str) -> Tuple[int, int]:
    if style == "half":
        return 1, 2
    if style == "braille":
        return 2, 4
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
    if requested not in ("ascii", "half", "braille"):
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
) -> None:
    """Resolve *sample_buf* into *cell_buf* inside *clip* = (x0, y0, x1, y1)."""
    style = effective_style(style, ascii_mode=ascii_mode, color_enabled=color_enabled)
    if style == "half":
        _resolve_half(sample_buf, cell_buf, clip, truecolor, color_enabled)
    elif style == "braille":
        _resolve_braille(sample_buf, cell_buf, clip, truecolor, color_enabled)
    else:
        _resolve_ascii(sample_buf, cell_buf, clip, truecolor, color_enabled, ascii_mode)


def _resolve_ascii(
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
