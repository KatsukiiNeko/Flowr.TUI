"""Colour themes for Bouquet TUI.

A Theme curates 2-3 main hue families plus at most one accent family (<= 25% of
flowers), and coordinates wrap, ribbon, hearts, message cycling, and greenery
tint.  The ``classic`` theme preserves v1 palettes and assignment exactly.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from typing import Dict, List, Sequence, Tuple

from ..flowers import all_varieties, get_variety
from ..flowers import colorways as c
from ..flowers.registry import Colorway, VarietySpec


@dataclass(frozen=True)
class Theme:
    name: str
    label: str
    hue_families: Tuple[str, ...]
    accent_family: str
    accent_fraction: float = 0.25
    allowed_colorways: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    wrap_style: str = "kraft"
    ribbon_palette: Sequence[int] = c.RIBBON
    heart_colors: Tuple[int, ...] = c.HEART_COLORS
    msg_colors: Tuple[int, ...] = c.MSG_COLORS
    greenery_tint: str = "default"  # "default", "dusty", "deep", "silver"


HUE_PALETTES: Dict[str, Tuple[int, ...]] = {
    "red": c.RED,
    "pink": c.PINK,
    "blush": c.BLUSH,
    "white": c.WHITE,
    "cream": c.CREAM,
    "peach": c.PEACH,
    "coral": c.CORAL,
    "orange": c.ORANGE,
    "yellow": c.YELLOW,
    "gold": c.GOLD,
    "purple": c.PURPLE,
    "lilac": c.LILAC,
    "blue": c.BLUE,
    "ice-blue": c.ICE_BLUE,
    "silver": c.SILVER,
    "rust": c.RUST,
    "burgundy": c.BURGUNDY,
}

# Canonical RGB distances for nearest-hue matching
_HUE_RGB: Dict[str, Tuple[int, int, int]] = {
    "red": (210, 30, 35),
    "pink": (235, 110, 175),
    "blush": (245, 195, 210),
    "white": (245, 245, 245),
    "cream": (242, 232, 208),
    "peach": (245, 185, 145),
    "coral": (235, 115, 100),
    "orange": (235, 140, 30),
    "yellow": (240, 215, 45),
    "gold": (215, 165, 45),
    "purple": (150, 75, 195),
    "lilac": (190, 160, 225),
    "blue": (75, 125, 185),
    "ice-blue": (165, 205, 240),
    "silver": (195, 200, 210),
    "rust": (175, 75, 40),
    "burgundy": (130, 30, 55),
}


THEMES: Dict[str, Theme] = {}


def _reg(theme: Theme) -> Theme:
    THEMES[theme.name] = theme
    return theme


_reg(Theme(
    name="classic",
    label="Classic",
    hue_families=("white", "pink", "yellow", "red", "purple", "orange"),
    accent_family="red",
    accent_fraction=0.25,
    wrap_style="kraft",
    ribbon_palette=c.RIBBON,
    heart_colors=c.HEART_COLORS,
    msg_colors=c.MSG_COLORS,
    greenery_tint="default",
))

_reg(Theme(
    name="blush",
    label="Blush",
    hue_families=("pink", "white", "peach"),
    accent_family="red",
    accent_fraction=0.20,
    allowed_colorways={
        "rose": ("Pink", "White", "Peach", "Red"),
        "tulip": ("Pink", "White", "Red"),
        "daisy": ("White", "Pink", "Red"),
        "cherry": ("Blush", "Pink", "White"),
        "peony": ("Pink", "White", "Coral"),
        "carnation": ("Pink", "White", "Red"),
        "lily": ("White", "Pink"),
        "cosmos": ("Pink", "White"),
        "poppy": ("Pink", "White", "Red"),
        "sunflower": ("Cream",),
    },
    wrap_style="cream",
    ribbon_palette=c.PINK,
    heart_colors=(168, 205, 211, 218, 225),
    msg_colors=(218, 211, 205, 225, 231, 225, 205, 211),
    greenery_tint="dusty",
))

_reg(Theme(
    name="romantic-reds",
    label="Romantic Reds",
    hue_families=("red", "pink", "white"),
    accent_family="gold",
    accent_fraction=0.20,
    allowed_colorways={
        "rose": ("Red", "Pink", "White"),
        "tulip": ("Red", "Pink", "White", "Yellow"),
        "carnation": ("Red", "Pink", "White"),
        "poppy": ("Red", "Pink", "White"),
        "peony": ("Pink", "Magenta", "White"),
        "daisy": ("Red", "Pink", "White"),
        "cherry": ("Pink", "White"),
        "lily": ("White", "Pink"),
        "cosmos": ("Pink", "White"),
    },
    wrap_style="cream",
    ribbon_palette=c.RED,
    heart_colors=(160, 196, 197, 203, 211),
    msg_colors=(160, 196, 203, 211, 231, 211, 203, 196),
    greenery_tint="deep",
))

_reg(Theme(
    name="sunset",
    label="Sunset",
    hue_families=("orange", "yellow", "coral"),
    accent_family="purple",
    accent_fraction=0.20,
    allowed_colorways={
        "sunflower": ("Sunny", "Amber"),
        "poppy": ("Orange", "Red"),
        "peony": ("Coral",),
        "lily": ("Orange",),
        "daisy": ("Yellow", "Orange", "Purple"),
        "tulip": ("Yellow", "Purple"),
        "rose": ("Peach",),
        "cosmos": ("Pink",),
    },
    wrap_style="kraft",
    ribbon_palette=c.ORANGE,
    heart_colors=(166, 202, 208, 214, 220),
    msg_colors=(202, 208, 214, 220, 226, 220, 214, 208),
    greenery_tint="default",
))

_reg(Theme(
    name="lavender-dream",
    label="Lavender Dream",
    hue_families=("purple", "pink", "white"),
    accent_family="yellow",
    accent_fraction=0.20,
    allowed_colorways={
        "tulip": ("Purple", "Pink", "White", "Yellow"),
        "daisy": ("Purple", "Pink", "White", "Yellow"),
        "cosmos": ("Pink", "Magenta", "White"),
        "rose": ("Pink", "White"),
        "peony": ("Pink", "Magenta", "White"),
        "cherry": ("Blush", "Pink", "White"),
        "carnation": ("Pink", "White"),
        "lily": ("White", "Pink"),
        "sunflower": ("Sunny", "Cream"),
    },
    wrap_style="cream",
    ribbon_palette=c.LILAC,
    heart_colors=(134, 140, 176, 183, 218),
    msg_colors=(134, 140, 176, 183, 225, 183, 176, 140),
    greenery_tint="dusty",
))

_reg(Theme(
    name="spring-pastel",
    label="Spring Pastel",
    hue_families=("pink", "yellow", "white"),
    accent_family="lilac",
    accent_fraction=0.25,
    allowed_colorways={
        "cherry": ("Blush", "Pink", "White"),
        "daisy": ("White", "Pink", "Yellow", "Purple"),
        "tulip": ("Pink", "Yellow", "White", "Purple"),
        "cosmos": ("Pink", "White"),
        "rose": ("Pink", "White", "Peach"),
        "lily": ("White", "Pink"),
        "carnation": ("Pink", "White"),
        "peony": ("Pink", "White"),
        "sunflower": ("Sunny", "Cream"),
    },
    wrap_style="cream",
    ribbon_palette=c.PINK,
    heart_colors=(175, 183, 218, 225, 229),
    msg_colors=(218, 225, 229, 183, 231, 183, 229, 225),
    greenery_tint="default",
))

_reg(Theme(
    name="autumn",
    label="Autumn",
    hue_families=("rust", "gold", "burgundy"),
    accent_family="cream",
    accent_fraction=0.25,
    allowed_colorways={
        "sunflower": ("Amber", "Burgundy", "Cream", "Sunny"),
        "poppy": ("Orange", "Red", "White"),
        "rose": ("Red", "Peach", "White"),
        "tulip": ("Red", "Yellow", "White"),
        "carnation": ("Red", "White"),
        "lily": ("Orange", "White"),
        "daisy": ("Orange", "Yellow", "Red", "White"),
        "peony": ("Coral", "White"),
    },
    wrap_style="kraft",
    ribbon_palette=c.BURGUNDY,
    heart_colors=(124, 130, 166, 173, 214),
    msg_colors=(130, 166, 173, 214, 223, 214, 173, 166),
    greenery_tint="default",
))

_reg(Theme(
    name="moonlight",
    label="Moonlight",
    hue_families=("white", "ice-blue", "lilac"),
    accent_family="pink",
    accent_fraction=0.20,
    allowed_colorways={
        "lily": ("White", "Pink"),
        "rose": ("White", "Pink"),
        "tulip": ("White", "Purple", "Pink"),
        "daisy": ("White", "Purple", "Pink"),
        "cherry": ("White", "Blush", "Pink"),
        "carnation": ("White", "Pink"),
        "peony": ("White", "Pink"),
        "cosmos": ("White", "Pink"),
        "sunflower": ("Cream",),
        "poppy": ("White", "Pink"),
    },
    wrap_style="black",
    ribbon_palette=c.ICE_BLUE,
    heart_colors=(110, 153, 189, 195, 225),
    msg_colors=(110, 153, 189, 231, 225, 231, 189, 153),
    greenery_tint="silver",
))

_reg(Theme(
    name="rainbow",
    label="Rainbow",
    hue_families=("red", "orange", "yellow", "pink", "purple", "blue"),
    accent_family="white",
    accent_fraction=0.20,
    wrap_style="kraft",
    ribbon_palette=c.RIBBON,
    heart_colors=c.HEART_COLORS,
    msg_colors=c.MSG_COLORS,
    greenery_tint="default",
))

THEME_NAMES: Tuple[str, ...] = tuple(THEMES.keys())
CURATED_THEME_NAMES: Tuple[str, ...] = tuple(n for n in THEME_NAMES if n not in ("classic", "rainbow"))


def get_theme(name: str) -> Theme:
    return THEMES.get(name, THEMES["classic"])


def _hue_distance(h1: str, h2: str) -> float:
    a = _HUE_RGB.get(h1, (200, 200, 200))
    b = _HUE_RGB.get(h2, (200, 200, 200))
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def nearest_colorway(spec: VarietySpec, target_hue: str) -> Colorway:
    """Return the variety's colorway closest by hue to *target_hue*."""
    return min(spec.colorways, key=lambda cw: _hue_distance(cw.hue_family, target_hue))


def resolve_themed_colorway(
    spec: VarietySpec,
    target_hue: str,
    theme: Theme,
) -> Colorway:
    """Resolve a Colorway for *spec* strictly inside *target_hue* for curated themes."""
    matching = [cw for cw in spec.colorways if cw.hue_family == target_hue]
    if matching:
        return matching[0]
    base_cw = nearest_colorway(spec, target_hue)
    palette = HUE_PALETTES.get(target_hue)
    if palette is None:
        return base_cw
    return replace(base_cw, name=target_hue.title(), petals=palette, hue=target_hue)


def assign_themed_hues(theme: Theme, total: int, seed: int) -> List[str]:
    """Deterministically assign hue families for *total* flowers respecting accent cap."""
    rng = random.Random(seed ^ 0x74E3E)
    main = list(theme.hue_families)
    max_accent = int(total * theme.accent_fraction)
    # Assign slots, ensuring accent count <= max_accent
    hues: List[str] = []
    accent_indices = set()
    if max_accent > 0 and total >= 4:
        n_accent = rng.randint(0, max_accent)
        accent_indices = set(rng.sample(range(total), n_accent))
    for i in range(total):
        if i in accent_indices:
            hues.append(theme.accent_family)
        else:
            hues.append(main[rng.randrange(len(main))])
    return hues


def preferred_varieties_for_theme(theme: Theme) -> Tuple[str, ...]:
    """Return variety ids that natively match *theme*, falling back to all."""
    if theme.name in ("classic", "rainbow"):
        return tuple(spec.id for spec in all_varieties())
    theme_hues = set(theme.hue_families) | {theme.accent_family}
    preferred = []
    for spec in all_varieties():
        if spec.id in theme.allowed_colorways or any(cw.hue_family in theme_hues for cw in spec.colorways):
            preferred.append(spec.id)
    return tuple(preferred) if preferred else tuple(spec.id for spec in all_varieties())
