"""Register the ten built-in flower varieties.

Adding a variety means adding a module and one registration line here.
"""

from __future__ import annotations

from ..registry import register
from . import (
    carnation,
    cherry,
    cosmos,
    daisy,
    lily,
    peony,
    poppy,
    rose,
    sunflower,
    tulip,
)

for _module in (
    rose,
    tulip,
    daisy,
    sunflower,
    lily,
    cherry,
    peony,
    carnation,
    poppy,
    cosmos,
):
    register(_module.SPEC)
