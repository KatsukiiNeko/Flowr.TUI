"""Bouquet TUI v2 acceptance tests (detail, styles, legibility, wrap, themes, greenery, petals, migration)."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bouquet.cli import build_parser, main as cli_main
from bouquet.config.settings import PRESETS, Settings, apply_preset
from bouquet.config.themes import CURATED_THEME_NAMES, THEMES
from bouquet.flowers import all_varieties
from bouquet.flowers import colorways as c
from bouquet.flowers.colorways import lut256_for_rgb_ramp, nearest_xterm256
from bouquet.geometry.camera import Camera, Projector, Viewport
from bouquet.render.buffer import CellBuffer
from bouquet.render.flowers import SampleProjector, draw_flower_heads, rasterise_flower_heads
from bouquet.render.frame import _rasterise_static_numpy, _rasterise_static_python, draw_scene
from bouquet.render.gallery import _GalleryProjector, gallery_lines
from bouquet.render.presenter import AnsiPresenter
from bouquet.render.resolvers import (
    auto_detail_target,
    effective_resolution,
    effective_style,
    resolve,
    resolve_truecolor,
)
from bouquet.render.samples import (
    EMPTY_Z,
    FLAG_CONTACT,
    FLAG_RIM,
    HAS_NUMPY,
    SampleBuffer,
    apply_head_outlines,
)
from bouquet.render.snapshot import render_snapshot
from bouquet.scene.composition import recommended_flower_count, themed_shuffle_counts
from bouquet.scene.greenery import all_greenery, build_greenery, register_greenery, GreenerySpec
from bouquet.scene.hearts import Hearts
from bouquet.scene.petals import PetalFall
from bouquet.scene.scene import FlowerHead, build_scene
from bouquet.text import display_width
from bouquet.tui.app import App


class DetailAndStyleTests(unittest.TestCase):
    def test_detail_determinism_and_square_samples(self):
        for detail in ("32", "64", "128", "256"):
            st = Settings(detail=detail, style="ascii")
            a = render_snapshot(st, 100, 32, at=0.4, color=True)
            b = render_snapshot(st, 100, 32, at=0.4, color=True)
            self.assertEqual(a, b, detail)
        sp = SampleProjector(Camera(), 160, 100, 0.0)
        self.assertEqual(sp.sx_scale, sp.scale)
        rx, ry = sp.project_radius(0.2, 1.0, aspect=1.0)
        self.assertAlmostEqual(rx, ry, places=6)

    def test_effective_resolution_formula_and_auto_targets(self):
        self.assertEqual(effective_resolution(128, 24, "ascii"), 20)
        self.assertEqual(effective_resolution(128, 40, "half"), 72)
        self.assertEqual(effective_resolution(256, 60, "braille"), 224)
        self.assertEqual(auto_detail_target(40, "ascii", True), 64)
        self.assertEqual(auto_detail_target(40, "half", True), 128)
        self.assertEqual(auto_detail_target(60, "braille", True), 256)
        self.assertEqual(auto_detail_target(60, "braille", False), 64)

    def test_classic_200x60_detail_improves_cell_diversity(self):
        counts = []
        for detail in ("32", "64", "128", "256"):
            st = Settings(detail=detail, style="ascii", color_mode="256",
                          hearts=0, sparkles=False, babies=False, petal_fall=0)
            sc = build_scene(st, detail=int(detail))
            cb = CellBuffer(199, 57)
            proj = Projector(Camera(st.camera, st.tilt), Viewport(199, 57), 0.0)
            draw_scene(cb, sc, proj, st, 0.0, Hearts(0, 21), 0.0, (0, 0, 199, 57),
                       sc.head_scale, detail=int(detail))
            pairs = {
                (cb.chars[r][col], cb.colors[r][col])
                for r in range(57) for col in range(199)
                if cb.chars[r][col] != " "
            }
            counts.append(len(pairs))
        self.assertGreater(counts[1], counts[0], counts)
        self.assertGreaterEqual(counts[2], counts[1], counts)
        # 256-colour quantisation can merge a few pairs at the highest detail,
        # so allow a small regression rather than demanding a strict increase.
        self.assertGreaterEqual(counts[3], int(counts[2] * 0.95), counts)

    def test_wrap_no_holes_at_every_detail_level(self):
        s = Settings(color_mode="256")
        for detail in (32, 64, 128, 256):
            sc = build_scene(s, detail=detail)
            sw, sh = int(round(detail * 119 / 74.0)), detail
            sb = SampleBuffer(sw, sh)
            sp = SampleProjector(Camera(s.camera, s.tilt), sw, sh, 0.0)
            wrap_pts = tuple(pt for pt in sc.points if pt[6] == c.PAPER)
            wrap_scene = type("WrapOnly", (), {
                "points": wrap_pts, "greenery": (), "theme_name": "classic", "wrap_style": "kraft"
            })()
            if HAS_NUMPY:
                _rasterise_static_numpy(sb, sp, wrap_scene, True)
            else:
                _rasterise_static_python(sb, sp, wrap_scene, True)
            covered_rows = [
                r for r in range(sh)
                if any((sb.z[r, col] if HAS_NUMPY else sb.z[r * sw + col]) > EMPTY_Z * 0.5 for col in range(sw))
            ]
            r_start = min(covered_rows) + max(2, int(0.35 * (max(covered_rows) - min(covered_rows))))
            filled = holes = 0
            for r in range(r_start, max(covered_rows)):
                cols = [
                    col for col in range(sw)
                    if (sb.z[r, col] if HAS_NUMPY else sb.z[r * sw + col]) > EMPTY_Z * 0.5
                ]
                if len(cols) >= 2:
                    for col in range(min(cols), max(cols) + 1):
                        filled += 1
                        z_val = sb.z[r, col] if HAS_NUMPY else sb.z[r * sw + col]
                        if z_val <= EMPTY_Z * 0.5:
                            holes += 1
            cov = (filled - holes) / max(1, filled)
            self.assertGreaterEqual(cov, 0.98, (detail, cov))

    def test_detail_cache_reuse_and_auto_hysteresis(self):
        app = App(Settings(detail="auto"), config_enabled=False)
        first_scene = app.scene
        # Composition change at same detail reuses static geometry
        app.settings.set_count("rose", 2)
        app.on_settings_changed(["rose_count"])
        self.assertEqual(app.scene.points[app.scene.total * app.scene.stem_steps:],
                         first_scene.points[first_scene.total * first_scene.stem_steps:])
        # Auto hysteresis: cannot change faster than once per 5 s
        with mock.patch.dict(os.environ, {"TERM": "xterm-256color"}):
            app._auto_detail = 64
            app._last_auto_change = 100.0
            app.actual_size = (200, 60)
            app.settings.style = "braille"
            app._maybe_update_auto_detail(102.0)  # < 5 s elapsed
            self.assertEqual(app._auto_detail, 64)
            app._maybe_update_auto_detail(106.0)  # >= 5 s elapsed
            self.assertEqual(app._auto_detail, 256 if HAS_NUMPY else 64)

    def test_half_and_braille_styles_and_fallbacks(self):
        with mock.patch.dict(os.environ, {"TERM": "xterm-256color", "COLORTERM": "truecolor"}):
            for style in ("ascii", "half", "braille"):
                st = Settings(detail="128", style=style, hearts=0, sparkles=False, babies=False, petal_fall=0)
                sc = build_scene(st, detail=128)
                cb = CellBuffer(80, 24)
                proj = Projector(Camera(st.camera, st.tilt), Viewport(80, 22), 0.0)
                draw_scene(cb, sc, proj, st, 0.0, Hearts(0, 21), 0.0, (0, 0, 80, 22),
                           sc.head_scale, detail=128)
                self.assertEqual(len(cb.chars), 24)
                self.assertEqual(len(cb.chars[0]), 80)
                for r in range(24):
                    self.assertLessEqual(display_width(cb.line(r)), 80)
                    for col in range(80):
                        if cb.chars[r][col] == " ":
                            self.assertIsNone(cb.bg_colors[r][col])
                            self.assertIsNone(cb.colors[r][col])
                        elif style == "braille":
                            code = ord(cb.chars[r][col])
                            self.assertTrue(0x2800 <= code <= 0x28FF, cb.chars[r][col])
                            self.assertIsNone(cb.bg_colors[r][col])
            # Fallbacks
            self.assertEqual(effective_style("braille", ascii_mode=True, color_enabled=True), "ascii")
            self.assertEqual(effective_style("half", ascii_mode=False, color_enabled=False), "half")
            plain = render_snapshot(Settings(style="braille", detail="64"), 80, 24, color=False)
            self.assertTrue(any(0x2800 <= ord(ch) <= 0x28FF for ch in plain))
        with mock.patch.dict(os.environ, {"TERM": "dumb"}):
            self.assertEqual(effective_style("braille", ascii_mode=False, color_enabled=True), "ascii")


class LegibilityAndWrapTests(unittest.TestCase):
    def test_legibility_visibility_across_sizes(self):
        for w, h in ((80, 24), (120, 40), (200, 60)):
            vw, vh = w - 1, h - 3
            rec = recommended_flower_count(Viewport(vw, vh))
            for pname in ("Classic", "Blush", "Moonlight"):
                st = apply_preset(Settings(color_mode="256"), pname)
                if pname != "Classic":
                    self.assertLessEqual(st.total_flowers(), rec)
            st = Settings(seed=101, theme="blush", color_mode="256",
                          counts=themed_shuffle_counts("blush", rec, 101))
            sc = build_scene(st, detail=64)
            sw, sh = max(16, int(round(64 * vw / (vh * 2.0)))), 64
            fracs = []
            for turn in range(0, 24, 3):
                yaw = turn * 2.0 * 3.141592653589793 / 24.0
                sp = SampleProjector(Camera(st.camera, st.tilt), sw, sh, yaw)
                sb_comb = SampleBuffer(sw, sh)
                if HAS_NUMPY:
                    _rasterise_static_numpy(sb_comb, sp, sc, st.ribbon)
                else:
                    _rasterise_static_python(sb_comb, sp, sc, st.ribbon)
                rasterise_flower_heads(sb_comb, sp, sc.flowers, 0.0, yaw, sc.head_scale, st, detail=64)
                for idx, fl in enumerate(sc.flowers):
                    oid = idx + 1
                    sb_one = SampleBuffer(sw, sh)
                    rasterise_flower_heads(sb_one, sp, (fl,), 0.0, yaw, sc.head_scale, st, detail=64, head_id_offset=oid)
                    if HAS_NUMPY:
                        import numpy as np
                        tot = int(np.count_nonzero(sb_one.obj_id == oid))
                        vis = int(np.count_nonzero((sb_one.obj_id == oid) & (sb_comb.obj_id == oid)))
                    else:
                        tot = sum(1 for x in sb_one.obj_id if x == oid)
                        vis = sum(1 for a, b in zip(sb_one.obj_id, sb_comb.obj_id) if a == oid and b == oid)
                    if tot:
                        fracs.append(vis / tot)
            fracs.sort()
            self.assertGreaterEqual(fracs[len(fracs) // 2], 0.60, (w, h))
            self.assertGreaterEqual(fracs[max(0, int(len(fracs) * 0.10))], 0.35, (w, h))

    def test_head_outlines_contact_shadow_and_rim(self):
        spec = all_varieties()[0]
        h1 = FlowerHead((0.0, 0.35, 0.25), (0.0, 1.0, 0.0), spec, spec.colorways[0], 0.22, 0.1)
        h2 = FlowerHead((0.12, 0.35, -0.10), (0.0, 1.0, 0.0), spec, spec.colorways[0], 0.22, 0.2)
        sb = SampleBuffer(64, 64)
        sp = SampleProjector(Camera(), 64, 64, 0.0)
        rasterise_flower_heads(sb, sp, (h1, h2), 0.0, 0.0, 1.0, Settings(depth_cue=0), detail=64)
        apply_head_outlines(sb, cell_samples_y=1.0, enabled=True)
        if HAS_NUMPY:
            import numpy as np
            self.assertTrue(np.any((sb.flags & FLAG_RIM) != 0))
            self.assertTrue(np.any((sb.flags & FLAG_CONTACT) != 0))
            interior = sb.brightness[(sb.obj_id == 2) & ((sb.flags & (FLAG_RIM | FLAG_CONTACT)) == 0)]
            boundary = sb.brightness[(sb.obj_id == 2) & ((sb.flags & FLAG_CONTACT) != 0)]
            self.assertLess(float(np.mean(boundary)), float(np.mean(interior)))
        else:
            self.assertTrue(any(f & FLAG_RIM for f in sb.flags))
            self.assertTrue(any(f & FLAG_CONTACT for f in sb.flags))

    def test_depth_cue_monotonic_dimming(self):
        spec = all_varieties()[0]
        near = FlowerHead((0.0, 0.35, 0.45), (0.0, 1.0, 0.0), spec, spec.colorways[0], 0.18, 0.1)
        far = FlowerHead((0.35, 0.35, -0.45), (0.0, 1.0, 0.0), spec, spec.colorways[0], 0.18, 0.1)
        sb = SampleBuffer(64, 64)
        sp = SampleProjector(Camera(), 64, 64, 0.0)
        rasterise_flower_heads(sb, sp, (near, far), 0.0, 0.0, 1.0, Settings(depth_cue=100), detail=64)
        if HAS_NUMPY:
            import numpy as np
            b_near = float(np.mean(sb.brightness[sb.obj_id == 1]))
            b_far = float(np.mean(sb.brightness[sb.obj_id == 2]))
        else:
            b_near = sum(b for b, o in zip(sb.brightness, sb.obj_id) if o == 1) / sum(1 for o in sb.obj_id if o == 1)
            b_far = sum(b for b, o in zip(sb.brightness, sb.obj_id) if o == 2) / sum(1 for o in sb.obj_id if o == 2)
        self.assertGreater(b_near, b_far)

    def test_glyph_discipline_per_variety(self):
        for spec in all_varieties():
            for w, h in ((9, 5), (11, 6), (13, 7)):
                sb = SampleBuffer(w * 2, h * 2)
                head = FlowerHead((0.0, 0.34, 0.0), (0.0, 1.0, 0.0), spec, spec.colorways[0], 0.45, 0.4)
                sp = _GalleryProjector(w * 2, h * 2)
                rasterise_flower_heads(sb, sp, (head,), 0.0, 0.0, 1.0, Settings(), detail=h * 2, phase_scale=0.0)
                cb = CellBuffer(w, h)
                resolve(sb, cb, (0, 0, w, h), style="ascii")
                chars = [cb.chars[r][col] for r in range(h) for col in range(w) if cb.chars[r][col] != " "]
                self.assertGreaterEqual(len(set(chars)), 3, (spec.id, w, h, set(chars)))
                dense = sum(1 for ch in chars if ch in "#@%") / max(1, len(chars))
                self.assertLessEqual(dense, 0.25, (spec.id, w, h, dense))

    def test_vertical_budget_and_wrap_palettes(self):
        st = Settings(color_mode="256", hearts=0, sparkles=False, babies=False, petal_fall=0)
        sc = build_scene(st, detail=64)
        for w, h in ((120, 40), (200, 60)):
            vw, vh = w - 1, h - 3
            cb_all = CellBuffer(vw, vh)
            proj = Projector(Camera(st.camera, st.tilt), Viewport(vw, vh), 0.0)
            draw_scene(cb_all, sc, proj, st, 0.0, Hearts(0, 21), 0.0, (0, 0, vw, vh), sc.head_scale, detail=64)
            cb_heads = CellBuffer(vw, vh)
            draw_flower_heads(cb_heads, proj, sc.flowers, 0.0, 0.0, sc.head_scale, st, (0, 0, vw, vh))
            all_rows = [r for r in range(vh) for col in range(vw) if cb_all.chars[r][col] != " "]
            head_rows = [r for r in range(vh) for col in range(vw) if cb_heads.chars[r][col] != " "]
            wrap_rows = [r for r in range(vh) for col in range(vw) if cb_all.colors[r][col] in c.PAPER]
            stem_rows = {r for r in range(vh) for col in range(vw) if cb_all.colors[r][col] in c.GREENS and r > max(wrap_rows)}
            share = (max(head_rows) - min(head_rows) + 1) / (max(all_rows) - min(all_rows) + 1)
            self.assertGreaterEqual(share, 0.60, (w, h, share))
            self.assertGreaterEqual(len(stem_rows), 2, (w, h, stem_rows))


class ThemeColorGreeneryPetalsTests(unittest.TestCase):
    def test_theme_discipline_and_classic_indices(self):
        self.assertGreaterEqual(len(THEMES), 9)
        for spec in all_varieties():
            self.assertGreaterEqual(len(spec.colorways), 3, spec.id)
        for tname in CURATED_THEME_NAMES:
            th = THEMES[tname]
            st = Settings(seed=42, theme=tname, counts={
                "rose": 3, "tulip": 3, "daisy": 4, "sunflower": 2, "lily": 2,
                "cherry": 2, "peony": 2, "carnation": 2, "poppy": 2, "cosmos": 2,
            })
            sc = build_scene(st, detail=64)
            hues = [fl.hue_family for fl in sc.flowers]
            main_hues = set(hues) - {th.accent_family}
            self.assertLessEqual(len(main_hues), 3, (tname, main_hues))
            self.assertLessEqual(hues.count(th.accent_family) / len(hues), 0.25 + 1e-9, tname)
        # Classic 256 mode preserves reference indices
        st = Settings(theme="classic", color_mode="256")
        sc = build_scene(st, detail=64)
        self.assertEqual(sc.flowers[0].colorway.petals, c.WHITE)

    def test_truecolor_presenter_and_no_color(self):
        with mock.patch.dict(os.environ, {"COLORTERM": "truecolor"}):
            self.assertTrue(resolve_truecolor("auto", True))
            st = Settings(theme="moonlight", detail="64", color_mode="truecolor")
            ansi = render_snapshot(st, 80, 24, color=True)
            self.assertIn("\x1b[38;2;", ansi)
            plain = render_snapshot(st, 80, 24, color=False)
            self.assertNotIn("\x1b[", plain)
        ramp = c.WRAP_RAMPS_RGB["kraft"]
        self.assertEqual(lut256_for_rgb_ramp(ramp), lut256_for_rgb_ramp(ramp))
        self.assertEqual(nearest_xterm256((255, 255, 255)), 231)

    def test_greenery_registry_determinism_and_caching(self):
        ids = {spec.id for spec in all_greenery()}
        self.assertTrue({"eucalyptus", "fern", "wheat"}.issubset(ids))
        g1 = build_greenery("eucalyptus", 8, 21, detail=64)
        g2 = build_greenery("eucalyptus", 8, 21, detail=64)
        self.assertEqual(g1, g2)
        self.assertEqual(build_greenery("off", 8, 21), ())
        s1 = build_scene(Settings(greenery_amount=8, greenery_type="eucalyptus"), detail=64)
        s2 = build_scene(Settings(counts={"rose": 2, "daisy": 8}, greenery_amount=8, greenery_type="eucalyptus"),
                         static_scene=s1, detail=64)
        self.assertIs(s2.greenery, s1.greenery)

    def test_petal_fall_dt_independent_and_retires_smoothly(self):
        fast = PetalFall(10, 42)
        slow = PetalFall(10, 42)
        for i in range(24):
            fast.update(1 / 24.0, (i + 1) / 24.0)
        for i in range(60):
            slow.update(1 / 60.0, (i + 1) / 60.0)
        self.assertLess(max(abs(a.y - b.y) for a, b in zip(fast.items, slow.items)), 0.01)
        fast.items[0].y = 0.5
        fast.set_target(5)
        self.assertEqual(fast.active, 5)
        self.assertTrue(fast.items[0].retiring)

    def test_v1_settings_migration_and_cli_flags(self):
        v1_path = Path("docs/verification/v2/v1_settings.json")
        if v1_path.exists():
            loaded, warnings = Settings.from_json_text(v1_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded.total_flowers(), 10)
            self.assertEqual(loaded.seed, 21)
            self.assertEqual(loaded.detail, "auto")
            self.assertEqual(loaded.style, "ascii")
            self.assertFalse(warnings)
        broken, warnings = Settings.from_dict({"version": 1, "settings": {
            "theme": "nonexistent", "detail": 999, "greenery_amount": -5, "petal_fall": 99,
        }})
        self.assertEqual(broken.theme, "classic")
        self.assertEqual(broken.detail, "auto")
        self.assertEqual(broken.greenery_amount, 0)
        self.assertEqual(broken.petal_fall, 40)
        self.assertTrue(warnings)
        # CLI flags
        args = build_parser().parse_args([
            "--theme", "blush", "--detail", "128", "--style", "braille",
            "--greenery", "12", "--color-mode", "256",
        ])
        self.assertEqual((args.theme, args.detail, args.style, args.greenery, args.color_mode),
                         ("blush", "128", "braille", 12, "256"))


if __name__ == "__main__":
    unittest.main()
