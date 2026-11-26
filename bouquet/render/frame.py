"""Draw a scene through SampleBuffer -> post-process -> StyleResolver -> CellBuffer.

Scene composition and message animation follow Ascii-Flower-Bouquet by Alish Sharma (MIT); see NOTICE.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from ..config.themes import get_theme
from ..flowers import colorways as c
from ..flowers.colorways import ColorValue, sample_palette
from ..geometry.camera import Camera, Projector
from ..geometry.shading import LX, LY, LZ, brightness
from ..text import ELLIPSIS, ascii_text, cells, display_width, truncate
from .buffer import CellBuffer
from .flowers import Clip, SampleProjector, rasterise_flower_heads
from .resolvers import effective_style, resolve, resolve_truecolor
from .samples import (
    GC_BABY,
    GC_GREENERY,
    GC_LEAF,
    GC_OVERRIDE,
    GC_PAPER,
    GC_RIBBON,
    GC_SPARKLE,
    GC_STEM,
    HAS_NUMPY,
    SampleBuffer,
    apply_head_outlines,
)

if HAS_NUMPY:
    import numpy as _np  # type: ignore[import-not-found]

HEART_COLORS = c.HEART_COLORS
_PACKED_CACHE: Dict[Tuple[int, int, bool, str], tuple] = {}


def _pack_static_points(scene, show_ribbon: bool, wrap_style: str):
    """Pack scene.points + scene.greenery into NumPy arrays, cached per scene identity."""
    key = (id(scene), len(scene.points) + len(scene.greenery), show_ribbon, wrap_style)
    cached = _PACKED_CACHE.get(key)
    if cached is not None:
        return cached

    theme = get_theme(scene.theme_name)
    rib_pal = theme.ribbon_palette
    wrap_pal = c.PAPER if (scene.theme_name == "classic" and wrap_style == "kraft") else c.WRAP_PALETTES_256.get(wrap_style, c.PAPER)
    wrap_rgb = None if (scene.theme_name == "classic" and wrap_style == "kraft") else c.WRAP_RAMPS_RGB.get(wrap_style)

    all_pts = []
    for pt in scene.points:
        if not show_ribbon and pt[6] == rib_pal:
            continue
        all_pts.append(pt)
    for pt in scene.greenery:
        all_pts.append(pt)

    if not all_pts:
        return None

    pal_lookup: Dict[Tuple[int, ...], int] = {}
    pal_list: List[Tuple[Sequence[int], Optional[tuple]]] = []

    def get_pid(pal: Sequence[int]) -> int:
        pk = tuple(pal)
        if pk in pal_lookup:
            return pal_lookup[pk]
        pid = len(pal_list)
        rgb = wrap_rgb if pal == wrap_pal and wrap_rgb is not None else None
        pal_list.append((pk, rgb))
        pal_lookup[pk] = pid
        return pid

    n = len(all_pts)
    pos = _np.empty((n, 3), dtype=_np.float64)
    nrm = _np.empty((n, 3), dtype=_np.float64)
    pids = _np.empty(n, dtype=_np.int16)
    tones = _np.empty(n, dtype=_np.float64)
    two_sided = _np.empty(n, dtype=bool)
    gcs = _np.empty(n, dtype=_np.uint8)
    ccs = _np.empty(n, dtype=_np.uint8)
    oids = _np.empty(n, dtype=_np.int32)
    splat = _np.empty(n, dtype=bool)

    n_scene = len(scene.points)
    for i, (x, y, z, nx, ny, nz, pal, tone, ts, ov) in enumerate(all_pts):
        pos[i, 0] = x
        pos[i, 1] = y
        pos[i, 2] = z
        nrm[i, 0] = nx
        nrm[i, 1] = ny
        nrm[i, 2] = nz
        pids[i] = get_pid(pal)
        tones[i] = tone
        two_sided[i] = ts
        if i >= n_scene:
            gcs[i] = GC_GREENERY
            oids[i] = 1005
            splat[i] = False
        elif pal == wrap_pal:
            gcs[i] = GC_PAPER
            oids[i] = 1001
            splat[i] = True
        elif pal == rib_pal:
            gcs[i] = GC_RIBBON
            oids[i] = 1002
            splat[i] = True
        elif pal == c.GREENS:
            gcs[i] = GC_LEAF
            oids[i] = 1003
            splat[i] = False
        else:
            gcs[i] = GC_STEM
            oids[i] = 1004
            splat[i] = False
        ccs[i] = ord(ov[0]) if ov else 0

    entry = (pos, nrm, pids, tones, two_sided, gcs, ccs, oids, splat, pal_list)
    if len(_PACKED_CACHE) > 32:
        _PACKED_CACHE.clear()
    _PACKED_CACHE[key] = entry
    return entry


def _rasterise_static_numpy(
    sample_buf: SampleBuffer,
    projector: SampleProjector,
    scene,
    show_ribbon: bool,
) -> None:
    packed = _pack_static_points(scene, show_ribbon, scene.wrap_style)
    if packed is None:
        return
    pos, nrm, pids, tones, two_sided, gcs, ccs, oids, splat, pal_list = packed
    pid_map = _np.array([sample_buf.register_palette(p, r) for p, r in pal_list], dtype=_np.int16)

    ca, sa, ct, st = projector.ca, projector.sa, projector.ct, projector.st
    dist = projector.distance
    sw, sh = sample_buf.width, sample_buf.height

    x = pos[:, 0]
    y = pos[:, 1]
    z = pos[:, 2]
    xr = x * ca - z * sa
    zr = x * sa + z * ca
    yp = y - 0.34  # camera.PIVOT_Y
    yt = yp * ct - zr * st
    zt = yp * st + zr * ct
    denom = dist - zt

    nx = nrm[:, 0]
    ny = nrm[:, 1]
    nz = nrm[:, 2]
    rnx = nx * ca - nz * sa
    nzr = nx * sa + nz * ca
    rny = ny * ct - nzr * st
    rnz = ny * st + nzr * ct

    # Keep back wall of wrap cone visible (shaded dark via dot>=0) so tilted rim has no gap
    valid = denom >= 0.05
    if not _np.any(valid):
        return

    xr = xr[valid]
    yt = yt[valid]
    zt = zt[valid]
    denom = denom[valid]
    rnx = rnx[valid]
    rny = rny[valid]
    rnz = rnz[valid]
    ts_v = two_sided[valid]
    tones_v = tones[valid]
    pids_v = pid_map[pids[valid]]
    gcs_v = gcs[valid]
    ccs_v = ccs[valid]
    oids_v = oids[valid]
    splat_v = splat[valid]

    factor = dist / denom
    sx = _np.floor(projector.cx + xr * factor * projector.sx_scale).astype(_np.int32)
    sy = _np.floor(projector.cy - yt * factor * projector.scale).astype(_np.int32)

    in_bounds = (sx >= 0) & (sx < sw) & (sy >= 0) & (sy < sh)
    if not _np.any(in_bounds):
        return

    sx = sx[in_bounds]
    sy = sy[in_bounds]
    zt = zt[in_bounds]
    rnx = rnx[in_bounds]
    rny = rny[in_bounds]
    rnz = rnz[in_bounds]
    ts_v = ts_v[in_bounds]
    tones_v = tones_v[in_bounds]
    pids_v = pids_v[in_bounds]
    gcs_v = gcs_v[in_bounds]
    ccs_v = ccs_v[in_bounds]
    oids_v = oids_v[in_bounds]
    splat_v = splat_v[in_bounds]

    dot = rnx * LX + rny * LY + rnz * LZ
    dot = _np.where(ts_v & (dot < 0.0), -dot * 0.55, dot)
    bright = _np.clip(0.25 + 0.75 * _np.maximum(0.0, dot) + tones_v, 0.0, 0.999)

    # Expand wrap/ribbon points to their 2x2 neighborhood, then resolve every
    # write in one ordered pass.  Sorting by z ascending lets the frontmost
    # write win; the sequence tiebreak reproduces the pure-Python rule that an
    # earlier point wins when two depths are exactly equal.
    seq = _np.arange(zt.shape[0])
    parts = [
        [sx, sy, zt, bright, pids_v, gcs_v, ccs_v, oids_v, seq],
    ]
    if _np.any(splat_v):
        s_seq = seq[splat_v]
        s_sx = sx[splat_v]
        s_sy = sy[splat_v]
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1)):
            nx_s = s_sx + dx
            ny_s = s_sy + dy
            keep = (nx_s >= 0) & (nx_s < sw) & (ny_s >= 0) & (ny_s < sh)
            parts.append([
                nx_s[keep], ny_s[keep], zt[splat_v][keep], bright[splat_v][keep],
                pids_v[splat_v][keep], gcs_v[splat_v][keep],
                ccs_v[splat_v][keep], oids_v[splat_v][keep], s_seq[keep],
            ])
    flat = [_np.concatenate([part[i] for part in parts]) for i in range(9)]
    wx, wy, wz, wb, wpid, wgc, wcc, woid, wseq = flat

    order = _np.lexsort((-wseq, wz))
    wx = wx[order]
    wy = wy[order]
    wz = wz[order]
    flat_id = wy * sw + wx
    # Last write for a target wins.  With equal z that is the earlier point.
    _, first_rev = _np.unique(flat_id[::-1], return_index=True)
    keep = len(flat_id) - 1 - first_rev
    sample_buf.z[wy[keep], wx[keep]] = wz[keep]
    sample_buf.brightness[wy[keep], wx[keep]] = wb[order][keep]
    sample_buf.palette_id[wy[keep], wx[keep]] = wpid[order][keep]
    sample_buf.glyph_class[wy[keep], wx[keep]] = wgc[order][keep]
    sample_buf.char_code[wy[keep], wx[keep]] = wcc[order][keep]
    sample_buf.obj_id[wy[keep], wx[keep]] = woid[order][keep]


def _rasterise_static_python(
    sample_buf: SampleBuffer,
    projector: SampleProjector,
    scene,
    show_ribbon: bool,
) -> None:
    theme = get_theme(scene.theme_name)
    rib_pal = theme.ribbon_palette
    wrap_pal = c.PAPER if (scene.theme_name == "classic" and scene.wrap_style == "kraft") else c.WRAP_PALETTES_256.get(scene.wrap_style, c.PAPER)
    wrap_rgb = None if (scene.theme_name == "classic" and scene.wrap_style == "kraft") else c.WRAP_RAMPS_RGB.get(scene.wrap_style)
    normals = projector.rotate_normal

    for is_greenery, pts in ((False, scene.points), (True, scene.greenery)):
        for x, y, z, nx, ny, nz, pal, tone, two_sided, override in pts:
            if not is_greenery and not show_ribbon and pal == rib_pal:
                continue
            rnx, rny, rnz = normals(nx, ny, nz)
            result = projector.project_float(x, y, z)
            if result is None:
                continue
            px, py, zt, _ = result
            sx, sy = int(px), int(py)
            if not (0 <= sx < sample_buf.width and 0 <= sy < sample_buf.height):
                continue
            val = brightness(rnx, rny, rnz, tone, two_sided)
            rgb = wrap_rgb if pal == wrap_pal and wrap_rgb is not None else None
            pid = sample_buf.register_palette(pal, rgb)
            if is_greenery:
                gc, oid, splat = GC_GREENERY, 1005, False
            elif pal == wrap_pal:
                gc, oid, splat = GC_PAPER, 1001, True
            elif pal == rib_pal:
                gc, oid, splat = GC_RIBBON, 1002, True
            elif pal == c.GREENS:
                gc, oid, splat = GC_LEAF, 1003, False
            else:
                gc, oid, splat = GC_STEM, 1004, False
            cc = ord(override[0]) if override else 0
            sample_buf.plot(sx, sy, zt, val, pid, gc, cc, oid, 0)
            if splat:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1)):
                    sample_buf.plot(sx + dx, sy + dy, zt, val, pid, gc, cc, oid, 0)


def draw_scene(
    buffer: CellBuffer,
    scene,
    projector: Projector,
    settings,
    t: float,
    hearts,
    yaw: float,
    clip: Clip,
    head_scale: float,
    ascii_mode: bool = False,
    ghost=None,
    ghost_scale: float = 0.0,
    detail: Optional[int] = None,
    petal_fall=None,
    color_enabled: bool = True,
) -> None:
    x0, y0, x1, y1 = clip
    view_w = max(1, x1 - x0)
    view_h = max(1, y1 - y0)

    theme = get_theme(getattr(settings, "theme", "classic"))
    color_mode = getattr(settings, "color_mode", "auto")
    truecolor = resolve_truecolor(color_mode, color_enabled)
    style = effective_style(getattr(settings, "style", "ascii"), ascii_mode=ascii_mode, color_enabled=color_enabled)

    # 1. Background screen-space particles (never obscure bouquet, never drawn over message row)
    heart_glyph = "*" if ascii_mode else "\u2665"
    heart_pal = theme.heart_colors
    for col, row, color in hearts.positions(view_w, view_h, t):
        if 0 <= row < view_h and 0 <= col < view_w:
            if not color_enabled:
                h_col: ColorValue = None
            elif heart_pal and theme.name != "classic":
                idx = min(len(heart_pal) - 1, hash(col + row * 7) % len(heart_pal))
                h_col = sample_palette(heart_pal, idx / max(1, len(heart_pal) - 1), truecolor=truecolor)
            else:
                h_col = sample_palette(c.HEART_COLORS, (c.HEART_COLORS.index(color) / max(1, len(c.HEART_COLORS) - 1)) if color in c.HEART_COLORS else 0.5, truecolor=truecolor) if truecolor else color
            buffer.plot(x0 + col, y0 + row, -50.0, heart_glyph, h_col)

    if petal_fall is not None:
        for col, row, ch, p_col in petal_fall.positions(view_w, view_h, t, truecolor=truecolor):
            if 0 <= row < view_h and 0 <= col < view_w:
                buffer.plot(x0 + col, y0 + row, -40.0, ch, p_col if color_enabled else None)

    # 2. SampleBuffer size (height = detail, width preserves 2:1 cell aspect -> square samples)
    eff_detail = int(detail) if detail is not None else getattr(scene, "detail", 64)
    sample_h = max(16, eff_detail)
    sample_w = max(16, int(round(sample_h * view_w / max(1.0, view_h * 2.0))))
    sb = SampleBuffer(sample_w, sample_h)
    sp = SampleProjector(Camera(settings.camera, settings.tilt), sample_w, sample_h, yaw)

    if ghost is not None and ghost_scale > 0.02:
        rasterise_flower_heads(
            sb, sp, ghost.flowers, t, yaw, ghost_scale, settings,
            detail=sample_h, head_id_offset=500,
        )

    if HAS_NUMPY:
        _rasterise_static_numpy(sb, sp, scene, settings.ribbon)
    else:
        _rasterise_static_python(sb, sp, scene, settings.ribbon)

    projected = rasterise_flower_heads(
        sb, sp, scene.flowers, t, yaw, head_scale, settings, detail=sample_h,
    )
    if petal_fall is not None and projected:
        petal_fall.set_spawn_sources(projected)

    # 3. Baby's breath & sparkles at SampleBuffer resolution
    if settings.babies:
        pid_baby = sb.register_palette((231, 255))
        for x, y, z, phase in scene.babies:
            res = sp.project_float(x, y, z)
            if res is None:
                continue
            px, py, zt, _ = res
            star = math.sin(t * 2.0 + phase) > 0.6
            ch = "*" if star else ("." if ascii_mode else "\u00b7")
            sb.plot(int(px), int(py), zt + 0.02, 0.99 if star else 0.5, pid_baby, GC_BABY, ord(ch), 1006, 0)

    if settings.sparkles:
        pid_spark = sb.register_palette((218, 225, 231))
        for x, y, z, phase, speed in scene.sparkles:
            res = sp.project_float(x, y, z)
            if res is None:
                continue
            px, py, zt, _ = res
            twinkle = math.sin(t * speed + phase)
            if twinkle > 0.85:
                sb.plot(int(px), int(py), zt, 0.99, pid_spark, GC_SPARKLE, ord("*"), 1007, 0)
            elif twinkle > 0.4:
                sb.plot(int(px), int(py), zt, 0.65, pid_spark, GC_SPARKLE, ord("+"), 1007, 0)
            elif twinkle > 0.0:
                ch = "." if ascii_mode else "\u00b7"
                sb.plot(int(px), int(py), zt, 0.25, pid_spark, GC_SPARKLE, ord(ch), 1007, 0)

    # 4. Post-process head outlines (LEG-3) on object ids
    cell_samples_y = sample_h / max(1.0, float(view_h))
    apply_head_outlines(sb, cell_samples_y=cell_samples_y, enabled=getattr(settings, "outlines", True))

    # 5. Resolve SampleBuffer -> CellBuffer
    resolve(
        sb, buffer, clip,
        style=style,
        truecolor=truecolor,
        color_enabled=color_enabled,
        ascii_mode=ascii_mode,
    )


def message_color(settings, t: float, index: int, truecolor: bool = False) -> ColorValue:
    if settings.message_mode == "none":
        return None
    if settings.message_mode == "solid":
        from ..flowers.colorways import SOLID_MESSAGE_COLORS

        for name, color in SOLID_MESSAGE_COLORS:
            if name == settings.message_color:
                return sample_palette((color,), 0.5, truecolor=truecolor) if truecolor else color
        return 211
    theme = get_theme(getattr(settings, "theme", "classic"))
    palette = theme.msg_colors or c.MSG_COLORS
    shift = int(t * settings.message_speed)
    col = palette[(index + shift) % len(palette)]
    if truecolor:
        return sample_palette((col,), 0.5, truecolor=True)
    return col


def draw_message(
    buffer: CellBuffer,
    row: int,
    x: int,
    width: int,
    settings,
    t: float,
    ascii_mode: bool = False,
    color_enabled: bool = True,
) -> None:
    if not settings.message or width <= 0:
        return
    truecolor = resolve_truecolor(getattr(settings, "color_mode", "auto"), color_enabled)
    text = settings.message
    if ascii_mode:
        text = ascii_text(text)
    text = truncate(text, width, ellipsis=ELLIPSIS if not ascii_mode else "...")
    start = x + max(0, (width - display_width(text)) // 2)
    cursor = start
    cell_index = 0
    for cluster, cluster_width in cells(text):
        color = message_color(settings, t, cell_index, truecolor=truecolor) if color_enabled else None
        cursor = buffer.put_text(row, cursor, cluster, color, max_width=x + width - cursor)
        cell_index += max(1, cluster_width)


def draw_status(
    buffer: CellBuffer,
    row: int,
    width: int,
    left: str,
    right: str,
    ascii_mode: bool = False,
    color: ColorValue = 244,
) -> None:
    from ..text import ascii_text, fit, truncate

    if ascii_mode:
        left = ascii_text(left)
        right = ascii_text(right)
    available = max(0, width)
    if display_width(left) + display_width(right) + 1 <= available:
        text = left + " " * (available - display_width(left) - display_width(right)) + right
    else:
        text = truncate(left + "  " + right, available, ellipsis="" if ascii_mode else ELLIPSIS)
    buffer.put_text(row, 0, fit(text, available), color)
