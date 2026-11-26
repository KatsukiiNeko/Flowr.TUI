"""Command-line interface."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from . import __version__
from .config.settings import (
    COLOR_MODES,
    DETAIL_CHOICES,
    PRESETS,
    STYLE_CHOICES,
    THEME_NAMES,
    Settings,
    apply_preset,
)
from .config.storage import default_config_path, load_settings
from .config.themes import get_theme
from .render.gallery import gallery_lines
from .render.snapshot import render_snapshot
from .tui.app import App


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bouquet",
        description="A living ASCII bouquet for your terminal. "
                    "After Ascii-Flower-Bouquet by Alish Sharma (MIT).",
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    parser.add_argument("--config", metavar="PATH", help="config file (default: platform config dir)")
    parser.add_argument("--no-config", action="store_true", help="ignore and do not write config")
    parser.add_argument("--preset", choices=tuple(PRESETS), help="start from a preset")
    parser.add_argument("--theme", choices=THEME_NAMES, help="colour theme")
    parser.add_argument("--detail", choices=DETAIL_CHOICES, help="render detail level (32/64/128/256/auto)")
    parser.add_argument("--style", choices=STYLE_CHOICES, help="render style (ascii/half/braille)")
    parser.add_argument("--greenery", type=int, metavar="N", help="greenery amount (0-20)")
    parser.add_argument("--color-mode", choices=COLOR_MODES, help="colour mode (auto/256/truecolor/mono)")
    parser.add_argument("--fps", type=int, metavar="N", help="target frames per second (5-60)")
    parser.add_argument("--message", metavar="TEXT", help="message shown below the bouquet")
    parser.add_argument("--seed", type=int, metavar="N", help="composition seed")
    parser.add_argument("--ascii", action="store_true", help="ASCII-only glyphs and style=ascii")
    parser.add_argument("--no-color", action="store_true", help="disable colour")
    parser.add_argument("--gallery", action="store_true", help="print all ten varieties and exit")
    parser.add_argument("--snapshot", nargs="?", const="-", metavar="PATH",
                        help="render one frame and exit (stdout when PATH is omitted)")
    parser.add_argument("--at", type=float, default=0.0, metavar="SECONDS",
                        help="animation time for --snapshot / starting time")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = Path(args.config) if args.config else default_config_path()
    warnings: List[str] = []
    if args.no_config:
        settings = Settings()
    else:
        settings, warnings = load_settings(config_path)
    if args.preset:
        settings = apply_preset(settings, args.preset)
    if args.theme:
        settings.theme = args.theme
        settings.wrap = get_theme(args.theme).wrap_style
    if args.detail:
        settings.detail = args.detail
    if args.style:
        settings.style = args.style
    if args.greenery is not None:
        settings.greenery_amount = args.greenery
    if args.color_mode:
        settings.color_mode = args.color_mode
    if args.ascii:
        settings.style = "ascii"
    if args.fps is not None:
        settings.fps = args.fps
    if args.message is not None:
        settings.message = args.message
    if args.seed is not None:
        settings.seed = args.seed
    settings.repair()

    for warning in warnings:
        print("bouquet: %s" % warning, file=sys.stderr)

    no_color = args.no_color or ("NO_COLOR" in os.environ) or settings.color_mode == "mono"

    if args.gallery:
        color = sys.stdout.isatty() and not no_color
        lines = gallery_lines(settings, ansi=color, ascii_mode=args.ascii)
        sys.stdout.write("\n".join(lines) + "\n")
        return 0

    if args.snapshot is not None:
        size = shutil.get_terminal_size(fallback=(80, 24))
        width = max(20, size.columns)
        height = max(12, size.lines)
        ansi = args.snapshot == "-" and sys.stdout.isatty() and not no_color
        output = render_snapshot(
            settings, width, height, max(0.0, args.at), args.ascii, ansi,
        )
        if args.snapshot == "-":
            sys.stdout.write(output)
        else:
            try:
                Path(args.snapshot).write_text(output, encoding="utf-8")
            except OSError as exc:
                print("bouquet: could not write snapshot: %s" % exc, file=sys.stderr)
                return 1
        return 0

    if (not sys.stdin.isatty() or not sys.stdout.isatty()
            or os.environ.get("TERM") == "dumb"):
        size = shutil.get_terminal_size(fallback=(80, 24))
        sys.stdout.write(render_snapshot(
            settings, size.columns, size.lines, max(0.0, args.at), args.ascii, False,
        ))
        return 0

    app = App(
        settings,
        config_path=config_path,
        config_enabled=not args.no_config,
        ascii_mode=args.ascii,
        color=not no_color,
        start_at=max(0.0, args.at),
    )
    if warnings:
        app.toast("Loaded with repairs: " + warnings[0], 6)
    app.run()
    return 0
