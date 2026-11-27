"""Interactive application loop and screen composition."""

from __future__ import annotations

import dataclasses
import math
import random
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

from ..config.settings import (
    PRESETS,
    TABS,
    Settings,
    apply_preset,
    sanitize_message,
)
from ..config.storage import default_config_path, load_settings, save_settings
from ..config.themes import CURATED_THEME_NAMES, get_theme
from ..geometry.camera import Camera, Projector, Viewport
from ..platform.keys import KeyParser
from ..platform.terminal import Terminal, Terminate
from ..render.buffer import CellBuffer
from ..render.frame import draw_message, draw_scene, draw_status
from ..render.presenter import AnsiPresenter
from ..render.resolvers import auto_detail_target, effective_style
from ..render.samples import HAS_NUMPY
from ..scene.composition import recommended_flower_count, themed_shuffle_counts
from ..scene.hearts import Hearts
from ..scene.petals import PetalFall
from ..scene.scene import Scene, build_scene
from ..text import display_width, truncate
from .editor import MessageEditor
from .help import draw_help
from .keymap import footer_hint
from .panel import Panel
from .widgets import draw_box, draw_confirm

TRANSITION_SECONDS = 0.4
MIN_COLS = 20
MIN_ROWS = 12
REBUILD_FIELDS = {
    "layout", "seed", "sparkle_density", "baby_density",
    "greenery_amount", "greenery_type", "theme", "wrap", "detail",
}
DETAIL_LEVELS = (32, 64, 128, 256)
AUTO_HYSTERESIS_SECONDS = 5.0


class App:
    def __init__(
        self,
        settings: Settings,
        config_path: Optional[Path] = None,
        config_enabled: bool = True,
        ascii_mode: bool = False,
        color: bool = True,
        start_at: float = 0.0,
    ) -> None:
        self.settings = settings
        if ascii_mode:
            self.settings.style = "ascii"
        self.config_path = Path(config_path) if config_path is not None else default_config_path()
        self.config_enabled = config_enabled
        self.ascii_mode = ascii_mode
        self.color = color
        self.presenter = AnsiPresenter(color=color)
        self.terminal = Terminal(self.presenter)
        self.parser = KeyParser()

        self.actual_size = (80, 24)
        self.cols = 79
        self.rows = 23
        self._auto_detail = auto_detail_target(self.actual_size[1], self._eff_style(), HAS_NUMPY)
        self._last_auto_change = 0.0
        self._low_fps_since: Optional[float] = None
        self._perf_hint_shown = False

        init_detail = self.active_detail()
        self._detail_cache: Dict[Tuple, Scene] = {}
        self.scene: Scene = self._build_and_cache(settings, init_detail)
        self._static_key = self._make_static_key(settings, init_detail)

        self._rebuild_lock = threading.Lock()
        self._pending_scene: Optional[Scene] = None
        self._rebuilding_detail = False

        self.hearts = Hearts(settings.hearts, settings.seed)
        self.petals = PetalFall(settings.petal_fall, settings.seed)
        self.t = max(0.0, start_at)
        self.yaw = self.t * settings.spin
        if self.t > 0:
            self.hearts.advance(self.t)
            self.petals.advance(self.t)
        self.spin_rate = 0.0 if settings.paused else settings.spin
        self.scene_birth = self.t - TRANSITION_SECONDS
        self.ghost_scene: Optional[Scene] = None
        self.ghost_start = 0.0
        self.panel: Optional[Panel] = None
        self.editor: Optional[MessageEditor] = None
        self.help_open = False
        self.confirm_reset = False
        self.running = True
        self.dirty = True
        self.pending_keys: List[str] = []
        self.frame_stamps: Deque[float] = deque()
        self.fps_actual = 0.0
        self.toast_text = ""
        self.toast_until = 0.0
        self._last_size: Optional[Tuple[int, int]] = None
        self._glyph_history: Dict[Tuple[int, int], str] = {}
        self.too_small = False
        self.buffer = CellBuffer(self.cols, self.rows)

    def _eff_style(self) -> str:
        return effective_style(self.settings.style, ascii_mode=self.ascii_mode, color_enabled=self.color)

    def active_detail(self) -> int:
        if self.settings.detail == "auto":
            return self._auto_detail
        return int(self.settings.detail)

    def recommended_count(self) -> int:
        vp = Viewport(max(1, self.cols), max(1, self.rows - 2), 0, 0)
        return recommended_flower_count(vp, self.settings.detail, self._eff_style())

    def _make_static_key(self, settings: Settings, detail: int) -> Tuple:
        return (
            detail, settings.seed, settings.baby_density, settings.sparkle_density,
            settings.greenery_amount, settings.greenery_type, settings.theme, settings.wrap,
        )

    def _build_and_cache(self, settings: Settings, detail: int, reusable: Optional[Scene] = None) -> Scene:
        key = self._make_static_key(settings, detail)
        if reusable is None:
            reusable = self._detail_cache.get(key)
        scene = build_scene(settings, static_scene=reusable, detail=detail)
        if len(self._detail_cache) >= 8:
            self._detail_cache.clear()
        self._detail_cache[key] = scene
        return scene

    # -- public ------------------------------------------------------------
    def toast(self, message: str, seconds: float = 4.0) -> None:
        self.toast_text = message
        self.toast_until = time.monotonic() + seconds

    def run(self) -> None:
        self.terminal.install_signal_handlers()
        try:
            self.terminal.enter()
            self._resize(force=True)
            last = time.perf_counter()
            while self.running:
                now = time.perf_counter()
                dt = min(0.1, max(0.0, now - last))
                last = now
                self._check_terminal()
                self._poll_rebuild()
                if not self.running:
                    break
                if self.pending_keys:
                    keys = self.pending_keys
                    self.pending_keys = []
                    for key in keys:
                        self.handle_key(key)
                        if not self.running:
                            break
                self._update(dt)
                interval = 1.0 / max(1, self.settings.fps)
                if self.dirty:
                    self._draw()
                    timeout = max(0.0, interval - (time.perf_counter() - now))
                else:
                    timeout = 0.1 if self._rebuilding_detail else 0.5
                data = self.terminal.read(timeout)
                if data:
                    self.pending_keys.extend(self.parser.feed(data))
                else:
                    flushed = self.parser.flush()
                    if flushed:
                        self.pending_keys.extend(flushed)
        except (Terminate, KeyboardInterrupt):
            pass
        finally:
            self._shutdown()

    # -- input -------------------------------------------------------------
    def handle_key(self, key: str) -> None:
        self.dirty = True
        if key == "ctrl-c":
            self.running = False
            return
        if self.editor is not None:
            result = self.editor.handle(key)
            if result == "commit":
                self.settings.message = self.editor.result()
                self.editor = None
                self._mark_custom(["message"])
                self.toast("Message saved")
            elif result == "cancel":
                self.editor = None
            return
        if self.confirm_reset:
            if key == "enter":
                self.restore_defaults()
            elif key in ("esc",):
                self.confirm_reset = False
            elif key == "q":
                self.running = False
            return
        if key == "q":
            self.running = False
            return
        if self.help_open:
            if key in ("?", "esc", "tab"):
                self.help_open = False
            return
        if key == "?":
            self.help_open = True
            return
        if key == "space":
            self.settings.paused = not self.settings.paused
            self.toast("Paused" if self.settings.paused else "Playing")
            return
        if key == "tab":
            self.panel = None if self.panel is not None else Panel()
            return
        if key in ("[", "]"):
            if self.panel is None:
                self.panel = Panel()
            self.panel.next_tab(-1 if key == "[" else 1)
            return
        if self.panel is not None and key in ("1", "2", "3", "4", "5", "6"):
            idx = int(key) - 1
            if 0 <= idx < len(TABS):
                self.panel.tab_index = idx
            return
        if key == "v":
            self.cycle_detail()
            return
        if key == "m":
            self.open_editor()
            return
        if key == "s":
            self.shuffle()
            return
        if key == "r":
            self.reset_animation()
            return
        if key == "D":
            self.confirm_reset = True
            return
        if key in ("+", "="):
            self._nudge_fps(1)
            return
        if key in ("-", "_"):
            self._nudge_fps(-1)
            return
        if self.panel is None:
            return
        if key in ("up", "down"):
            self.panel.move(-1 if key == "up" else 1, self.settings)
        elif key in ("shift-up", "shift-down", "shift-left", "shift-right"):
            direction = -1 if key in ("shift-up", "shift-left") else 1
            field = self.panel.adjust(self.settings, direction, coarse=True)
            self._panel_change(field)
        elif key in ("left", "right"):
            field = self.panel.adjust(self.settings, -1 if key == "left" else 1)
            self._panel_change(field)
        elif key in ("pgup", "shift-pgup"):
            field = self.panel.adjust(self.settings, -1, coarse=True)
            self._panel_change(field)
        elif key in ("pgdn", "shift-pgdn"):
            field = self.panel.adjust(self.settings, 1, coarse=True)
            self._panel_change(field)
        elif key == "enter":
            self.panel.activate(self)
        elif key == "esc":
            self.panel = None

    def _panel_change(self, field: Optional[str]) -> None:
        if field == "total":
            self.toast("Flower total is capped at %d" % 24, 2.5)
        elif field == "empty":
            self.toast("Keep at least one flower", 2.5)
        elif field:
            self.on_settings_changed([field])

    def _nudge_fps(self, delta: int) -> None:
        self.settings.fps = max(5, min(60, self.settings.fps + delta))
        self._mark_custom(["fps"])
        self.toast("Target FPS: %d" % self.settings.fps, 1.5)

    def cycle_detail(self) -> None:
        choices = ("auto", "32", "64", "128", "256")
        idx = choices.index(self.settings.detail) if self.settings.detail in choices else 0
        self.settings.detail = choices[(idx + 1) % len(choices)]
        self.on_settings_changed(["detail"])
        eff = self.active_detail()
        if not HAS_NUMPY and eff >= 128:
            self.toast("Detail %dx is slow without NumPy" % eff, 4.0)
        else:
            label = "Auto->%dx" % eff if self.settings.detail == "auto" else "%dx" % eff
            self.toast("Detail: %s" % label, 2.0)

    def open_editor(self) -> None:
        self.panel = None
        self.editor = MessageEditor(self.settings.message)

    def shuffle(self) -> None:
        rng = random.SystemRandom()
        seed = rng.randrange(0, 1000000)
        theme_name = rng.choice(CURATED_THEME_NAMES)
        theme = get_theme(theme_name)
        self.settings.seed = seed
        self.settings.theme = theme_name
        self.settings.wrap = theme.wrap_style
        self.settings.counts = themed_shuffle_counts(theme_name, self.recommended_count(), seed)
        self.settings.colorways = {vid: -1 for vid in self.settings.colorways}
        self._mark_custom(["seed", "theme"])
        self.rebuild()
        self.toast("Shuffled · %s · seed %d" % (theme.label, seed))

    def reset_animation(self) -> None:
        self.t = 0.0
        self.yaw = 0.0
        self.spin_rate = 0.0 if self.settings.paused else self.settings.spin
        self.hearts = Hearts(self.settings.hearts, self.settings.seed)
        self.petals = PetalFall(self.settings.petal_fall, self.settings.seed)
        self.ghost_scene = None
        self.scene_birth = -TRANSITION_SECONDS
        self.toast("Animation reset")

    def restore_defaults(self) -> None:
        self.confirm_reset = False
        self.settings = Settings()
        if self.ascii_mode:
            self.settings.style = "ascii"
        self.t = 0.0
        self.yaw = 0.0
        self.spin_rate = self.settings.spin
        self.hearts = Hearts(self.settings.hearts, self.settings.seed)
        self.petals = PetalFall(self.settings.petal_fall, self.settings.seed)
        self.ghost_scene = None
        detail = self.active_detail()
        self.scene = self._build_and_cache(self.settings, detail)
        self._static_key = self._make_static_key(self.settings, detail)
        self.scene_birth = -TRANSITION_SECONDS
        self.toast("Defaults restored")

    def panel_action(self, action: str, data=None) -> None:
        if action == "edit_message":
            self.open_editor()
        elif action == "preset" and isinstance(data, str):
            self.settings = apply_preset(self.settings, data)
            if self.ascii_mode:
                self.settings.style = "ascii"
            self.hearts = Hearts(self.settings.hearts, self.settings.seed)
            self.petals = PetalFall(self.settings.petal_fall, self.settings.seed)
            self.ghost_scene = None
            detail = self.active_detail()
            self.scene = self._build_and_cache(self.settings, detail)
            self._static_key = self._make_static_key(self.settings, detail)
            self.scene_birth = self.t - TRANSITION_SECONDS
            self.toast("Preset: %s" % data)
        elif action == "save":
            self.save_now()
        elif action == "load":
            self.load_now()
        elif action == "defaults":
            self.confirm_reset = True
        elif action == "reset_animation":
            self.reset_animation()
        elif action == "shuffle":
            self.shuffle()

    def save_now(self) -> None:
        if not self.config_enabled:
            self.toast("Config disabled (--no-config)", 4)
            return
        self.settings.repair()
        error = save_settings(self.settings, self.config_path)
        self.toast(("Saved " + str(self.config_path)) if error is None else error, 5)

    def load_now(self) -> None:
        if not self.config_enabled:
            self.toast("Config disabled (--no-config)", 4)
            return
        settings, warnings = load_settings(self.config_path)
        self.settings = settings
        if self.ascii_mode:
            self.settings.style = "ascii"
        self.settings.paused = False
        self.hearts = Hearts(self.settings.hearts, self.settings.seed)
        self.petals = PetalFall(self.settings.petal_fall, self.settings.seed)
        self.ghost_scene = None
        detail = self.active_detail()
        self.scene = self._build_and_cache(self.settings, detail)
        self._static_key = self._make_static_key(self.settings, detail)
        self.scene_birth = self.t - TRANSITION_SECONDS
        if warnings:
            self.toast("Loaded with repairs: " + warnings[0], 5)
        else:
            self.toast("Loaded " + str(self.config_path), 4)

    def on_settings_changed(self, fields: List[str]) -> None:
        if not fields:
            return
        self._mark_custom(fields)
        if "hearts" in fields:
            self.hearts.set_target(self.settings.hearts)
        if "petal_fall" in fields:
            self.petals.set_target(self.settings.petal_fall)
        if "theme" in fields:
            self.settings.wrap = get_theme(self.settings.theme).wrap_style
        if "style" in fields and self.ascii_mode:
            self.settings.style = "ascii"
        if {"detail", "style", "theme", "color_mode"} & set(fields):
            self._glyph_history.clear()
        if "detail" in fields:
            self._perf_hint_shown = False
            self._low_fps_since = None
            eff = self.active_detail()
            if not HAS_NUMPY and eff >= 128:
                self.toast("Detail %dx is slow without NumPy" % eff, 4.0)
            self.rebuild(async_detail=True)
            return
        changed = set(fields)
        rebuild = bool(changed & REBUILD_FIELDS)
        rebuild = rebuild or any(field.endswith("_count") for field in changed)
        rebuild = rebuild or any(field.startswith("colorway:") for field in changed)
        if rebuild:
            self.rebuild(async_detail=False)
        if "message" in fields:
            self.settings.message = sanitize_message(self.settings.message)

    def _mark_custom(self, fields: List[str]) -> None:
        display_only = {"paused", "detail", "style", "color_mode"}
        if any(field not in display_only for field in fields):
            if self.settings.preset != "Custom":
                self.settings.preset = "Custom"

    def rebuild(self, async_detail: bool = False) -> None:
        detail = self.active_detail()
        static_key = self._make_static_key(self.settings, detail)
        cached = self._detail_cache.get(static_key)
        if cached is not None and not any(
            getattr(self.settings, f, None) != getattr(cached, f, None)
            for f in ()
        ) and static_key == self._static_key:
            self.scene = cached
            return
        if async_detail and cached is None and detail >= 128:
            self._start_detail_rebuild(detail)
            return
        self.ghost_scene = self.scene
        self.ghost_start = self.t
        reusable = self.scene if static_key == self._static_key else cached
        self.scene = self._build_and_cache(self.settings, detail, reusable=reusable)
        self._static_key = static_key
        self.scene_birth = self.t

    def _start_detail_rebuild(self, detail: int) -> None:
        settings_copy = dataclasses.replace(
            self.settings,
            counts=dict(self.settings.counts),
            colorways=dict(self.settings.colorways),
        )
        self._rebuilding_detail = True

        def worker() -> None:
            scene = build_scene(settings_copy, detail=detail)
            key = self._make_static_key(settings_copy, detail)
            with self._rebuild_lock:
                self._detail_cache[key] = scene
                self._pending_scene = scene

        threading.Thread(target=worker, daemon=True).start()

    def _poll_rebuild(self) -> None:
        if not self._rebuilding_detail:
            return
        with self._rebuild_lock:
            pending = self._pending_scene
            if pending is not None:
                self._pending_scene = None
                self._rebuilding_detail = False
                self.scene = pending
                self._static_key = self._make_static_key(self.settings, pending.detail)
                self.dirty = True

    # -- loop --------------------------------------------------------------
    def _check_terminal(self) -> None:
        if self.terminal.suspend_pending:
            self.terminal.suspend_pending = False
            self.toast("Resumed", 2)
            self.terminal.suspend()
            self._resize(force=True)
            return
        size = self.terminal.size()
        if self._last_size != size:
            self._resize(size)

    def _resize(self, size: Optional[Tuple[int, int]] = None, force: bool = False) -> None:
        if size is None:
            size = self.terminal.size()
        self._last_size = size
        width, height = size
        self.actual_size = (width, height)
        self.too_small = width < MIN_COLS or height < MIN_ROWS
        self.dirty = True
        cols = max(1, width - 1)
        rows = max(1, height - 1)
        if force or cols != self.buffer.cols or rows != self.buffer.rows:
            self.buffer = CellBuffer(cols, rows)
            self.cols, self.rows = cols, rows
            self._glyph_history.clear()
            self.presenter.invalidate()
        self._maybe_update_auto_detail(time.monotonic(), allow_upgrade=True)

    def _maybe_update_auto_detail(self, now: float, allow_upgrade: bool = False) -> None:
        if self.settings.detail != "auto":
            return
        if now - self._last_auto_change < AUTO_HYSTERESIS_SECONDS and not allow_upgrade:
            return
        target = auto_detail_target(self.actual_size[1], self._eff_style(), HAS_NUMPY)
        if self.fps_actual > 0 and self.fps_actual < 0.5 * self.settings.fps:
            if self._low_fps_since is None:
                self._low_fps_since = now
            elif now - self._low_fps_since >= 2.0 and now - self._last_auto_change >= AUTO_HYSTERESIS_SECONDS:
                idx = DETAIL_LEVELS.index(self._auto_detail) if self._auto_detail in DETAIL_LEVELS else 1
                if idx > 0:
                    self._auto_detail = DETAIL_LEVELS[idx - 1]
                    self._glyph_history.clear()
                    self._last_auto_change = now
                    self._low_fps_since = None
                    self.rebuild(async_detail=True)
            return
        else:
            self._low_fps_since = None
        if target != self._auto_detail and (now - self._last_auto_change >= AUTO_HYSTERESIS_SECONDS or self._last_auto_change == 0.0):
            self._auto_detail = target
            self._glyph_history.clear()
            self._last_auto_change = now
            self.rebuild(async_detail=True)

    def _check_explicit_perf(self, now: float) -> None:
        if self.settings.detail == "auto" or self.settings.paused or self._perf_hint_shown:
            return
        if self.fps_actual > 0 and self.fps_actual < 0.5 * self.settings.fps:
            if self._low_fps_since is None:
                self._low_fps_since = now
            elif now - self._low_fps_since >= 2.0:
                cur = int(self.settings.detail)
                idx = DETAIL_LEVELS.index(cur) if cur in DETAIL_LEVELS else 1
                if idx > 0:
                    self.toast("Detail too high for this machine, try %dx" % DETAIL_LEVELS[idx - 1], 6.0)
                self._perf_hint_shown = True
        else:
            self._low_fps_since = None

    def _update(self, dt: float) -> None:
        settings = self.settings
        target = 0.0 if settings.paused else settings.spin
        previous_rate = self.spin_rate
        max_step = max(0.1, abs(settings.spin - self.spin_rate)) / 0.3 * dt
        if self.spin_rate < target:
            self.spin_rate = min(target, self.spin_rate + max_step)
        elif self.spin_rate > target:
            self.spin_rate = max(target, self.spin_rate - max_step)
        if self.spin_rate != previous_rate:
            self.dirty = True
        if self.spin_rate != 0.0:
            self.yaw += self.spin_rate * dt
        if not settings.paused:
            self.t += dt
            self.hearts.update(dt, self.t)
            self.petals.update(dt, self.t)
            self.dirty = True
        self.hearts.set_target(settings.hearts)
        self.petals.set_target(settings.petal_fall)
        if self.ghost_scene is not None and self.t - self.ghost_start >= TRANSITION_SECONDS:
            self.ghost_scene = None
            self.dirty = True
        now = time.monotonic()
        self._maybe_update_auto_detail(now)
        self._check_explicit_perf(now)

    def _draw(self) -> None:
        buffer = self.buffer
        buffer.clear()
        if self.too_small:
            self._draw_too_small(buffer)
            self.presenter.render(buffer)
            self.dirty = False
            return

        cols, rows = buffer.cols, buffer.rows
        if self.panel is not None and self.actual_size[0] >= 100:
            panel_w = 38
            scene_w = cols - panel_w
            clip = (0, 0, scene_w, max(1, rows - 2))
            panel_rect = (scene_w, 0, panel_w, rows - 1)
        elif self.panel is not None and self.actual_size[0] >= 60 and self.actual_size[1] >= 18:
            panel_w = min(cols - 4, 66)
            panel_h = min(rows - 6, 14)
            panel_x = (cols - panel_w) // 2
            panel_y = rows - 2 - panel_h
            scene_w = cols
            clip = (0, 0, scene_w, max(1, rows - 2))
            panel_rect = (panel_x, panel_y, panel_w, panel_h)
        elif self.panel is not None:
            scene_w = cols
            clip = (0, 0, cols, max(1, rows - 2))
            panel_rect = (1, 0, max(2, cols - 2), rows - 1)
        else:
            scene_w = cols
            clip = (0, 0, cols, max(1, rows - 2))
            panel_rect = None

        settings = self.settings
        sway = 0.0
        if settings.sway:
            sway = math.radians(settings.sway_degrees) * math.sin(self.t * 1.1)
        yaw = self.yaw + sway
        viewport = Viewport(scene_w, max(1, rows - 2), 0, 0)
        projector = Projector(Camera(settings.camera, settings.tilt), viewport, yaw)
        age = self.t - self.scene_birth
        head_scale = self.scene.head_scale * (1.0 if age >= TRANSITION_SECONDS else max(0.0, age / TRANSITION_SECONDS))
        ghost_scale = 0.0
        if self.ghost_scene is not None:
            ghost_scale = max(0.0, 1.0 - (self.t - self.ghost_start) / TRANSITION_SECONDS)
        draw_scene(
            buffer, self.scene, projector, settings, self.t, self.hearts, yaw,
            clip, head_scale, self.ascii_mode, self.ghost_scene, ghost_scale,
            detail=self.scene.detail,
            petal_fall=self.petals if settings.petal_fall > 0 else None,
            color_enabled=self.color,
            glyph_history=self._glyph_history,
        )
        draw_message(buffer, rows - 2, 0, scene_w, settings, self.t, self.ascii_mode, color_enabled=self.color)

        if self.help_open:
            draw_help(buffer, self.ascii_mode)
        elif self.panel is not None and panel_rect is not None:
            self.panel.draw(buffer, settings, self, panel_rect, self.ascii_mode)

        if self.confirm_reset:
            draw_confirm(buffer, self.ascii_mode)

        cursor = None
        if self.editor is not None:
            cursor = self._draw_editor(buffer)
        self._draw_status(buffer, rows - 1, cols)
        self._record_frame()
        self.presenter.render(buffer, cursor)
        self.dirty = False

    def _draw_too_small(self, buffer: CellBuffer) -> None:
        lines = [
            "Terminal too small",
            "Need %dx%d" % (MIN_COLS, MIN_ROWS),
            "Have %dx%d" % self.actual_size,
            "q quits",
        ]
        first_row = max(0, (buffer.rows - len(lines)) // 2)
        for index, line in enumerate(lines):
            if first_row + index >= buffer.rows:
                break
            text = truncate(line, buffer.cols, ellipsis="")
            x = max(0, (buffer.cols - display_width(text)) // 2)
            color = 205 if index == 0 else 244
            buffer.put_text(first_row + index, x, text, color, max_width=buffer.cols - x)

    def _draw_editor(self, buffer: CellBuffer):
        editor = self.editor
        if editor is None:
            return None
        width = min(buffer.cols - 2, 64)
        width = max(6, width)
        height = 5
        x = max(0, (buffer.cols - width) // 2)
        y = max(0, min(buffer.rows - height - 1, buffer.rows - 7))
        draw_box(buffer, x, y, width, height, "Edit message")
        inner = max(1, width - 6)
        visible, cursor = editor.layout(inner)
        buffer.put_text(y + 2, x + 2, "> ", 205, max_width=width - 4)
        buffer.put_text(y + 2, x + 4, visible, 231, max_width=inner)
        hint = ("Enter save / Esc cancel / arrows move" if self.ascii_mode
                else "Enter save \u00b7 Esc cancel \u00b7 arrows move")
        buffer.put_text(y + 3, x + 2, truncate(hint, width - 4), 244, max_width=width - 4)
        return y + 2, x + 4 + cursor

    def _draw_status(self, buffer: CellBuffer, row: int, width: int) -> None:
        heart = "*" if self.ascii_mode else "\u2665"
        left = "%s Bouquet" % heart
        right = self._status_right()
        if self._rebuilding_detail:
            right = "Rebuilding detail... | " + right
        elif time.monotonic() < self.toast_until and self.toast_text:
            right = self.toast_text + " | " + right
        draw_status(buffer, row, width, left, right, self.ascii_mode, 244)

    def _status_right(self) -> str:
        settings = self.settings
        eff_d = self.active_detail()
        detail_label = "Auto\u2192%dx" % eff_d if settings.detail == "auto" else "%dx" % eff_d
        total = settings.total_flowers()
        dense_tag = " dense" if total > self.recommended_count() else ""
        preset_str = ("Custom (seed %d)" % settings.seed) if settings.preset == "Custom" else settings.preset
        theme_label = get_theme(settings.theme).label

        if self.actual_size[0] >= 110:
            heart = "*" if self.ascii_mode else "\u2665"
            deg = " deg" if self.ascii_mode else "\u00b0"
            tilt_deg = int(round(math.degrees(settings.tilt)))
            state = "Paused \u00b7 " if settings.paused else ""
            hint = footer_hint(self.ascii_mode) if self.actual_size[0] >= 140 else "? help Tab panel v detail q quit"
            parts = [
                "%sSpin %.1f" % (state, settings.spin),
                "Tilt %d%s" % (tilt_deg, deg),
                "Cam %.1f" % settings.camera,
                "%s %d" % (heart, settings.hearts),
                "%d flowers%s" % (total, dense_tag),
                "Detail %s" % detail_label,
                "Theme %s" % theme_label,
            ]
            if preset_str.lower() != theme_label.lower():
                parts.append(preset_str)
            parts.extend(["%.1f/%d fps" % (self.fps_actual, settings.fps), hint])
            joined = " \u00b7 ".join(parts)
            if display_width(joined) > self.cols - 12:
                parts[-1] = "? Tab v q"
                joined = " \u00b7 ".join(parts)
            return joined

        state = "hold" if settings.paused else "play"
        spin = ("%.1f" % settings.spin).replace("-0.", "-.").replace("0.", ".")
        tilt = ("%.2f" % settings.tilt).replace("0.", ".")
        parts = [
            "%.1f/%d" % (self.fps_actual, settings.fps),
            state,
            "s" + spin,
            "t" + tilt,
            "c%g" % settings.camera,
            "h%d" % settings.hearts,
            "f%d%s" % (total, dense_tag),
            detail_label,
            theme_label,
            preset_str,
            footer_hint(self.ascii_mode),
        ]
        return " ".join(parts)

    def _record_frame(self) -> None:
        now = time.monotonic()
        self.frame_stamps.append(now)
        while self.frame_stamps and now - self.frame_stamps[0] > 1.0:
            self.frame_stamps.popleft()
        if len(self.frame_stamps) >= 2:
            span = self.frame_stamps[-1] - self.frame_stamps[0]
            if span > 0:
                self.fps_actual = (len(self.frame_stamps) - 1) / span

    def _shutdown(self) -> None:
        self.terminal.restore()
        self.terminal.restore_signal_handlers()
        if self.config_enabled:
            self.settings.repair()
            error = save_settings(self.settings, self.config_path)
            if error:
                print("bouquet: %s" % error, file=sys.stderr)
