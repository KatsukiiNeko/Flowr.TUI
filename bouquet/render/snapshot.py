"""Deterministic snapshots (plain text or ANSI), used by the CLI and tests."""

from __future__ import annotations

import math

from ..config.settings import Settings
from ..flowers.colorways import ColorValue
from ..geometry.camera import Camera, Projector, Viewport
from ..scene.hearts import Hearts
from ..scene.petals import PetalFall
from ..scene.scene import build_scene
from .buffer import CellBuffer
from .frame import draw_message, draw_scene
from .presenter import bg_escape, fg_escape
from .resolvers import auto_detail_target, effective_style
from .samples import HAS_NUMPY


def _resolve_snapshot_detail(settings: Settings, height: int) -> int:
    if settings.detail == "auto":
        style = effective_style(settings.style)
        return auto_detail_target(height, style, HAS_NUMPY)
    return int(settings.detail)


def render_snapshot(
    settings: Settings,
    width: int = 80,
    height: int = 24,
    at: float = 0.0,
    ascii_mode: bool = False,
    color: bool = False,
) -> str:
    width = max(20, width)
    height = max(12, height)
    eff_detail = _resolve_snapshot_detail(settings, height)
    scene = build_scene(settings, detail=eff_detail)
    hearts = Hearts(settings.hearts, settings.seed)
    petals = PetalFall(settings.petal_fall, settings.seed) if settings.petal_fall > 0 else None
    at = max(0.0, at)
    hearts.advance(at)
    if petals is not None:
        petals.advance(at)
    sway = 0.0
    if settings.sway:
        sway = math.radians(settings.sway_degrees) * math.sin(at * 1.1)
    yaw = at * settings.spin + sway
    projector = Projector(
        Camera(settings.camera, settings.tilt),
        Viewport(width, height - 2, 0, 0),
        yaw,
    )
    buffer = CellBuffer(width, height)
    draw_scene(
        buffer, scene, projector, settings, at, hearts, yaw,
        (0, 0, width, height - 2), scene.head_scale, ascii_mode,
        detail=eff_detail, petal_fall=petals, color_enabled=color,
    )
    draw_message(buffer, height - 2, 0, width, settings, at, ascii_mode, color_enabled=color)
    if color:
        return buffer_to_ansi(buffer)
    return buffer.text() + "\n"


def buffer_to_ansi(buffer: CellBuffer) -> str:
    lines = []
    for row in range(buffer.rows):
        parts = []
        current_fg: ColorValue = None
        current_bg: ColorValue = None
        for col in range(buffer.cols):
            char = buffer.chars[row][col]
            if char == "":
                continue
            fg = buffer.colors[row][col]
            bg = buffer.bg_colors[row][col]
            if fg != current_fg:
                current_fg = fg
                parts.append(fg_escape(fg))
            if bg != current_bg:
                current_bg = bg
                parts.append(bg_escape(bg))
            parts.append(char)
        if current_fg is not None or current_bg is not None:
            parts.append("\x1b[0m")
        lines.append("".join(parts).rstrip())
    return "\n".join(lines) + "\n"
