#!/usr/bin/env python3

"""Свободный (canvas) макет акта — интерактивный конструктор, где поля и
составные блоки (шапка, таблица работ, подписи и т.д.) перетаскиваются
мышью в произвольное место страницы A5, а не идут фиксированным сверху-вниз
списком.

Хранит и возвращает данные в ТОМ ЖЕ формате, что читает
reports/report_renderer.py::ActPDFGenerator._draw_canvas_act() —
``{field_key: {"x_mm": .., "y_mm": .., "w_mm": .., "font_size"?: ..,
"bold"?: .., "show_label"?: ..}}`` — так что этот виджет не знает и не
обязан знать, как именно поле рисуется в PDF; он только позиционирует
прямоугольники-заглушки и передаёт координаты наружу.

Высота бокса на канвасе — ориентировочная (CANVAS_DEFAULT_HEIGHTS_MM),
реальная высота в PDF всегда пересчитывается из фактического содержимого.
"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import Any, Callable

import customtkinter as ctk

from reports.report_renderer import (
    CANVAS_COMPOSITE_FIELDS,
    CANVAS_DEFAULT_HEIGHTS_MM,
    CANVAS_SIMPLE_FIELDS,
    FIELD_LABELS,
)

logger = logging.getLogger(__name__)

# Страница A5 в мм и масштаб отображения (px/мм) — подобран, чтобы страница
# целиком помещалась в панель предпросмотра без прокрутки на обычном экране.
PAGE_W_MM = 148.0
PAGE_H_MM = 210.0
PX_PER_MM = 2.35
SIMPLE_FIELD_HEIGHT_MM = 8.0
MIN_WIDTH_MM = 15.0
HANDLE_PX = 8

# Сетка выравнивания — свободное позиционирование "в пиксель" удобно для
# точной подгонки, но неудобно для быстрой раскладки (пользовательский
# фидбек: "крутой, но слегка непривычный"). Координаты/ширина при
# перетаскивании округляются к ближайшей линии сетки — двигать и особенно
# выравнивать несколько полей друг под другом становится предсказуемо.
GRID_MM = 5.0


def _snap(value_mm: float, step_mm: float = GRID_MM) -> float:
    return round(value_mm / step_mm) * step_mm


def _label_for(key: str) -> str:
    if key in CANVAS_COMPOSITE_FIELDS:
        return CANVAS_COMPOSITE_FIELDS[key]["label"]
    return FIELD_LABELS.get(key, key)


def _palette_keys(act_type: str) -> list[str]:
    """Все ключи, которые вообще можно разместить на канвасе для этого типа
    акта, в разумном порядке показа в палитре (составные блоки сначала)."""
    composite = [
        k
        for k, meta in CANVAS_COMPOSITE_FIELDS.items()
        if act_type in meta["act_types"]
    ]
    return composite + list(CANVAS_SIMPLE_FIELDS)


class ActCanvasEditor(ctk.CTkFrame):
    """Палитра нерасставленных полей слева + канвас страницы A5 справа."""

    def __init__(
        self,
        parent,
        colors: dict[str, str],
        act_type: str,
        canvas_fields: dict[str, dict[str, Any]],
        on_change: Callable[[], None],
    ):
        super().__init__(parent, fg_color="transparent")
        self.colors = colors
        self.act_type = act_type
        self.on_change = on_change
        # Копия, а не ссылка — редактор владеет своим состоянием, наружу
        # отдаём снимок через get_canvas_fields().
        self.fields: dict[str, dict[str, Any]] = {
            k: dict(v) for k, v in (canvas_fields or {}).items()
        }
        self.selected_key: str | None = None
        self._drag: dict[str, Any] | None = None
        self._item_of_key: dict[str, tuple[int, int, int]] = {}  # key -> (rect, handle, text)

        self._build_ui()
        self._redraw_all()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        hint = ctk.CTkLabel(
            self,
            text="💡 Кликните поле в палитре, чтобы добавить на макет. "
            "Перетаскивайте за центр — двигать, за уголок ◢ — менять ширину.",
            font=ctk.CTkFont(size=10),
            text_color=self.colors["text_secondary"],
            justify="left",
            wraplength=520,
        )
        hint.pack(anchor="w", padx=4, pady=(0, 4))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        self.palette = ctk.CTkScrollableFrame(
            body, fg_color=self.colors["bg_secondary"], width=170, label_text="Поля"
        )
        self.palette.pack(side="left", fill="y", padx=(0, 6))

        canvas_wrap = ctk.CTkFrame(body, fg_color="transparent")
        canvas_wrap.pack(side="left", fill="both", expand=True)

        page_w_px = int(PAGE_W_MM * PX_PER_MM)
        page_h_px = int(PAGE_H_MM * PX_PER_MM)
        # Страница PDF всегда белая независимо от темы приложения — это её
        # реальный печатный вид, поэтому цвет здесь захардкожен, а не взят
        # из self.colors.
        self.canvas = tk.Canvas(
            canvas_wrap,
            width=page_w_px,
            height=page_h_px,
            bg="#FFFFFF",
            highlightthickness=1,
            highlightbackground=self.colors.get("border", "#888888"),
        )
        self.canvas.pack(padx=2, pady=2)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        self.props_bar = ctk.CTkFrame(canvas_wrap, fg_color="transparent")
        self.props_bar.pack(fill="x", pady=(6, 0))
        self._build_props_bar_placeholder()

        self._rebuild_palette()

    def _build_props_bar_placeholder(self):
        for w in self.props_bar.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.props_bar,
            text="Выберите поле на макете для настройки шрифта/подписи.",
            font=ctk.CTkFont(size=11),
            text_color=self.colors["text_secondary"],
        ).pack(anchor="w")

    def _rebuild_palette(self):
        for w in self.palette.winfo_children():
            w.destroy()
        placed = set(self.fields.keys())
        available = [k for k in _palette_keys(self.act_type) if k not in placed]
        if not available:
            ctk.CTkLabel(
                self.palette,
                text="Все поля уже\nна макете",
                font=ctk.CTkFont(size=11),
                text_color=self.colors["text_secondary"],
                justify="left",
            ).pack(anchor="w", padx=6, pady=6)
            return
        for key in available:
            btn = ctk.CTkButton(
                self.palette,
                text=f"+ {_label_for(key)}",
                anchor="w",
                fg_color=self.colors.get("bg_tertiary", "transparent"),
                text_color=self.colors["text_primary"],
                hover_color=self.colors["accent"],
                height=26,
                font=ctk.CTkFont(size=11),
                command=lambda k=key: self._add_field(k),
            )
            btn.pack(fill="x", padx=4, pady=2)

    # ------------------------------------------------------------------
    # Добавление / удаление полей
    # ------------------------------------------------------------------

    def _add_field(self, key: str):
        margin_mm = 6.0
        default_w = (
            PAGE_W_MM - 2 * margin_mm
            if key in CANVAS_COMPOSITE_FIELDS
            else min(80.0, PAGE_W_MM - 2 * margin_mm)
        )
        # Каскадом вниз от последнего добавленного, с переносом ближе к
        # низу страницы — чтобы новые поля не сыпались друг на друга.
        y = margin_mm
        if self.fields:
            y = max(v.get("y_mm", margin_mm) for v in self.fields.values()) + 12
        if y > PAGE_H_MM - 20:
            y = margin_mm
        self.fields[key] = {"x_mm": margin_mm, "y_mm": y, "w_mm": default_w}
        self._rebuild_palette()
        self._redraw_all()
        self._select(key)
        self.on_change()

    def _remove_selected(self):
        if self.selected_key and self.selected_key in self.fields:
            del self.fields[self.selected_key]
            self.selected_key = None
            self._rebuild_palette()
            self._redraw_all()
            self._build_props_bar_placeholder()
            self.on_change()

    # ------------------------------------------------------------------
    # Отрисовка
    # ------------------------------------------------------------------

    def _box_height_mm(self, key: str) -> float:
        return CANVAS_DEFAULT_HEIGHTS_MM.get(key, SIMPLE_FIELD_HEIGHT_MM)

    def _sample_text(self, key: str, cfg: dict[str, Any]) -> str:
        if key in CANVAS_COMPOSITE_FIELDS:
            return f"▤ {_label_for(key)}"
        label = FIELD_LABELS.get(key, key)
        show_label = cfg.get("show_label", True)
        return f"{label}: [значение]" if show_label else "[значение]"

    def _draw_grid(self):
        """Лёгкая сетка выравнивания (GRID_MM) под полями — только
        визуальный ориентир, сам snap считается независимо в _on_drag()."""
        page_w_px = PAGE_W_MM * PX_PER_MM
        page_h_px = PAGE_H_MM * PX_PER_MM
        n_cols = int(PAGE_W_MM / GRID_MM) + 1
        n_rows = int(PAGE_H_MM / GRID_MM) + 1
        for i in range(n_cols):
            x = i * GRID_MM * PX_PER_MM
            self.canvas.create_line(
                x, 0, x, page_h_px, fill="#EDEDED", tags="grid"
            )
        for j in range(n_rows):
            y = j * GRID_MM * PX_PER_MM
            self.canvas.create_line(
                0, y, page_w_px, y, fill="#EDEDED", tags="grid"
            )

    def _redraw_all(self):
        self.canvas.delete("all")
        self._item_of_key.clear()
        self._draw_grid()
        for key, cfg in self.fields.items():
            self._draw_field(key, cfg)
        if self.selected_key and self.selected_key not in self.fields:
            self.selected_key = None

    def _draw_field(self, key: str, cfg: dict[str, Any]):
        x0 = cfg.get("x_mm", 6.0) * PX_PER_MM
        y0 = cfg.get("y_mm", 6.0) * PX_PER_MM
        w = cfg.get("w_mm", 60.0) * PX_PER_MM
        h = self._box_height_mm(key) * PX_PER_MM
        x1, y1 = x0 + w, y0 + h

        selected = key == self.selected_key
        outline = self.colors["accent"] if selected else self.colors.get(
            "text_secondary", "#666666"
        )
        is_composite = key in CANVAS_COMPOSITE_FIELDS
        fill = (
            self.colors.get("bg_tertiary", "#EAEAEA")
            if is_composite
            else "#F5F8FF"
        )

        rect = self.canvas.create_rectangle(
            x0,
            y0,
            x1,
            y1,
            outline=outline,
            width=2 if selected else 1,
            dash=() if is_composite else (4, 2),
            fill=fill,
            tags=(f"field:{key}", "body"),
        )
        text = self.canvas.create_text(
            x0 + 4,
            y0 + 3,
            anchor="nw",
            text=self._sample_text(key, cfg),
            font=("TkDefaultFont", int(cfg.get("font_size", 9))),
            fill="#222222",
            width=max(w - 8, 10),
            tags=(f"field:{key}", "body"),
        )
        handle = self.canvas.create_rectangle(
            x1 - HANDLE_PX,
            y1 - HANDLE_PX,
            x1,
            y1,
            fill=outline,
            outline="",
            tags=(f"field:{key}", "handle"),
        )
        self._item_of_key[key] = (rect, handle, text)

    def _redraw_field(self, key: str):
        for item_id in self._item_of_key.get(key, ()):
            self.canvas.delete(item_id)
        self._draw_field(key, self.fields[key])

    # ------------------------------------------------------------------
    # Drag/resize
    # ------------------------------------------------------------------

    def _key_at(self, x: int, y: int) -> tuple[str | None, bool]:
        """Возвращает (ключ_поля, is_handle) под координатой, либо (None, False)."""
        item = self.canvas.find_closest(x, y)
        if not item:
            return None, False
        tags = self.canvas.gettags(item[0])
        key = next((t.split(":", 1)[1] for t in tags if t.startswith("field:")), None)
        if key is None:
            return None, False
        # find_closest всегда что-то находит, даже далеко от курсора —
        # отбрасываем промах мимо реального бокса.
        bbox = self.canvas.bbox(item[0])
        if bbox and not (bbox[0] - 4 <= x <= bbox[2] + 4 and bbox[1] - 4 <= y <= bbox[3] + 4):
            return None, False
        return key, "handle" in tags

    def _select(self, key: str | None):
        prev = self.selected_key
        self.selected_key = key
        if prev and prev in self.fields:
            self._redraw_field(prev)
        if key:
            self._redraw_field(key)
            self._build_props_bar(key)
        else:
            self._build_props_bar_placeholder()

    def _on_press(self, event):
        key, is_handle = self._key_at(event.x, event.y)
        if key is None:
            self._select(None)
            return
        self._select(key)
        cfg = self.fields[key]
        self._drag = {
            "key": key,
            "mode": "resize" if is_handle else "move",
            "start_x": event.x,
            "start_y": event.y,
            "orig_x_mm": cfg.get("x_mm", 0.0),
            "orig_y_mm": cfg.get("y_mm", 0.0),
            "orig_w_mm": cfg.get("w_mm", 60.0),
        }

    def _on_drag(self, event):
        if not self._drag:
            return
        key = self._drag["key"]
        cfg = self.fields.get(key)
        if cfg is None:
            return
        dx_mm = (event.x - self._drag["start_x"]) / PX_PER_MM
        dy_mm = (event.y - self._drag["start_y"]) / PX_PER_MM
        if self._drag["mode"] == "move":
            new_x = _snap(self._drag["orig_x_mm"] + dx_mm)
            new_y = _snap(self._drag["orig_y_mm"] + dy_mm)
            w = cfg.get("w_mm", 60.0)
            h = self._box_height_mm(key)
            cfg["x_mm"] = max(0.0, min(new_x, PAGE_W_MM - w))
            cfg["y_mm"] = max(0.0, min(new_y, PAGE_H_MM - h))
        else:
            new_w = _snap(self._drag["orig_w_mm"] + dx_mm)
            max_w = PAGE_W_MM - cfg.get("x_mm", 0.0)
            cfg["w_mm"] = max(MIN_WIDTH_MM, min(new_w, max_w))
        self._redraw_field(key)

    def _on_release(self, _event):
        if self._drag:
            self._drag = None
            self.on_change()

    # ------------------------------------------------------------------
    # Панель свойств выбранного поля
    # ------------------------------------------------------------------

    def _build_props_bar(self, key: str):
        for w in self.props_bar.winfo_children():
            w.destroy()
        cfg = self.fields[key]
        is_composite = key in CANVAS_COMPOSITE_FIELDS

        row = ctk.CTkFrame(self.props_bar, fg_color="transparent")
        row.pack(fill="x")

        ctk.CTkLabel(
            row,
            text=_label_for(key),
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left", padx=(0, 10))

        if not is_composite:
            show_label_var = ctk.BooleanVar(value=cfg.get("show_label", True))

            def _on_show_label():
                cfg["show_label"] = show_label_var.get()
                self._redraw_field(key)
                self.on_change()

            ctk.CTkCheckBox(
                row,
                text="Подпись поля",
                variable=show_label_var,
                fg_color=self.colors["accent"],
                command=_on_show_label,
            ).pack(side="left", padx=(0, 10))

            bold_var = ctk.BooleanVar(value=cfg.get("bold", False))

            def _on_bold():
                cfg["bold"] = bold_var.get()
                self.on_change()

            ctk.CTkCheckBox(
                row,
                text="Жирный",
                variable=bold_var,
                fg_color=self.colors["accent"],
                command=_on_bold,
            ).pack(side="left", padx=(0, 10))

            ctk.CTkLabel(row, text="Размер шрифта:", font=ctk.CTkFont(size=11)).pack(
                side="left", padx=(0, 4)
            )
            size_combo = ctk.CTkComboBox(
                row,
                values=["7", "8", "9", "10", "11", "12", "14", "16"],
                width=60,
                height=26,
                command=lambda v: self._on_font_size(key, v),
            )
            size_combo.set(str(int(cfg.get("font_size", 9))))
            size_combo.pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            row,
            text="✖ Убрать с макета",
            fg_color=self.colors.get("error", "#C0392B"),
            hover_color=self.colors.get("error", "#C0392B"),
            width=130,
            height=26,
            command=self._remove_selected,
        ).pack(side="right")

    def _on_font_size(self, key: str, value: str):
        try:
            self.fields[key]["font_size"] = int(value)
        except (TypeError, ValueError):
            return
        self._redraw_field(key)
        self.on_change()

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    def get_canvas_fields(self) -> dict[str, dict[str, Any]]:
        return {k: dict(v) for k, v in self.fields.items()}

    def load_canvas_fields(self, data: dict[str, dict[str, Any]]) -> None:
        """Заменяет текущую раскладку (используется импортом акта — см.
        reports/act_importer.py — чтобы разложить распознанные поля сразу
        по их найденным/приблизительным позициям)."""
        self.fields = {k: dict(v) for k, v in (data or {}).items()}
        self.selected_key = None
        self._rebuild_palette()
        self._redraw_all()
        self._build_props_bar_placeholder()
        self.on_change()
