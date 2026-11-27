"""Plain/ANSI gallery of every registered variety at three head sizes.

Honours detail, style and theme settings (UX-4, DET-6).
"""

from __future__ import annotations

from typing import List

from ..config.settings import Settings
from ..config.themes import assign_themed_hues, get_theme, resolve_themed_colorway
from ..flowers import all_varieties
from ..geometry.camera import Camera, Projector, Viewport
from ..scene.scene import FlowerHead
from ..text import fit
from .buffer import CellBuffer
from .flowers import SampleProjector, rasterise_flower_heads
from .presenter import bg_escape, fg_escape
from .resolvers import effective_style, resolve, resolve_truecolor
from .samples import HAS_NUMPY, SampleBuffer

SIZES = (("Small", 7, 3), ("Medium", 10, 5), ("Large", 13, 7))


def _render_variety_box(
    spec,
    colorway,
    width: int,
    height: int,
    detail: int,
    style: str,
    truecolor: bool,
    ansi: bool,
    ascii_mode: bool,
    block_width: int,
    settings: Settings,
) -> List[str]:
    sb_h = max(12, min(detail, height * 4))
    sb_w = max(8, int(round(sb_h * width / max(1.0, height * 2.0))))
    sb = SampleBuffer(sb_w, sb_h)
    # Build a synthetic single-head projection centered in sb
    head = FlowerHead((0.0, 0.34, 0.0), (0.0, 1.0, 0.0), spec, colorway, 0.50, 0.4)
    sp = _GalleryProjector(sb_w, sb_h)
    rasterise_flower_heads(sb, sp, (head,), 0.0, 0.0, 1.0, settings, detail=sb_h, phase_scale=0.0)
    cb = CellBuffer(width, height)
    resolve(sb, cb, (0, 0, width, height), style=style, truecolor=truecolor, color_enabled=ansi, ascii_mode=ascii_mode)

    pad_l = " " * ((block_width - width) // 2)
    pad_r = " " * ((block_width - width + 1) // 2)
    out = []
    for r in range(height):
        if not ansi:
            out.append(pad_l + "".join(cb.chars[r]) + pad_r)
            continue
        parts = [pad_l]
        cur_fg = None
        cur_bg = None
        for c_idx in range(width):
            fg = cb.colors[r][c_idx]
            bg = cb.bg_colors[r][c_idx]
            if fg != cur_fg:
                cur_fg = fg
                parts.append(fg_escape(fg))
            if bg != cur_bg:
                cur_bg = bg
                parts.append(bg_escape(bg))
            parts.append(cb.chars[r][c_idx])
        if cur_fg is not None or cur_bg is not None:
            parts.append("\x1b[0m")
        parts.append(pad_r)
        out.append("".join(parts))
    return out


class _GalleryProjector(SampleProjector):
    def __init__(self, sw: int, sh: int) -> None:
        self.distance = 4.0
        self.tilt = 0.0
        self.scale = min(sw, sh) * 0.82
        self.cx = sw / 2.0
        self.cy = sh / 2.0
        self.sx_scale = self.scale
        self.ca = 1.0
        self.sa = 0.0
        self.ct = 1.0
        self.st = 0.0


def gallery_lines(
    settings: Settings,
    ansi: bool = False,
    ascii_mode: bool = False,
    max_width: int = 0,
) -> List[str]:
    varieties = list(all_varieties())
    theme = get_theme(getattr(settings, "theme", "classic"))
    style = effective_style(getattr(settings, "style", "ascii"), ascii_mode=ascii_mode, color_enabled=ansi)
    truecolor = resolve_truecolor(getattr(settings, "color_mode", "auto"), ansi)
    if settings.detail == "auto":
        detail = 64 if not HAS_NUMPY else 128
    else:
        detail = int(settings.detail)

    hues = assign_themed_hues(theme, len(varieties), settings.seed) if theme.name not in ("classic", "rainbow") else None

    rows = [
        "Bouquet TUI  -  ten flower varieties (theme: %s, detail: %sx, style: %s)"
        % (theme.name, detail, style),
        "",
    ]
    for size_name, cell_w, cell_h in SIZES:
        rows.append("%s heads (%dx%d cells)" % (size_name, cell_w, cell_h))
        for start in range(0, len(varieties), 5):
            group = varieties[start:start + 5]
            block_width = max(15, cell_w)
            rows.append("  ".join(fit(spec.name, block_width) for spec in group).rstrip())
            rendered_boxes = []
            for idx, spec in enumerate(group):
                if hues is not None:
                    cw = resolve_themed_colorway(spec, hues[start + idx], theme)
                else:
                    cw = spec.colorways[0]
                rendered_boxes.append(_render_variety_box(
                    spec, cw, cell_w, cell_h, detail, style, truecolor, ansi, ascii_mode, block_width, settings
                ))
            for y in range(cell_h):
                rows.append("  ".join(box[y] for box in rendered_boxes).rstrip())
            rows.append("")
    rows.append("Inspired by Ascii-Flower-Bouquet by Alish Sharma (MIT).")
    if max_width and not ansi:
        rows = [fit(line, max_width) for line in rows]
    return rows
