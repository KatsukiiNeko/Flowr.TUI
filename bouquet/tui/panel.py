"""Settings panel: flowers, look, animation, effects, message and presets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from ..config.settings import (
    FIELD_META,
    MAX_FLOWERS,
    PRESETS,
    TABS,
    TAB_ANIMATION,
    TAB_EFFECTS,
    TAB_FLOWERS,
    TAB_LOOK,
    TAB_MESSAGE,
    TAB_PRESETS,
    Settings,
)
from ..flowers import get_variety
from ..render.buffer import CellBuffer
from ..render.resolvers import effective_resolution, effective_style
from ..render.samples import HAS_NUMPY
from ..text import ascii_text, display_width, fit, truncate
from .widgets import draw_box

Rect = Tuple[int, int, int, int]

_LOOK_FIELDS = (
    "theme", "detail", "style", "color_mode", "wrap",
    "greenery_amount", "greenery_type", "outlines", "depth_cue", "petal_gradient",
)
_ANIM_FIELDS = ("fps", "spin", "tilt", "camera")
_EFFECT_FIELDS = (
    "sway", "sway_degrees", "bob", "hearts", "petal_fall",
    "sparkles", "sparkle_density", "babies", "baby_density", "ribbon",
)


@dataclass
class PanelRow:
    kind: str
    label: str
    field: str = ""
    value: Any = None
    action: str = ""
    data: Any = None
    options: Tuple[str, ...] = ()


class Panel:
    def __init__(self) -> None:
        self.tab_index = 0
        self.selected = {tab: 0 for tab in TABS}

    @property
    def tab(self) -> str:
        return TABS[self.tab_index]

    def next_tab(self, delta: int = 1) -> None:
        self.tab_index = (self.tab_index + delta) % len(TABS)

    def rows(self, settings: Settings) -> List[PanelRow]:
        tab = self.tab
        rows: List[PanelRow] = []
        if tab == TAB_FLOWERS:
            for variety_id, spec in _varieties():
                field = variety_id + "_count"
                rows.append(PanelRow("count", spec.name, field=field,
                                     value=settings.count(variety_id),
                                     options=(str(MAX_FLOWERS),)))
            rows.append(PanelRow("field", "Layout", field="layout",
                                 value=settings.layout, options=FIELD_META["layout"].choices))
            rows.append(PanelRow("field", "Seed", field="seed", value=settings.seed))
            rows.append(PanelRow("action", "Shuffle bouquet", action="shuffle"))
            rows.append(PanelRow("info", "Total",
                                 value="%d / %d" % (settings.total_flowers(), MAX_FLOWERS)))
            rows.append(PanelRow("info", "Colourways", value=""))
            for variety_id, spec in _varieties():
                rows.append(PanelRow("colorway", spec.name, field=variety_id,
                                     value=settings.colorway(variety_id),
                                     options=tuple(cw.name for cw in spec.colorways)))
        elif tab == TAB_LOOK:
            for field in _LOOK_FIELDS:
                meta = FIELD_META[field]
                rows.append(PanelRow("field", meta.label, field=field,
                                     value=getattr(settings, field), options=meta.choices))
        elif tab == TAB_ANIMATION:
            rows.append(PanelRow("paused", "Paused", value=settings.paused))
            for field in _ANIM_FIELDS:
                meta = FIELD_META[field]
                rows.append(PanelRow("field", meta.label, field=field,
                                     value=getattr(settings, field)))
            rows.append(PanelRow("action", "Reset animation", action="reset_animation"))
        elif tab == TAB_EFFECTS:
            for field in _EFFECT_FIELDS:
                meta = FIELD_META[field]
                rows.append(PanelRow("field", meta.label, field=field,
                                     value=getattr(settings, field)))
        elif tab == TAB_MESSAGE:
            rows.append(PanelRow("action", "Edit message", action="edit_message"))
            rows.append(PanelRow("field", "Colour mode", field="message_mode",
                                 value=settings.message_mode,
                                 options=FIELD_META["message_mode"].choices))
            rows.append(PanelRow("field", "Solid colour", field="message_color",
                                 value=settings.message_color,
                                 options=FIELD_META["message_color"].choices))
            rows.append(PanelRow("field", "Colour speed", field="message_speed",
                                 value=settings.message_speed))
            preview = settings.message or "(empty)"
            rows.append(PanelRow("info", "Preview", value=preview))
        elif tab == TAB_PRESETS:
            for name in PRESETS:
                rows.append(PanelRow(
                    "action", name, action="preset", data=name,
                    value="active" if settings.preset == name else "apply",
                ))
            rows.append(PanelRow("info", "Current", value=settings.preset))
            rows.append(PanelRow("action", "Save settings", action="save"))
            rows.append(PanelRow("action", "Load settings", action="load"))
            rows.append(PanelRow("action", "Restore defaults", action="defaults"))
        return rows

    def current(self, settings: Settings) -> Optional[PanelRow]:
        rows = self.rows(settings)
        if not rows:
            return None
        index = max(0, min(len(rows) - 1, self.selected.get(self.tab, 0)))
        self.selected[self.tab] = index
        return rows[index]

    def move(self, delta: int, settings: Settings) -> None:
        rows = self.rows(settings)
        if not rows:
            return
        index = self.selected.get(self.tab, 0) + delta
        self.selected[self.tab] = max(0, min(len(rows) - 1, index))

    def adjust(self, settings: Settings, delta: int, coarse: bool = False) -> Optional[str]:
        row = self.current(settings)
        if row is None or delta == 0:
            return None
        if row.kind == "count":
            variety_id = row.field[:-len("_count")]
            current = settings.count(variety_id)
            step = 5 if coarse else 1
            target = max(0, min(MAX_FLOWERS, current + delta * step))
            if target > current:
                room = MAX_FLOWERS - settings.total_flowers()
                target = min(target, current + max(0, room))
                if target == current:
                    return "total"
            elif target == 0 and settings.total_flowers() <= 1:
                return "empty"
            settings.set_count(variety_id, target)
            return row.field
        if row.kind == "colorway":
            spec = get_variety(row.field)
            value = settings.colorway(row.field)
            value += delta
            if value < -1:
                value = len(spec.colorways) - 1
            elif value >= len(spec.colorways):
                value = -1
            settings.colorways[row.field] = value
            return "colorway:" + row.field
        if row.kind == "paused":
            settings.paused = not settings.paused
            return "paused"
        if row.kind == "field":
            meta = FIELD_META[row.field]
            value = getattr(settings, row.field)
            if meta.kind == "bool":
                setattr(settings, row.field, not value)
            elif meta.kind == "choice":
                options = meta.choices
                if options:
                    index = options.index(value) if value in options else 0
                    setattr(settings, row.field, options[(index + delta) % len(options)])
            elif meta.kind in ("int", "float"):
                step = meta.coarse if coarse else meta.step
                target = value + delta * step
                target = max(meta.minimum, min(meta.maximum, target))
                if meta.kind == "int":
                    target = int(round(target))
                else:
                    target = round(target, 4)
                setattr(settings, row.field, target)
            else:
                return None
            return row.field
        return None

    def activate(self, app) -> None:
        row = self.current(app.settings)
        if row is None:
            return
        if row.kind == "paused":
            self.adjust(app.settings, 1)
            app.on_settings_changed(["paused"])
            return
        if row.kind == "field" and row.field == "message":
            app.open_editor()
            return
        if row.kind == "action":
            app.panel_action(row.action, row.data)
            return
        if row.kind == "field" and FIELD_META[row.field].kind == "bool":
            self.adjust(app.settings, 1)
            app.on_settings_changed([row.field])
        elif row.kind == "field" and FIELD_META[row.field].kind == "choice":
            self.adjust(app.settings, 1)
            app.on_settings_changed([row.field])

    def _row_hint(self, row: PanelRow, settings: Settings, app) -> str:
        if row.field == "detail":
            term_rows = app.actual_size[1]
            eff_d = app.active_detail()
            eff_s = effective_style(settings.style, ascii_mode=app.ascii_mode, color_enabled=app.color)
            shown = effective_resolution(eff_d, term_rows, eff_s)
            if settings.detail == "auto":
                hint = "Auto->%dx (shows ~%d at this size)" % (eff_d, shown)
            else:
                hint = "%dx (shows ~%d at this size)" % (eff_d, shown)
            if not HAS_NUMPY and eff_d >= 128:
                hint += " [slow: no NumPy]"
            return hint
        if row.field in FIELD_META and FIELD_META[row.field].hint:
            return FIELD_META[row.field].hint
        if row.kind == "info" and row.label == "Total":
            return "Recommended <= %d at this size" % app.recommended_count()
        return ""

    # -- rendering ---------------------------------------------------------
    def draw(self, buffer: CellBuffer, settings: Settings, app, rect: Rect,
             ascii_mode: bool = False) -> None:
        x, y, width, height = rect
        draw_box(buffer, x, y, width, height, "Settings")
        inner = max(0, width - 4)
        if inner <= 0 or height < 4:
            return
        labels = []
        for index, tab in enumerate(TABS):
            labels.append("[%s]" % tab if index == self.tab_index else " %s " % tab)
        tab_line = " ".join(labels)
        if display_width(tab_line) > inner:
            tab_line = "< [%s] >  %d/%d" % (self.tab, self.tab_index + 1, len(TABS))
        buffer.put_text(y + 1, x + 2, fit(tab_line, inner), 205, max_width=inner)
        buffer.put_text(y + 2, x + 2, "-" * inner, 238, max_width=inner)

        rows = self.rows(settings)
        selected = max(0, min(len(rows) - 1, self.selected.get(self.tab, 0)))
        self.selected[self.tab] = selected
        reserve_bottom = 3 if height >= 8 else (2 if height >= 6 else 1)
        visible = max(1, height - 3 - reserve_bottom)
        offset = max(0, min(len(rows) - visible, selected - visible // 2))
        for line, index in enumerate(range(offset, min(len(rows), offset + visible))):
            row = rows[index]
            row_y = y + 3 + line
            is_selected = index == selected
            prefix = "> " if is_selected else "  "
            value = self._value(row, settings, app)
            if ascii_mode:
                value = ascii_text(value)
            value_width = min(inner // 2, max(4, display_width(value)))
            label_width = max(1, inner - value_width - 3)
            label = truncate(row.label, label_width)
            label_color = 231 if is_selected else 244
            value_color = 205 if is_selected else 231
            buffer.put_text(row_y, x + 2, prefix + fit(label, label_width), label_color,
                            max_width=inner)
            value_text = truncate(value, value_width)
            buffer.put_text(row_y, x + 2 + inner - display_width(value_text),
                            value_text, value_color, max_width=value_width)

        if height >= 8:
            row_hint = self._row_hint(rows[selected], settings, app)
            if row_hint:
                if ascii_mode:
                    row_hint = ascii_text(row_hint)
                buffer.put_text(y + height - 3, x + 2, fit(truncate(row_hint, inner), inner),
                                214 if "slow" in row_hint else 244, max_width=inner)

        if height >= 6:
            hint = ("Up/Down select  Left/Right adjust  [ ]/1-6 tab  Tab close" if ascii_mode
                    else "\u2191\u2193 select  \u2190\u2192 adjust  [ ]/1-6 tab  Tab close")
            if display_width(hint) > inner:
                hint = ("Up/Down  [ ]/1-6 tabs  Tab close" if ascii_mode
                        else "\u2191\u2193  [ ]/1-6 tabs  Tab close")
            if offset:
                hint = "^ " + hint
            if offset + visible < len(rows):
                hint += " v"
            buffer.put_text(y + height - 2, x + 2, fit(hint, inner), 238, max_width=inner)

    def _value(self, row: PanelRow, settings: Settings, app) -> str:
        if row.kind == "count":
            return "%d" % row.value if row.value else "0"
        if row.kind == "colorway":
            if row.value is None or row.value < 0:
                return "Mixed"
            spec = get_variety(row.field)
            return spec.colorways[row.value % len(spec.colorways)].name
        if row.kind == "paused":
            return "On" if settings.paused else "Off"
        if row.kind == "info":
            return str(row.value)
        if row.kind == "action":
            return str(row.value or "Enter")
        if row.kind == "field":
            meta = FIELD_META[row.field]
            value = getattr(settings, row.field)
            if row.field == "detail":
                eff_d = app.active_detail()
                eff_s = effective_style(settings.style, ascii_mode=app.ascii_mode, color_enabled=app.color)
                shown = effective_resolution(eff_d, app.actual_size[1], eff_s)
                if value == "auto":
                    return "Auto->%dx (~%d)" % (eff_d, shown)
                return "%sx (~%d)" % (value, shown)
            if meta.kind == "bool":
                return "On" if value else "Off"
            if meta.kind == "choice":
                return str(value)
            if meta.kind == "float":
                decimals = 2 if meta.step < 0.1 else 1
                return ("%." + str(decimals) + "f") % value
            if meta.kind == "text":
                return truncate(str(value) or "(empty)", 16)
            return str(value)
        return ""


def _varieties():
    from ..flowers import all_varieties

    return [(spec.id, spec) for spec in all_varieties()]
