"""Core acceptance checks for Bouquet TUI."""

from __future__ import annotations

import itertools
import tempfile
import unittest
from pathlib import Path

from bouquet.config.settings import PRESETS, Settings, apply_preset
from bouquet.config.storage import load_settings, save_settings
from bouquet.flowers import all_varieties
from bouquet.flowers.registry import LOD_FULL, LOD_SIMPLIFIED
from bouquet.geometry.camera import Camera, Projector, Viewport
from bouquet.platform.keys import KeyParser
from bouquet.render.buffer import CellBuffer
from bouquet.render.gallery import gallery_lines
from bouquet.render.flowers import draw_flower_heads
from bouquet.render.snapshot import render_snapshot
from bouquet.scene.composition import flower_sequence
from bouquet.scene.hearts import Hearts
from bouquet.scene.scene import build_scene
from bouquet.text import display_width, truncate
from bouquet.tui.app import App
from bouquet.tui.editor import MessageEditor
from bouquet.tui.keymap import KEYMAP
from bouquet.tui.panel import Panel


def _mask(spec, width, height):
    mask = []
    for row in range(height):
        line = []
        for col in range(width):
            x = ((col + 0.5 - width / 2.0) / (width / 2.0)) / spec.aspect
            y = (row + 0.5 - height / 2.0) / (height / 2.0)
            line.append(spec.shape(x, y, 0.4, LOD_FULL, spec.colorways[0]) is not None)
        mask.append(line)
    return mask


def _iou(first, second):
    intersection = union = 0
    for row_a, row_b in zip(first, second):
        for a, b in zip(row_a, row_b):
            intersection += bool(a and b)
            union += bool(a or b)
    return intersection / union if union else 1.0


def _median_visible_fraction(settings):
    scene = build_scene(settings)
    width, height = 79, 21
    fractions = []
    for turn in range(24):
        yaw = turn * 2.0 * 3.141592653589793 / 24.0
        t = yaw / settings.spin if settings.spin else 0.0
        projector = Projector(Camera(settings.camera, settings.tilt),
                              Viewport(width, height), yaw)
        individual = []
        for flower in scene.flowers:
            buffer = CellBuffer(width, height)
            draw_flower_heads(buffer, projector, (flower,), t, yaw, scene.head_scale,
                              settings, (0, 0, width, height))
            individual.append({
                (row, col): buffer.zbuf[row][col]
                for row in range(height) for col in range(width)
                if buffer.zbuf[row][col] > -1e8
            })
        combined = CellBuffer(width, height)
        draw_flower_heads(combined, projector, scene.flowers, t, yaw, scene.head_scale,
                          settings, (0, 0, width, height))
        for cells in individual:
            if cells:
                visible = sum(abs(combined.zbuf[row][col] - z) < 1e-8
                              for (row, col), z in cells.items())
                fractions.append(visible / len(cells))
    fractions.sort()
    return fractions[len(fractions) // 2]


class SettingsTests(unittest.TestCase):
    def test_defaults_round_trip_and_repair(self):
        settings = Settings()
        self.assertEqual((settings.fps, settings.spin, settings.tilt, settings.camera),
                         (24, 0.6, 0.30, 4.0))
        self.assertEqual(settings.total_flowers(), 10)
        for name in ("Classic", "Spring Garden", "Romantic Reds", "Sunny Field",
                     "Wildflower Mix", "Minimal"):
            self.assertIn(name, PRESETS)
        minimal = apply_preset(settings, "Minimal")
        self.assertEqual(minimal.total_flowers(), 2)
        self.assertFalse(minimal.ribbon or minimal.babies or minimal.sparkles)
        restored, warnings = Settings.from_dict(settings.to_dict())
        self.assertEqual(restored.to_dict(), settings.to_dict())
        self.assertFalse(warnings)
        broken, warnings = Settings.from_dict({"version": 1, "settings": {
            "fps": 1000, "spin": "-99", "camera": 0, "daisy_count": 999,
        }})
        self.assertEqual((broken.fps, broken.spin, broken.camera), (60, -3.0, 2.0))
        self.assertEqual(broken.total_flowers(), 24)
        self.assertTrue(warnings)

    def test_storage_missing_corrupt_and_atomic_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings, warnings = load_settings(path)
            self.assertEqual(settings.total_flowers(), 10)
            self.assertFalse(warnings)
            self.assertIsNone(save_settings(settings, path))
            loaded, warnings = load_settings(path)
            self.assertEqual(loaded.to_dict(), settings.to_dict())
            self.assertFalse(warnings)
            path.write_text("{broken", encoding="utf-8")
            loaded, warnings = load_settings(path)
            self.assertEqual(loaded.total_flowers(), 10)
            self.assertTrue(warnings)


class CompositionAndFlowerTests(unittest.TestCase):
    def test_classic_sequence_and_seeded_scene(self):
        settings = Settings()
        sequence = flower_sequence(settings)
        self.assertEqual(len(sequence), 10)
        self.assertEqual([i for i, name in enumerate(sequence) if name == "tulip"], [3, 8])
        self.assertEqual(build_scene(settings), build_scene(Settings()))
        settings.set_count("rose", 1)
        settings.set_count("daisy", 0)
        settings.set_count("tulip", 0)
        settings.repair()
        self.assertEqual(build_scene(settings).sequence, ("rose",))

    def test_static_scene_geometry_reused_for_count_changes(self):
        original = Settings()
        static = build_scene(original)
        changed = Settings(counts={"rose": 1, "tulip": 2, "daisy": 7})
        rebuilt = build_scene(changed, static_scene=static)
        self.assertEqual(rebuilt.points[rebuilt.total * 70:],
                         static.points[static.total * 70:])
        self.assertIs(rebuilt.babies, static.babies)
        self.assertIs(rebuilt.sparkles, static.sparkles)

    def test_24_flower_visibility_stays_readable(self):
        settings = Settings()
        settings.counts = {variety_id: 0 for variety_id in settings.counts}
        settings.set_count("daisy", 24)
        settings.repair()
        self.assertGreaterEqual(_median_visible_fraction(settings), 0.60)

    def test_panel_rejects_empty_and_over_cap_counts(self):
        settings = Settings(counts={"daisy": 1})
        panel = Panel()
        panel.selected[panel.tab] = 2
        self.assertEqual(panel.adjust(settings, -1), "empty")
        self.assertEqual(settings.total_flowers(), 1)

        settings = Settings(counts={"daisy": 23, "tulip": 1})
        self.assertEqual(panel.adjust(settings, 1), "total")
        self.assertEqual(settings.total_flowers(), 24)

    def test_panel_keys_move_rows_switch_tabs_and_change_values(self):
        app = App(Settings(), config_enabled=False)
        app.handle_key("tab")
        self.assertIsNotNone(app.panel)
        app.handle_key("down")
        self.assertEqual(app.panel.selected[app.panel.tab], 1)
        app.handle_key("up")
        self.assertEqual(app.panel.selected[app.panel.tab], 0)
        app.handle_key("2")
        self.assertEqual(app.panel.tab, "Look")
        before = app.settings.theme
        app.handle_key("right")
        self.assertNotEqual(app.settings.theme, before)
        app.handle_key("tab")
        self.assertIsNone(app.panel)

    def test_all_varieties_render_in_lod_and_have_distinct_masks(self):
        varieties = list(all_varieties())
        self.assertEqual(len(varieties), 10)
        for spec in varieties:
            for lod in (LOD_FULL, LOD_SIMPLIFIED):
                samples = [spec.shape(x / 8.0, y / 8.0, 0.4, lod, spec.colorways[0])
                           for x in range(-8, 9) for y in range(-8, 9)]
                self.assertTrue(any(sample is not None for sample in samples), spec.id)
                self.assertEqual(samples, [spec.shape(x / 8.0, y / 8.0, 0.4, lod,
                                                      spec.colorways[0])
                                           for x in range(-8, 9) for y in range(-8, 9)])
        # Tiny cell grids quantize different outlines into similar masks.
        for width, height in ((9, 5), (11, 6), (13, 7)):
            masks = [_mask(spec, width, height) for spec in varieties]
            overlap = max(_iou(a, b) for a, b in itertools.combinations(masks, 2))
            self.assertLess(overlap, 0.80, (width, height, overlap))


class GeometryAndTextTests(unittest.TestCase):
    def test_projection_guard_and_wide_character_buffer(self):
        projector = Projector(Camera(0.1, 0.3), Viewport(80, 24), 0.0)
        self.assertGreaterEqual(projector.distance, 2.0)
        self.assertIsNone(projector.project_float(0.0, 100.0, 0.0))
        buffer = CellBuffer(5, 2)
        buffer.put_text(0, 0, "A你e\u0301", None)
        self.assertEqual(display_width(buffer.line(0)), 4)
        self.assertEqual(buffer.chars[0][1], "你")
        self.assertEqual(buffer.chars[0][2], "")

    def test_message_width_truncation_and_editor(self):
        self.assertEqual(display_width("你e\u0301"), 3)
        self.assertLessEqual(display_width(truncate("你abcdef", 4)), 4)
        editor = MessageEditor("for you")
        editor.handle("home")
        editor.handle("你")
        editor.handle("delete")
        self.assertEqual(editor.result(), "你or you")
        self.assertEqual(editor.handle("enter"), "commit")
        self.assertEqual(MessageEditor("").result(), "")

    def test_snapshot_dimensions(self):
        frame = render_snapshot(Settings(), 60, 20, at=1.0)
        lines = frame.splitlines()
        self.assertEqual(len(lines), 20)
        self.assertTrue(all(display_width(line) <= 60 for line in lines))

    def test_gallery_covers_all_varieties_and_sizes(self):
        lines = gallery_lines(Settings(), ascii_mode=True)
        output = "\n".join(lines)
        for size in ("Small", "Medium", "Large"):
            self.assertIn(size + " heads", output)
        for spec in all_varieties():
            self.assertIn(spec.name, output)
        self.assertTrue(all(display_width(line) <= 100 for line in lines))

    def test_classic_golden_frame(self):
        golden = Path(__file__).parent / "golden" / "classic-80x24.txt"
        self.assertEqual(render_snapshot(Settings(), 80, 24),
                         golden.read_text(encoding="utf-8"))


class EffectsAndInputTests(unittest.TestCase):
    def test_heart_reduction_retires_only_surplus(self):
        hearts = Hearts(18, 21)
        hearts.items[0].y = 0.5
        hearts.set_target(17)
        self.assertEqual(hearts.active, 17)
        self.assertTrue(hearts.items[0].retiring)
        self.assertGreater(hearts.items[0].y, 0.0)
        hearts.set_target(22)
        self.assertEqual(hearts.active, 22)

    def test_key_parser_partial_sequences_and_utf8(self):
        parser = KeyParser()
        self.assertEqual(parser.feed(b"\x1b["), [])
        self.assertEqual(parser.feed(b"A"), ["up"])
        self.assertEqual(parser.feed("你".encode("utf-8")), ["你"])
        self.assertEqual(parser.feed(b"\x1b"), [])
        self.assertEqual(parser.flush(), ["esc"])
        parser = KeyParser()
        parser.feed(b"\x1b[")
        self.assertEqual(parser.flush(), ["unknown"])

    def test_keymap_bindings_have_parser_events(self):
        events = {
            b"\x03": "ctrl-c", b"\x1b[A": "up", b"\x1b[B": "down",
            b"\x1b[C": "right", b"\x1b[D": "left", b"\x1b[1;2A": "shift-up",
            b"\x1b[1;2D": "shift-left", b"\x1b[5~": "pgup",
            b"\x1b[6~": "pgdn", b"\x1b[5;2~": "shift-pgup",
            b"\x1b[6;2~": "shift-pgdn", b"\x1b[H": "home",
            b"\x1b[F": "end", b"\x1b[3~": "delete", b"\x1b[Z": "shift-tab",
            b"\x7f": "backspace", b"\r": "enter", b" ": "space",
        }
        for raw, expected in events.items():
            with self.subTest(key=expected):
                self.assertEqual(KeyParser().feed(raw), [expected])
        known = {key for binding in KEYMAP for key in binding.keys}
        self.assertIn("ctrl-c", known)
        self.assertIn("shift-pgup", known)
        self.assertIn("backspace", known)

    def test_heart_motion_is_bounded_and_frame_rate_independent(self):
        fast = Hearts(8, 44)
        slow = Hearts(8, 44)
        for i in range(24):
            fast.update(1 / 24.0, (i + 1) / 24.0)
        for i in range(60):
            slow.update(1 / 60.0, (i + 1) / 60.0)
        self.assertEqual(len(fast.items), 8)
        self.assertEqual(len(slow.items), 8)
        self.assertLess(max(abs(a.y - b.y) for a, b in zip(fast.items, slow.items)), 0.01)

    def test_spin_change_integrates_without_clock_jump(self):
        app = App(Settings(), config_enabled=False)
        app._update(0.1)
        before_yaw = app.yaw
        before_time = app.t
        app.settings.spin = 1.0
        app._update(0.1)
        self.assertLess(abs(app.yaw - before_yaw), 0.1)
        self.assertAlmostEqual(app.t, before_time + 0.1)
        app.settings.paused = True
        before_time = app.t
        app._update(0.1)
        self.assertEqual(app.t, before_time)


if __name__ == "__main__":
    unittest.main()
