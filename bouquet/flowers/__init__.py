"""Flower varieties and the shared shape primitives."""

from __future__ import annotations

from . import varieties  # noqa: F401  (populates the registry)
from .registry import (
    Colorway,
    Sample,
    VarietySpec,
    all_varieties,
    colorway_for,
    get_variety,
    variety_ids,
)

__all__ = [
    "Colorway",
    "Sample",
    "VarietySpec",
    "all_varieties",
    "colorway_for",
    "get_variety",
    "variety_ids",
]
