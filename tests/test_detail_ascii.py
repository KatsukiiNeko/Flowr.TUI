"""ASCII detail pipeline: shape masks, dominant colour, honesty and boundaries."""

from __future__ import annotations

import argparse
import io
import unittest
from contextlib import redirect_stdout

from bouquet.cli import build_parser, main as cli_main, parse_size
from bouquet.config.settings import Settings
from bouquet.flowers import all_varieties
from bouquet.render.buffer import CellBuffer
from bouquet.render.flowers import rasterise_flower_heads
from bouquet.render.gallery import _GalleryProjector
from bouquet.render.resolvers import (
    GLYPH_MASKS,
    TOKEN_GLYPHS,
    effective_resolution,
    resolve,
    samples_per_cell,
    _resolve_ascii_masked_numpy,
    _resolve_ascii_masked_python,
)
from bouquet.render.samples import (
    FLAG_RIM,
    HAS_NUMPY,
    SampleBuffer,
)
from bouquet.render.snapshot import render_snapshot
from bouquet.scene.scene import FlowerHead
from tools.detail_metrics import compare, measure


class GlyphMaskTests(unittest.TestCase):
    def test_mask_table_is_compact_and_inside_the_grid(self):
        self.assertGreaterEqual(len(GLYPH_MASKS), 30)
        self.assertLessEqual(len(GLYPH_MASKS), 60)
        for char, mask in GLYPH_MASKS.items():
            self.assertEqual(len(char), 1)
            self.assertGreaterEqual(mask, 0)
            self.assertLess(mask, 1 << 32)
            self.assertTrue(char.isascii() or char == " ")

    def test_candidates_are_class_restricted(self):
        for token, glyphs in TOKEN_GLYPHS.items():
            self.assertTrue(glyphs, token)
            for char in glyphs:
                self.assertIn(char, GLYPH_MASKS, token)
        for token in ("petal", "soft", "cup", "star", "dense", "poppy", "sepal"):
            self.assertFalse(set("#@%") & set(TOKEN_GLYPHS[token]), token)
        self.assertIn("@", TOKEN_GLYPHS["center"])


class DetailMeasurementTests(unittest.TestCase):
    def test_levels_get_richer_without_losing_area(self):
        for width, height in ((120, 40), (200, 60)):
            reports = compare([
                measure(detail, width, height, runs=2)
                for detail in (32, 64, 128, 256)
            ])
            self.assertGreater(reports[1]["glyphs"], reports[0]["glyphs"])
            self.assertGreaterEqual(reports[2]["glyphs"], reports[1]["glyphs"])
            self.assertGreaterEqual(reports[3]["glyphs"], reports[2]["glyphs"])
            for earlier, later in zip(reports, reports[1:]):
                self.assertGreater(later["pairs"], earlier["pairs"], (width, height))
                self.assertGreater(later["changed_pct"], 5.0, (width, height))
                covered = max(1, min(earlier["cells"], later["cells"]))
                self.assertLessEqual(abs(earlier["cells"] - later["cells"]) / covered, 0.15)
            residuals = [report["mask_residual_per_cell"] for report in reports[1:]]
            self.assertGreaterEqual(residuals[0], residuals[1] - 0.05)
            self.assertGreaterEqual(residuals[1], residuals[2] - 0.05)
            self.assertGreater(reports[3]["partial_cells"], reports[1]["partial_cells"])

    def test_fallback_at_32_does_not_use_masks(self):
        report = measure(32, 120, 40, runs=1)
        self.assertEqual(report["partial_cells"], 0)
        self.assertEqual(report["mask_residual"], 0.0)

    def test_effective_resolution_is_honest(self):
        self.assertEqual(effective_resolution(256, 24, "ascii"), 20)
        self.assertEqual(effective_resolution(256, 40, "ascii"), 36)
        self.assertEqual(effective_resolution(256, 40, "half"), 72)
        self.assertEqual(effective_resolution(256, 60, "braille"), 224)
        self.assertEqual(effective_resolution(256, 40, "sextant"), 108)


class ClassParityAndDensityTests(unittest.TestCase):
    def _pattern_buffer(self):
        sb = SampleBuffer(36, 64)
        pid = sb.register_palette((196, 203, 210))
        from bouquet.render.samples import GC_PETAL, GC_STEM

        for y in range(64):
            for x in range(36):
                dx = (x - 17) / 15.0
                dy = (y - 30) / 26.0
                if dx * dx + dy * dy <= 1.0:
                    bright = max(0.05, min(0.99, 0.9 - 0.5 * (dx * dx + dy * dy)))
                    gc = GC_STEM if abs(dx) < 0.12 else GC_PETAL
                    flags = FLAG_RIM if abs(dx * dx + dy * dy - 1.0) < 0.08 else 0
                    sb.plot(x, y, 1.0 - y * 0.01, bright, pid, gc, 0, 1, flags)
        return sb

    def test_pure_python_and_numpy_masked_paths_match(self):
        if not HAS_NUMPY:
            self.skipTest("NumPy is not installed")
        sb = self._pattern_buffer()
        numpy_buf = CellBuffer(24, 20)
        python_buf = CellBuffer(24, 20)
        clip = (0, 0, 24, 20)
        _resolve_ascii_masked_numpy(sb, numpy_buf, clip, False, True, False, None, None)
        _resolve_ascii_masked_python(sb, python_buf, clip, False, True, False, None, None)
        self.assertEqual(numpy_buf.chars, python_buf.chars)
        self.assertEqual(numpy_buf.colors, python_buf.colors)

    def test_dense_glyphs_stay_below_a_quarter_of_a_head(self):
        for spec in all_varieties():
            for detail in (64, 128):
                sb = SampleBuffer(24, detail)
                head = FlowerHead(
                    (0.0, 0.34, 0.0), (0.0, 1.0, 0.0), spec, spec.colorways[0], 0.45, 0.4,
                )
                projector = _GalleryProjector(24, detail)
                rasterise_flower_heads(
                    sb, projector, (head,), 0.0, 0.0, 1.0, Settings(),
                    detail=detail, phase_scale=0.0,
                )
                buffer = CellBuffer(13, 7)
                resolve(sb, buffer, (0, 0, 13, 7), style="ascii")
                chars = [
                    buffer.chars[row][col]
                    for row in range(7) for col in range(13)
                    if buffer.chars[row][col] != " "
                ]
                dense = sum(1 for char in chars if char in "#@%")
                self.assertLessEqual(dense / max(1, len(chars)), 0.25, (spec.id, detail))


class SextantAndSizeTests(unittest.TestCase):
    def test_sextant_style_is_valid_unicode_and_dense(self):
        self.assertEqual(samples_per_cell("sextant"), (2, 3))
        plain = render_snapshot(
            Settings(detail="64", style="sextant", hearts=0, sparkles=False,
                     babies=False, petal_fall=0, color_mode="256", message=""),
            80, 24,
        )
        chars = {char for char in plain if char not in " \n"}
        self.assertTrue(chars)
        for char in chars:
            code = ord(char)
            self.assertGreaterEqual(code, 0x1FB00)
            self.assertLessEqual(code, 0x1FB3B)

    def test_size_parser_rejects_bad_or_tiny_values(self):
        self.assertEqual(parse_size("120x40"), (120, 40))
        for value in ("120", "120x", "abc", "10x40", "120x5", "120x40x1"):
            with self.assertRaises(argparse.ArgumentTypeError):
                parse_size(value)
        args = build_parser().parse_args(["--size", "60x20", "--snapshot", "-"])
        self.assertEqual(args.size, (60, 20))

    def test_size_controls_snapshot_and_gallery_width(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli_main(["--no-config", "--size", "60x20", "--snapshot", "-"])
        self.assertEqual(code, 0)
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 20)
        self.assertTrue(all(len(line) <= 60 for line in lines))
        gallery = io.StringIO()
        with redirect_stdout(gallery):
            code = cli_main(["--no-config", "--size", "60x20", "--gallery", "--ascii"])
        self.assertEqual(code, 0)
        gallery_lines_out = gallery.getvalue().splitlines()
        self.assertTrue(gallery_lines_out)
        self.assertTrue(all(len(line) <= 60 for line in gallery_lines_out))


if __name__ == "__main__":
    unittest.main()
