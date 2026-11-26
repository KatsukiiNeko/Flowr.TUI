"""Flower variety registry.

A variety is a morphological spec plus a pure sampling function.  Sampling
takes a point in the head's unit disc and returns a cell sample, so the
renderer never needs to know which flower it is drawing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

L_PETAL = 0
L_INNER = 1
L_CENTER = 2
L_STAMEN = 3
L_SEPAL = 4
L_PISTIL = 5

LOD_BLOB = 0
LOD_SIMPLIFIED = 1
LOD_FULL = 2


@dataclass(frozen=True)
class Sample:
    coverage: float
    shade: float
    layer: int = L_PETAL
    glyph: str = "petal"
    base: float = 0.62


@dataclass(frozen=True)
class Colorway:
    name: str
    petals: Tuple[int, ...]
    center: Tuple[int, ...]
    accent: Tuple[int, ...] = (22, 28, 34, 35, 71, 77, 114)
    variant: int = 0
    hue: str = ""

    @property
    def hue_family(self) -> str:
        if self.hue:
            return self.hue.lower()
        return _infer_hue(self.name)


def _infer_hue(name: str) -> str:
    low = name.lower()
    for token in ("red", "crimson", "burgundy"):
        if token in low:
            return "red" if token != "burgundy" else "burgundy"
    for token in ("pink", "blush", "magenta", "rose"):
        if token in low:
            return "pink"
    for token in ("white", "cream", "paper"):
        if token in low:
            return "white"
    for token in ("peach", "coral"):
        if token in low:
            return token
    for token in ("yellow", "sunny", "gold"):
        if token in low:
            return "yellow"
    for token in ("orange", "amber", "rust"):
        if token in low:
            return "orange" if token != "rust" else "rust"
    for token in ("purple", "lilac", "violet"):
        if token in low:
            return "purple" if token == "violet" else token
    for token in ("blue", "ice"):
        if token in low:
            return "blue"
    return low or "pink"


ShapeFn = Callable[[float, float, float, int, Colorway], Optional[Sample]]


@dataclass(frozen=True)
class VarietySpec:
    id: str
    name: str
    size: float
    aspect: float
    colorways: Tuple[Colorway, ...]
    shape: ShapeFn
    # Prominent centres keep a visible glyph at the simplified level.
    has_center: bool = False
    blob_glyph: str = "o"


_REGISTRY: List[VarietySpec] = []
_BY_ID: Dict[str, VarietySpec] = {}


def register(spec: VarietySpec) -> VarietySpec:
    if spec.id in _BY_ID:
        raise ValueError("duplicate flower variety: %s" % spec.id)
    if not spec.colorways:
        raise ValueError("variety %s has no colourways" % spec.id)
    if spec.size <= 0 or spec.aspect <= 0:
        raise ValueError("variety %s has an invalid size" % spec.id)
    _REGISTRY.append(spec)
    _BY_ID[spec.id] = spec
    return spec


def all_varieties() -> Tuple[VarietySpec, ...]:
    return tuple(_REGISTRY)


def get_variety(variety_id: str) -> VarietySpec:
    return _BY_ID[variety_id]


def variety_ids() -> Tuple[str, ...]:
    return tuple(spec.id for spec in _REGISTRY)


def colorway_for(spec: VarietySpec, index: int) -> Colorway:
    if not spec.colorways:
        raise ValueError(spec.id)
    return spec.colorways[index % len(spec.colorways)]
