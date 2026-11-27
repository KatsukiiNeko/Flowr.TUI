"""Settings: one metadata-driven dataclass, presets and (de)serialisation.

Every user-facing setting lives in :class:`Settings`.  The panel, the presets
and the JSON loader all read the same field metadata, so adding a setting means
touching one place.  Unknown or out-of-range values in a config file are
repaired rather than trusted.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from ..flowers import all_varieties
from ..flowers.colorways import SOLID_MESSAGE_COLORS, WRAP_STYLES

VERSION = 2
MAX_FLOWERS = 24
MAX_MESSAGE = 120

LAYOUTS = ("interleaved", "clustered", "random")
MESSAGE_MODES = ("cycling", "solid", "none")
THEME_NAMES = (
    "classic",
    "blush",
    "romantic-reds",
    "sunset",
    "lavender-dream",
    "spring-pastel",
    "autumn",
    "moonlight",
    "rainbow",
)
DETAIL_CHOICES = ("auto", "32", "64", "128", "256")
STYLE_CHOICES = ("ascii", "half", "braille", "sextant")
COLOR_MODES = ("auto", "256", "truecolor", "mono")
GREENERY_TYPES = ("eucalyptus", "fern", "wheat", "mixed", "off")

TAB_FLOWERS = "Flowers"
TAB_LOOK = "Look"
TAB_ANIMATION = "Animation"
TAB_EFFECTS = "Effects"
TAB_MESSAGE = "Message"
TAB_PRESETS = "Presets"
TABS = (TAB_FLOWERS, TAB_LOOK, TAB_ANIMATION, TAB_EFFECTS, TAB_MESSAGE, TAB_PRESETS)


@dataclass(frozen=True)
class FieldMeta:
    field: str
    label: str
    tab: str
    kind: str = "int"  # int, float, bool, choice, text, action
    minimum: float = 0
    maximum: float = 100
    step: float = 1
    coarse: float = 5
    choices: Tuple[str, ...] = ()
    persist: bool = True
    hint: str = ""


VARIETY_IDS = tuple(spec.id for spec in all_varieties())
VARIETY_NAMES = {spec.id: spec.name for spec in all_varieties()}
VARIETY_COLORWAYS = {spec.id: tuple(cw.name for cw in spec.colorways) for spec in all_varieties()}


def count_field(variety_id: str) -> str:
    return variety_id + "_count"


COUNT_META = {
    count_field(variety_id): FieldMeta(
        count_field(variety_id),
        VARIETY_NAMES[variety_id],
        TAB_FLOWERS,
        "int",
        0,
        24,
        1,
        5,
        hint="Number of %s heads (total cap %d)" % (VARIETY_NAMES[variety_id], MAX_FLOWERS),
    )
    for variety_id in VARIETY_IDS
}

FIELD_META: Dict[str, FieldMeta] = {
    # Look tab
    "theme": FieldMeta("theme", "Theme", TAB_LOOK, "choice", choices=THEME_NAMES,
                       hint="Curated palette for flowers, wrap, ribbon and hearts"),
    "detail": FieldMeta("detail", "Detail", TAB_LOOK, "choice", choices=DETAIL_CHOICES,
                        hint="Internal sample canvas height (Auto matches terminal)"),
    "style": FieldMeta("style", "Style", TAB_LOOK, "choice", choices=STYLE_CHOICES,
                       hint="Glyph style: ascii (1x1), half (1x2), braille (2x4), sextant (2x3)"),
    "color_mode": FieldMeta("color_mode", "Colour mode", TAB_LOOK, "choice", choices=COLOR_MODES,
                            hint="auto uses 24-bit truecolor when COLORTERM is set"),
    "wrap": FieldMeta("wrap", "Wrap", TAB_LOOK, "choice", choices=WRAP_STYLES,
                      hint="Paper cone colour style"),
    "greenery_amount": FieldMeta("greenery_amount", "Greenery", TAB_LOOK, "int", 0, 20, 1, 5,
                                 hint="Filler sprigs around bouquet (0-20)"),
    "greenery_type": FieldMeta("greenery_type", "Greenery type", TAB_LOOK, "choice",
                               choices=GREENERY_TYPES, hint="Greenery foliage style"),
    "outlines": FieldMeta("outlines", "Head outlines", TAB_LOOK, "bool",
                          hint="Contact shadow and rim between overlapping heads"),
    "depth_cue": FieldMeta("depth_cue", "Depth cue", TAB_LOOK, "int", 0, 100, 5, 20,
                           hint="Dimming applied to farther heads (0-100%)"),
    "petal_gradient": FieldMeta("petal_gradient", "Petal gradient", TAB_LOOK, "bool",
                                hint="Shade petals darker at base and brighter at tips"),
    # Animation tab
    "fps": FieldMeta("fps", "FPS", TAB_ANIMATION, "int", 5, 60, 1, 5,
                     hint="Target frames per second"),
    "spin": FieldMeta("spin", "Spin speed", TAB_ANIMATION, "float", -3.0, 3.0, 0.05, 0.3,
                      hint="Rotation speed in rad/s"),
    "tilt": FieldMeta("tilt", "Tilt", TAB_ANIMATION, "float", 0.0, 1.2, 0.02, 0.1,
                      hint="Camera pitch angle in radians"),
    "camera": FieldMeta("camera", "Camera", TAB_ANIMATION, "float", 2.0, 8.0, 0.1, 0.5,
                        hint="Camera distance from bouquet"),
    # Effects tab
    "sway": FieldMeta("sway", "Sway", TAB_EFFECTS, "bool",
                      hint="Gentle horizontal wind sway"),
    "sway_degrees": FieldMeta("sway_degrees", "Sway angle", TAB_EFFECTS, "float", 0.0, 2.0, 0.1, 0.5,
                              hint="Maximum sway amplitude in degrees"),
    "bob": FieldMeta("bob", "Head bob", TAB_EFFECTS, "bool",
                     hint="Subtle per-head vertical bobbing"),
    "hearts": FieldMeta("hearts", "Hearts", TAB_EFFECTS, "int", 0, 60, 1, 5,
                        hint="Drifting heart particles"),
    "petal_fall": FieldMeta("petal_fall", "Petal fall", TAB_EFFECTS, "int", 0, 40, 1, 5,
                            hint="Drifting fallen petals behind bouquet"),
    "sparkles": FieldMeta("sparkles", "Sparkles", TAB_EFFECTS, "bool",
                          hint="Twinkling ambient sparkles"),
    "sparkle_density": FieldMeta("sparkle_density", "Sparkle density", TAB_EFFECTS, "int", 0, 60, 2, 10,
                                 hint="Number of sparkle points"),
    "babies": FieldMeta("babies", "Baby's breath", TAB_EFFECTS, "bool",
                        hint="Small white filler blossoms"),
    "baby_density": FieldMeta("baby_density", "Baby's breath density", TAB_EFFECTS, "int", 0, 180, 5, 25,
                              hint="Number of baby's breath points"),
    "ribbon": FieldMeta("ribbon", "Ribbon", TAB_EFFECTS, "bool",
                        hint="Ribbon band and bow around the wrap"),
    # Message tab
    "message": FieldMeta("message", "Message", TAB_MESSAGE, "text", 0, MAX_MESSAGE, 1, 1,
                         hint="Caption shown below the bouquet"),
    "message_mode": FieldMeta(
        "message_mode", "Colour mode", TAB_MESSAGE, "choice", choices=MESSAGE_MODES,
        hint="Cycling, solid colour, or plain text",
    ),
    "message_color": FieldMeta(
        "message_color", "Solid colour", TAB_MESSAGE, "choice",
        choices=tuple(name for name, _ in SOLID_MESSAGE_COLORS),
        hint="Message colour when mode is solid",
    ),
    "message_speed": FieldMeta("message_speed", "Colour speed", TAB_MESSAGE, "int", 0, 20, 1, 5,
                               hint="Message colour cycle speed"),
    # Flowers tab
    "layout": FieldMeta("layout", "Layout", TAB_FLOWERS, "choice", choices=LAYOUTS,
                        hint="Order flowers are placed around the cap"),
    "seed": FieldMeta("seed", "Seed", TAB_FLOWERS, "int", 0, 999999, 1, 100,
                      hint="Random seed for layout, filler and jitter"),
}
FIELD_META.update(COUNT_META)


def _default_counts() -> Dict[str, int]:
    return {variety_id: (8 if variety_id == "daisy" else 2 if variety_id == "tulip" else 0)
            for variety_id in VARIETY_IDS}


def _default_colorways() -> Dict[str, int]:
    return {variety_id: -1 for variety_id in VARIETY_IDS}


@dataclass
class Settings:
    fps: int = 24
    spin: float = 0.6
    tilt: float = 0.30
    camera: float = 4.0
    sway: bool = True
    sway_degrees: float = 2.0
    bob: bool = True
    hearts: int = 18
    petal_fall: int = 8
    sparkles: bool = True
    sparkle_density: int = 30
    babies: bool = True
    baby_density: int = 90
    ribbon: bool = True
    message: str = "for you \u2665"
    message_mode: str = "cycling"
    message_color: str = "Pink"
    message_speed: int = 6
    layout: str = "interleaved"
    seed: int = 21
    theme: str = "classic"
    detail: str = "auto"
    style: str = "ascii"
    color_mode: str = "auto"
    wrap: str = "kraft"
    greenery_amount: int = 8
    greenery_type: str = "eucalyptus"
    outlines: bool = True
    depth_cue: int = 60
    petal_gradient: bool = True
    counts: Dict[str, int] = field(default_factory=_default_counts)
    colorways: Dict[str, int] = field(default_factory=_default_colorways)
    preset: str = "Classic"
    paused: bool = False

    def __post_init__(self) -> None:
        self.repair()

    # -- accessors ---------------------------------------------------------
    def count(self, variety_id: str) -> int:
        return int(self.counts.get(variety_id, 0))

    def set_count(self, variety_id: str, value: int) -> None:
        self.counts[variety_id] = int(value)

    def total_flowers(self) -> int:
        return sum(self.count(variety_id) for variety_id in VARIETY_IDS)

    def colorway(self, variety_id: str) -> int:
        return int(self.colorways.get(variety_id, -1))

    # -- validation --------------------------------------------------------
    def repair(self) -> List[str]:
        """Clamp everything into range.  Returns human-readable repairs."""
        warnings: List[str] = []
        for meta in FIELD_META.values():
            if meta.field in COUNT_META or not hasattr(self, meta.field) or not meta.persist:
                continue
            value = getattr(self, meta.field)
            fixed = _coerce(meta, value)
            if fixed != value:
                warnings.append("%s repaired" % meta.label)
                setattr(self, meta.field, fixed)

        if self.message_mode not in MESSAGE_MODES:
            self.message_mode = "cycling"
            warnings.append("colour mode repaired")
        if self.message_color not in _solid_color_names():
            self.message_color = "Pink"
            warnings.append("message colour repaired")
        if self.layout not in LAYOUTS:
            self.layout = "interleaved"
            warnings.append("layout repaired")
        if self.theme not in THEME_NAMES:
            self.theme = "classic"
            warnings.append("theme repaired")
        if self.detail not in DETAIL_CHOICES:
            self.detail = "auto"
            warnings.append("detail repaired")
        if self.style not in STYLE_CHOICES:
            self.style = "ascii"
            warnings.append("style repaired")
        if self.color_mode not in COLOR_MODES:
            self.color_mode = "auto"
            warnings.append("colour mode repaired")
        if self.wrap not in WRAP_STYLES:
            self.wrap = "kraft"
            warnings.append("wrap repaired")
        if self.greenery_type not in GREENERY_TYPES:
            self.greenery_type = "eucalyptus"
            warnings.append("greenery type repaired")

        self.message = sanitize_message(self.message)
        for variety_id in VARIETY_IDS:
            value = int(self.colorways.get(variety_id, -1))
            limit = len(VARIETY_COLORWAYS.get(variety_id, ()))
            if value < -1 or value >= limit:
                value = -1
                warnings.append("%s colourway repaired" % VARIETY_NAMES[variety_id])
            self.colorways[variety_id] = value

        counts = {
            variety_id: int(_coerce(COUNT_META[count_field(variety_id)], self.count(variety_id)))
            for variety_id in VARIETY_IDS
        }
        if sum(counts.values()) == 0:
            counts["daisy"] = 1
            warnings.append("flower count repaired")
        while sum(counts.values()) > MAX_FLOWERS:
            victim = max(VARIETY_IDS, key=lambda vid: (counts[vid], -VARIETY_IDS.index(vid)))
            counts[victim] -= 1
            if counts[victim] < 0:
                counts[victim] = 0
                break
            warnings.append("flower total trimmed to %d" % MAX_FLOWERS)
        self.counts = counts

        if self.preset not in PRESETS:
            self.preset = "Custom"
        return _unique(warnings)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        for meta in FIELD_META.values():
            if not meta.persist:
                continue
            if meta.field in COUNT_META:
                variety_id = meta.field[:-len("_count")]
                data[meta.field] = self.count(variety_id)
            else:
                data[meta.field] = getattr(self, meta.field)
        data["colorways"] = {vid: self.colorway(vid) for vid in VARIETY_IDS}
        data["preset"] = self.preset
        return {"version": VERSION, "settings": data}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Tuple["Settings", List[str]]:
        warnings: List[str] = []
        if not isinstance(payload, Mapping):
            return cls(), ["config is not an object"]
        version = payload.get("version", VERSION)
        if isinstance(version, (int, float)) and version > VERSION:
            warnings.append("config version %s is newer; known fields loaded" % version)
        data = payload.get("settings")
        if not isinstance(data, Mapping):
            data = payload  # tolerate a flat, hand-written config
        settings = cls()
        # Note: v1 configs won't have new v2 fields, so they keep v2 defaults
        # except Classic preset keeps v1 classic look unless overridden.
        for meta in FIELD_META.values():
            if not meta.persist or meta.field not in data:
                continue
            raw = data[meta.field]
            value = _coerce(meta, raw)
            if value != raw:
                warnings.append("%s repaired" % meta.label)
            if meta.field in COUNT_META:
                settings.set_count(meta.field[:-len("_count")], value)
            else:
                setattr(settings, meta.field, value)
        raw_colorways = data.get("colorways")
        if isinstance(raw_colorways, Mapping):
            for variety_id in VARIETY_IDS:
                if variety_id in raw_colorways:
                    try:
                        settings.colorways[variety_id] = int(raw_colorways[variety_id])
                    except (TypeError, ValueError):
                        warnings.append("%s colourway reset" % VARIETY_NAMES[variety_id])
        if isinstance(data.get("preset"), str):
            settings.preset = data["preset"]
        warnings.extend(settings.repair())
        return settings, warnings

    @classmethod
    def from_json_text(cls, text: str) -> Tuple["Settings", List[str]]:
        import json

        try:
            payload = json.loads(text)
        except (ValueError, TypeError) as exc:
            return cls(), ["config is not valid JSON: %s" % exc]
        return cls.from_dict(payload)


def _solid_color_names() -> Tuple[str, ...]:
    from ..flowers.colorways import SOLID_MESSAGE_COLORS

    return tuple(name for name, _ in SOLID_MESSAGE_COLORS)


def _coerce(meta: FieldMeta, value: Any) -> Any:
    if meta.kind == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return False
    if meta.kind in ("int", "float"):
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = float(meta.minimum)
        if not math.isfinite(number):
            number = float(meta.minimum)
        number = max(float(meta.minimum), min(float(meta.maximum), number))
        return int(round(number)) if meta.kind == "int" else round(number, 4)
    if meta.kind == "choice":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            value = str(int(value))
        return value if value in meta.choices else (meta.choices[0] if meta.choices else "")
    if meta.kind == "text":
        if not isinstance(value, str):
            value = str(value)
        return sanitize_message(value)
    return value


def sanitize_message(value: str) -> str:
    text = "".join(ch for ch in str(value) if ch >= " " and ch != "\x7f")
    return text.replace("\r", " ").replace("\n", " ").replace("\t", " ")[:MAX_MESSAGE]


def _unique(items: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


# -- presets --------------------------------------------------------------
# Note (DET-6): Presets never change detail, style or color_mode.

def _preset_fields(**kwargs: Any) -> Dict[str, Any]:
    fields: Dict[str, Any] = {
        "fps": 24,
        "spin": 0.6,
        "tilt": 0.30,
        "camera": 4.0,
        "sway": True,
        "sway_degrees": 2.0,
        "bob": True,
        "hearts": 18,
        "petal_fall": 8,
        "sparkles": True,
        "sparkle_density": 30,
        "babies": True,
        "baby_density": 90,
        "ribbon": True,
        "message": "for you \u2665",
        "message_mode": "cycling",
        "message_color": "Pink",
        "message_speed": 6,
        "layout": "interleaved",
        "seed": 21,
        "theme": "classic",
        "wrap": "kraft",
        "greenery_amount": 8,
        "greenery_type": "eucalyptus",
        "outlines": True,
        "depth_cue": 60,
        "petal_gradient": True,
        "colorways": _default_colorways(),
    }
    counts = {variety_id: 0 for variety_id in VARIETY_IDS}
    counts.update(kwargs.pop("counts", {}))
    fields["counts"] = counts
    fields.update(kwargs)
    return fields


PRESETS: Dict[str, Dict[str, Any]] = {
    "Classic": _preset_fields(
        counts={"daisy": 8, "tulip": 2},
        theme="classic",
        wrap="kraft",
        greenery_amount=0,
        greenery_type="off",
        petal_fall=0,
    ),
    "Spring Garden": _preset_fields(
        counts={"rose": 1, "tulip": 2, "daisy": 2, "cherry": 2, "cosmos": 2, "lily": 1},
        hearts=24,
        seed=7,
        message="hello \u2665",
        message_color="Blush",
        layout="interleaved",
        theme="spring-pastel",
        wrap="cream",
        greenery_amount=10,
        greenery_type="eucalyptus",
    ),
    "Romantic Reds": _preset_fields(
        counts={"rose": 3, "tulip": 2, "poppy": 2, "carnation": 2},
        hearts=12,
        seed=13,
        message="for you \u2665",
        message_mode="solid",
        message_color="Crimson",
        layout="clustered",
        theme="romantic-reds",
        wrap="cream",
        greenery_amount=6,
        greenery_type="fern",
    ),
    "Sunny Field": _preset_fields(
        counts={"sunflower": 3, "daisy": 4, "tulip": 2, "cosmos": 1},
        hearts=24,
        seed=42,
        message="hello \u2665",
        message_color="Gold",
        layout="interleaved",
        theme="sunset",
        wrap="kraft",
        greenery_amount=8,
        greenery_type="wheat",
    ),
    "Wildflower Mix": _preset_fields(
        counts={"rose": 1, "tulip": 1, "daisy": 1, "sunflower": 1, "lily": 1,
                "cherry": 1, "peony": 1, "carnation": 1, "poppy": 1, "cosmos": 1},
        hearts=32,
        sparkle_density=40,
        seed=99,
        message="wild at heart \u2665",
        layout="random",
        theme="rainbow",
        wrap="kraft",
        greenery_amount=10,
        greenery_type="mixed",
    ),
    "Blush": _preset_fields(
        counts={"rose": 2, "peony": 2, "cherry": 2, "tulip": 2, "cosmos": 2},
        hearts=20,
        seed=18,
        message="blush \u2665",
        message_color="Blush",
        layout="interleaved",
        theme="blush",
        wrap="blush",
        greenery_amount=8,
        greenery_type="eucalyptus",
    ),
    "Moonlight": _preset_fields(
        counts={"rose": 2, "tulip": 1, "lily": 2, "poppy": 2, "cosmos": 2},
        hearts=12,
        sparkle_density=45,
        baby_density=70,
        seed=3,
        message="midnight \u2665",
        message_mode="solid",
        message_color="Ice",
        layout="clustered",
        theme="moonlight",
        wrap="black",
        greenery_amount=8,
        greenery_type="eucalyptus",
    ),
    "Autumn Harvest": _preset_fields(
        counts={"sunflower": 2, "rose": 2, "poppy": 2, "carnation": 2, "daisy": 2},
        hearts=10,
        seed=55,
        message="autumn \u2665",
        message_mode="solid",
        message_color="Amber",
        layout="interleaved",
        theme="autumn",
        wrap="kraft",
        greenery_amount=10,
        greenery_type="wheat",
    ),
    "Minimal": _preset_fields(
        counts={"rose": 2},
        hearts=0,
        petal_fall=0,
        sparkles=False,
        sparkle_density=0,
        babies=False,
        baby_density=0,
        ribbon=False,
        sway=False,
        bob=False,
        message="",
        message_mode="none",
        seed=21,
        theme="classic",
        wrap="kraft",
        greenery_amount=0,
        greenery_type="off",
    ),
    # Aliases preserved for v1 compatibility
    "Pastel": _preset_fields(
        counts={"rose": 1, "tulip": 2, "daisy": 2, "cherry": 2, "cosmos": 2, "lily": 1},
        hearts=24,
        seed=7,
        message="hello \u2665",
        message_color="Blush",
        layout="interleaved",
        theme="spring-pastel",
        wrap="cream",
        greenery_amount=8,
        greenery_type="eucalyptus",
    ),
    "Midnight": _preset_fields(
        counts={"rose": 2, "tulip": 1, "lily": 2, "poppy": 2, "cosmos": 2},
        hearts=12,
        sparkle_density=45,
        baby_density=70,
        seed=3,
        message="midnight \u2665",
        message_mode="solid",
        message_color="Ice",
        layout="clustered",
        theme="moonlight",
        wrap="black",
        greenery_amount=8,
        greenery_type="eucalyptus",
    ),
    "Wildflower": _preset_fields(
        counts={"rose": 1, "tulip": 1, "daisy": 1, "sunflower": 1, "lily": 1,
                "cherry": 1, "peony": 1, "carnation": 1, "poppy": 1, "cosmos": 1},
        hearts=32,
        sparkle_density=40,
        seed=99,
        message="wild at heart \u2665",
        layout="random",
        theme="rainbow",
        wrap="kraft",
        greenery_amount=10,
        greenery_type="mixed",
    ),
}


def apply_preset(settings: Settings, name: str) -> Settings:
    if name not in PRESETS:
        raise KeyError("unknown preset: %s" % name)
    values = dict(PRESETS[name])
    colorways = dict(values.pop("colorways"))
    result = dataclasses.replace(settings, **values, colorways=colorways, preset=name)
    result.repair()
    return result


def is_preset_unchanged(settings: Settings) -> bool:
    if settings.preset not in PRESETS:
        return False
    reference = apply_preset(settings, settings.preset)
    for meta in FIELD_META.values():
        if not meta.persist or meta.field in ("detail", "style", "color_mode"):
            continue
        if meta.field in COUNT_META:
            variety_id = meta.field[:-len("_count")]
            if settings.count(variety_id) != reference.count(variety_id):
                return False
        elif getattr(settings, meta.field) != getattr(reference, meta.field):
            return False
    return settings.colorways == reference.colorways
