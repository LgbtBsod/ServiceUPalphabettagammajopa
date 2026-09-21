"""Свободный (canvas) макет акта — Flet-эквивалент reports/act_canvas_builder.py.

Тот же формат данных (canvas_fields: {field_key: {x_mm, y_mm, w_mm, ...}}),
тот же генератор (reports/report_renderer.py::ActPDFGenerator) — шаблон,
сохранённый здесь, открывается и печатается и классическим интерфейсом, и
наоборот. В отличие от классического билдера, здесь НЕТ отдельного "режима
списка полей" — это осознанное упрощение: Flet-оболочка не претендует на
полный паритет со старым flow-списком (см. gui_flet/app.py docstring), а
canvas — единственный и более удобный способ разместить поля что в
десктопе, что в браузере.

Драг реализован через ft.GestureDetector.on_pan_start/on_pan_update/
on_pan_end поверх ft.Stack с абсолютным позиционированием (left/top) — в
этой версии Flet нет более высокоуровневого drag-to-reposition примитива
(ft.Draggable/DragTarget — это drag МЕЖДУ фиксированными зонами, не
свободное позиционирование). on_pan_update даёт global_delta — смещение
С НАЧАЛА жеста, а не с прошлого тика, поэтому позиция при движении
считается как start + delta, а не накоплением дельт (там легко накопить
ошибку округления по кадрам)."""

from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import sys
import tempfile
from typing import Any

import flet as ft

from reports.act_importer import (
    SUPPORTED_EXTENSIONS,
    extract_text,
    suggest_canvas_layout,
    suggest_template_from_text,
)
from reports.report_editor import FIELD_LABELS, load_template_data, save_template_data
from reports.report_renderer import (
    CANVAS_COMPOSITE_FIELDS,
    CANVAS_DEFAULT_HEIGHTS_MM,
    CANVAS_SIMPLE_FIELDS,
    ActPDFGenerator,
)
from utils.messages import Msg

from . import theme
from .views_orders import _opt

logger = logging.getLogger(__name__)

PAGE_W_MM = 148.0
PAGE_H_MM = 210.0
PX_PER_MM = 2.6
SIMPLE_FIELD_HEIGHT_MM = 8.0
MIN_WIDTH_MM = 15.0
# Живое тестирование в браузере (drag на маленьком уголке между
# перекрывающимися боксами) показало, что 16px легко промахнуть — курсор
# попадает на body соседнего поля вместо ручки; 22px даёт запас.
HANDLE_PX = 22

# Сетка выравнивания — то же значение и та же идея, что и в classic-GUI
# билдере (reports/act_canvas_builder.py::GRID_MM): свободное позиционирование
# "в пиксель" удобно для точной подгонки, но неудобно для быстрой раскладки
# (пользовательский фидбек: "крутой, но слегка непривычный"). Координаты/
# ширина при перетаскивании округляются к ближайшей линии сетки.
GRID_MM = 5.0

_ACT_TYPES = [("receipt", "Акт приёма"), ("completion", "Акт выполненных работ")]

_DEMO_DEVICE = {
    "order_number": "00001",
    "receipt_date": "2026-01-01",
    "completion_date": "2026-01-05",
    "client_name": "Иванов Иван Иванович",
    "phone": "+7 (999) 123-45-67",
    "device_type": "Ноутбук",
    "brand": "Apple",
    "model": "MacBook Pro",
    "serial_number": "C02XK1234ABC",
    "completeness": "Полная комплектация",
    "appearance": "Отличное состояние",
    "defect": "Не включается, нет изображения на экране",
    "completed_work": "Замена дисплея, профилактика",
    "total_price": "8500",
    "prepayment": "2000",
    "warranty": "3 месяца",
    "engineer": "Иванов И.И.",
    "client_status": "Постоянный",
}


def _label_for(key: str) -> str:
    if key in CANVAS_COMPOSITE_FIELDS:
        return CANVAS_COMPOSITE_FIELDS[key]["label"]
    return FIELD_LABELS.get(key, key)


def _palette_keys(act_type: str) -> list[str]:
    composite = [
        k for k, meta in CANVAS_COMPOSITE_FIELDS.items() if act_type in meta["act_types"]
    ]
    return composite + list(CANVAS_SIMPLE_FIELDS)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(value, hi))


def _snap(value_mm: float, step_mm: float = GRID_MM) -> float:
    return round(value_mm / step_mm) * step_mm


class ActBuilderView:
    def __init__(self, app):
        self.app = app
        self.act_type = "receipt"
        self.templates: dict[str, dict[str, Any]] = {
            "receipt": load_template_data("receipt"),
            "completion": load_template_data("completion"),
        }
        self.selected_key: str | None = None
        self._drag: dict[str, Any] | None = None
        self._body_ctrls: dict[str, ft.GestureDetector] = {}
        self._handle_ctrls: dict[str, ft.GestureDetector] = {}

        self._file_picker = ft.FilePicker()
        self.app.page.services.append(self._file_picker)

    # ── данные ───────────────────────────────────────────────

    def _fields(self) -> dict[str, dict[str, Any]]:
        tpl = self.templates[self.act_type]
        fields = tpl.get("canvas_fields")
        if not fields:
            gen = ActPDFGenerator(template_data=tpl)
            fields = gen.default_canvas_layout(self.act_type)
            tpl["canvas_fields"] = fields
        return fields

    def _box_height_mm(self, key: str) -> float:
        return CANVAS_DEFAULT_HEIGHTS_MM.get(key, SIMPLE_FIELD_HEIGHT_MM)

    # ── публичный рендер ─────────────────────────────────────

    def render(self) -> ft.Control:
        c = self.app.colors
        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Свободный макет акта", size=24, weight=ft.FontWeight.BOLD,
                                 color=c["text_primary"]),
                        ft.Container(expand=True),
                        ft.OutlinedButton("📥 Импорт из файла", on_click=self._on_import_click),
                        ft.OutlinedButton("🔎 Точный PDF", on_click=self._on_exact_pdf_click),
                        ft.FilledButton("💾 Сохранить", on_click=self._on_save_click),
                    ],
                ),
                ft.Container(height=8),
                ft.SegmentedButton(
                    selected=[self.act_type],
                    segments=[ft.Segment(value=k, label=ft.Text(label)) for k, label in _ACT_TYPES],
                    on_change=self._on_act_type_change,
                ),
                ft.Container(height=10),
                ft.Row(
                    [
                        self._build_palette(),
                        ft.Container(width=12),
                        ft.Column([self._build_canvas(), self._build_props_bar()], spacing=10),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
            ],
            spacing=4,
            scroll=ft.ScrollMode.AUTO,
        )

    # ── палитра ──────────────────────────────────────────────

    def _build_palette(self) -> ft.Control:
        c = self.app.colors
        placed = set(self._fields().keys())
        available = [k for k in _palette_keys(self.act_type) if k not in placed]

        items = [
            ft.TextButton(
                content=ft.Text(f"+ {_label_for(k)}", size=12, color=c["text_primary"]),
                style=ft.ButtonStyle(alignment=ft.alignment.Alignment(-1, 0)),
                on_click=lambda _e, key=k: self._add_field(key),
            )
            for k in available
        ]
        if not items:
            items = [ft.Text("Все поля уже\nна макете", size=12, color=c["text_secondary"])]

        return ft.Container(
            ft.Column([ft.Text("Поля", weight=ft.FontWeight.BOLD, size=13,
                                color=c["text_primary"]), *items], spacing=2, tight=True),
            width=190, bgcolor=c["bg_card"], border_radius=10, padding=10,
            border=theme.card_border(c["border"]),
        )

    def _add_field(self, key: str) -> None:
        fields = self._fields()
        margin_mm = 6.0
        default_w = (
            PAGE_W_MM - 2 * margin_mm
            if key in CANVAS_COMPOSITE_FIELDS
            else min(80.0, PAGE_W_MM - 2 * margin_mm)
        )
        y = margin_mm
        if fields:
            y = max(v.get("y_mm", margin_mm) for v in fields.values()) + 12
        if y > PAGE_H_MM - 20:
            y = margin_mm
        fields[key] = {"x_mm": margin_mm, "y_mm": y, "w_mm": default_w}
        self.selected_key = key
        self.app.rerender()

    def _remove_selected(self, _e=None) -> None:
        fields = self._fields()
        if self.selected_key and self.selected_key in fields:
            del fields[self.selected_key]
            self.selected_key = None
            self.app.rerender()

    # ── канвас (страница A5 + перетаскиваемые боксы) ────────

    def _build_grid_lines(self) -> list[ft.Control]:
        """Лёгкая сетка выравнивания (GRID_MM) под полями — тонкие
        Container'ы вместо настоящих линий (в этой версии Flet нет
        ft.canvas), тот же приём, что и в classic-GUI билдере."""
        page_w_px = PAGE_W_MM * PX_PER_MM
        page_h_px = PAGE_H_MM * PX_PER_MM
        lines: list[ft.Control] = []
        n_cols = int(PAGE_W_MM / GRID_MM) + 1
        n_rows = int(PAGE_H_MM / GRID_MM) + 1
        for i in range(n_cols):
            x = i * GRID_MM * PX_PER_MM
            lines.append(ft.Container(left=x, top=0, width=1, height=page_h_px, bgcolor="#EDEDED"))
        for j in range(n_rows):
            y = j * GRID_MM * PX_PER_MM
            lines.append(ft.Container(left=0, top=y, width=page_w_px, height=1, bgcolor="#EDEDED"))
        return lines

    def _build_canvas(self) -> ft.Control:
        c = self.app.colors
        page_w_px = PAGE_W_MM * PX_PER_MM
        page_h_px = PAGE_H_MM * PX_PER_MM

        self._body_ctrls = {}
        self._handle_ctrls = {}
        controls: list[ft.Control] = [
            # Страница PDF всегда белая, независимо от темы приложения —
            # это её реальный печатный вид.
            ft.Container(width=page_w_px, height=page_h_px, bgcolor="#FFFFFF",
                         border=theme.card_border(c["border"])),
            *self._build_grid_lines(),
        ]
        for key, cfg in self._fields().items():
            body, handle = self._build_field_controls(key, cfg)
            self._body_ctrls[key] = body
            self._handle_ctrls[key] = handle
            controls.append(body)
            controls.append(handle)

        stack = ft.Stack(controls, width=page_w_px, height=page_h_px)
        return ft.Container(
            stack,
            bgcolor=c["bg_tertiary"], border_radius=8, padding=8,
        )

    def _sample_text(self, key: str, cfg: dict[str, Any]) -> str:
        if key in CANVAS_COMPOSITE_FIELDS:
            return f"▤ {_label_for(key)}"
        label = FIELD_LABELS.get(key, key)
        show_label = cfg.get("show_label", True)
        return f"{label}: [значение]" if show_label else "[значение]"

    def _build_field_controls(
        self, key: str, cfg: dict[str, Any]
    ) -> tuple[ft.GestureDetector, ft.GestureDetector]:
        left = cfg.get("x_mm", 6.0) * PX_PER_MM
        top = cfg.get("y_mm", 6.0) * PX_PER_MM
        w = cfg.get("w_mm", 60.0) * PX_PER_MM
        h = self._box_height_mm(key) * PX_PER_MM
        selected = key == self.selected_key
        is_composite = key in CANVAS_COMPOSITE_FIELDS
        accent = self.app.colors["accent"]

        body_box = ft.Container(
            ft.Text(self._sample_text(key, cfg), size=int(cfg.get("font_size", 11)),
                     color="#222222",
                     weight=ft.FontWeight.BOLD if cfg.get("bold") else ft.FontWeight.NORMAL),
            width=w, height=h, padding=4,
            bgcolor="#EAEAEA" if is_composite else "#F5F8FF",
            border=ft.Border(
                top=ft.BorderSide(2 if selected else 1, accent if selected else "#888888"),
                right=ft.BorderSide(2 if selected else 1, accent if selected else "#888888"),
                bottom=ft.BorderSide(2 if selected else 1, accent if selected else "#888888"),
                left=ft.BorderSide(2 if selected else 1, accent if selected else "#888888"),
            ),
        )
        body = ft.GestureDetector(
            content=body_box, left=left, top=top,
            on_tap=lambda _e, k=key: self._select(k),
            on_pan_start=lambda e, k=key: self._on_move_start(e, k),
            on_pan_update=lambda e, k=key: self._on_move_update(e, k),
            on_pan_end=lambda e, k=key: self._on_move_end(e, k),
        )

        handle_box = ft.Container(width=HANDLE_PX, height=HANDLE_PX, bgcolor=accent)
        handle = ft.GestureDetector(
            content=handle_box,
            left=left + w - HANDLE_PX, top=top + h - HANDLE_PX,
            on_pan_start=lambda e, k=key: self._on_resize_start(e, k),
            on_pan_update=lambda e, k=key: self._on_resize_update(e, k),
            on_pan_end=lambda e, k=key: self._on_resize_end(e, k),
        )
        return body, handle

    # ── drag: перемещение ────────────────────────────────────

    def _on_move_start(self, _e: ft.DragStartEvent, key: str) -> None:
        body = self._body_ctrls[key]
        self._drag = {"key": key, "mode": "move", "left": body.left, "top": body.top}
        self._select(key, rerender=False)

    def _on_move_update(self, e: ft.DragUpdateEvent, key: str) -> None:
        if not self._drag or self._drag["key"] != key or self._drag["mode"] != "move":
            return
        dx = e.global_delta.x if e.global_delta else 0
        dy = e.global_delta.y if e.global_delta else 0
        cfg = self._fields()[key]
        w = cfg.get("w_mm", 60.0) * PX_PER_MM
        h = self._box_height_mm(key) * PX_PER_MM
        page_w_px = PAGE_W_MM * PX_PER_MM
        page_h_px = PAGE_H_MM * PX_PER_MM
        # Снап к сетке уже во время перетаскивания (не только на отпускании) —
        # тот же live-фидбек, что и в classic-GUI билдере.
        snapped_left = _snap((self._drag["left"] + dx) / PX_PER_MM) * PX_PER_MM
        snapped_top = _snap((self._drag["top"] + dy) / PX_PER_MM) * PX_PER_MM
        new_left = _clamp(snapped_left, 0, page_w_px - w)
        new_top = _clamp(snapped_top, 0, page_h_px - h)
        body = self._body_ctrls[key]
        body.left, body.top = new_left, new_top
        handle = self._handle_ctrls[key]
        handle.left, handle.top = new_left + w - HANDLE_PX, new_top + h - HANDLE_PX
        self.app.page.update()

    def _on_move_end(self, _e: ft.DragEndEvent, key: str) -> None:
        if not self._drag or self._drag["key"] != key:
            return
        body = self._body_ctrls[key]
        cfg = self._fields()[key]
        cfg["x_mm"] = body.left / PX_PER_MM
        cfg["y_mm"] = body.top / PX_PER_MM
        self._drag = None
        # _on_move_start выбирает key через _select(key, rerender=False)
        # (полный rerender() посреди активного жеста мог бы сбить
        # распознаватель drag у GestureDetector), поэтому граница выделения
        # и панель свойств оставались показывать ПРЕЖНЕЕ выбранное поле всё
        # время перетаскивания. Теперь, когда жест завершён и пересборка
        # безопасна, досчитываем это здесь — иначе после драга поле B
        # становится selected_key "тихо", а на экране всё ещё подсвечено
        # поле A с его же панелью свойств, и клик "Убрать с макета" удаляет
        # не то, что видно (workflow-найденный баг).
        self.app.rerender()

    # ── drag: изменение ширины ───────────────────────────────

    def _on_resize_start(self, _e: ft.DragStartEvent, key: str) -> None:
        cfg = self._fields()[key]
        self._drag = {"key": key, "mode": "resize", "w_mm": cfg.get("w_mm", 60.0)}

    def _on_resize_update(self, e: ft.DragUpdateEvent, key: str) -> None:
        if not self._drag or self._drag["key"] != key or self._drag["mode"] != "resize":
            return
        dx = e.global_delta.x if e.global_delta else 0
        cfg = self._fields()[key]
        max_w_mm = PAGE_W_MM - cfg.get("x_mm", 0.0)
        raw_w_mm = self._drag["w_mm"] + dx / PX_PER_MM
        new_w_mm = _clamp(_snap(raw_w_mm), MIN_WIDTH_MM, max_w_mm)
        new_w_px = new_w_mm * PX_PER_MM
        body = self._body_ctrls[key]
        body.content.width = new_w_px
        body.width = new_w_px
        handle = self._handle_ctrls[key]
        handle.left = body.left + new_w_px - HANDLE_PX
        self._drag["_live_w_mm"] = new_w_mm
        self.app.page.update()

    def _on_resize_end(self, _e: ft.DragEndEvent, key: str) -> None:
        if not self._drag or self._drag["key"] != key:
            return
        live_w = self._drag.get("_live_w_mm")
        if live_w is not None:
            self._fields()[key]["w_mm"] = live_w
        self._drag = None

    # ── выбор / свойства ─────────────────────────────────────

    def _select(self, key: str | None, *, rerender: bool = True) -> None:
        self.selected_key = key
        if rerender:
            self.app.rerender()

    def _build_props_bar(self) -> ft.Control:
        c = self.app.colors
        key = self.selected_key
        fields = self._fields()
        if not key or key not in fields:
            return ft.Container(
                ft.Text("Выберите поле на макете для настройки шрифта/подписи.",
                         size=12, color=c["text_secondary"]),
                padding=8,
            )
        cfg = fields[key]
        is_composite = key in CANVAS_COMPOSITE_FIELDS
        row: list[ft.Control] = [
            ft.Text(_label_for(key), weight=ft.FontWeight.BOLD, size=13, color=c["text_primary"]),
        ]
        if not is_composite:
            row.append(ft.Checkbox(
                label="Подпись поля", value=cfg.get("show_label", True),
                on_change=lambda e, k=key: self._on_show_label_change(k, e.control.value),
            ))
            row.append(ft.Checkbox(
                label="Жирный", value=cfg.get("bold", False),
                on_change=lambda e, k=key: self._on_bold_change(k, e.control.value),
            ))
            row.append(ft.Text("Размер шрифта:", size=12, color=c["text_secondary"]))
            row.append(ft.Dropdown(
                value=str(int(cfg.get("font_size", 9))),
                options=[_opt(v) for v in ["7", "8", "9", "10", "11", "12", "14", "16"]],
                width=80, dense=True,
                on_select=lambda e, k=key: self._on_font_size_change(k, e.control.value),
            ))
        row.append(ft.OutlinedButton("✖ Убрать с макета", on_click=self._remove_selected))
        # Row БЕЗ wrap/expand: в этой версии Flet expand-дочерний элемент
        # внутри Row(wrap=True) рендерится как гигантский серый прямоугольник
        # (Wrap во Flutter не поддерживает Expanded-детей так же, как
        # обычный Row/Flex) — свойства короткие, помещаются на одну строку
        # со скроллом по горизонтали как fallback на узких экранах.
        return ft.Container(
            ft.Row(row, spacing=10, scroll=ft.ScrollMode.AUTO),
            padding=8, bgcolor=c["bg_card"], border_radius=8,
            border=theme.card_border(c["border"]),
        )

    def _on_show_label_change(self, key: str, value: bool) -> None:
        self._fields()[key]["show_label"] = value
        self.app.rerender()

    def _on_bold_change(self, key: str, value: bool) -> None:
        self._fields()[key]["bold"] = value
        self.app.rerender()

    def _on_font_size_change(self, key: str, value: str) -> None:
        with contextlib.suppress(TypeError, ValueError):
            self._fields()[key]["font_size"] = int(value)
        self.app.rerender()

    # ── акт (переключатель) ──────────────────────────────────

    def _on_act_type_change(self, e: ft.ControlEvent) -> None:
        selected = e.control.selected[0] if e.control.selected else "receipt"
        self.act_type = selected
        self.selected_key = None
        self.app.rerender()

    # ── сохранение ───────────────────────────────────────────

    def _on_save_click(self, _e=None) -> None:
        tpl = self.templates[self.act_type]
        tpl["layout_mode"] = "canvas"
        tpl["canvas_fields"] = self._fields()
        ok = save_template_data(self.act_type, tpl)
        self.app.show_snackbar(
            "Макет сохранён" if ok else "Не удалось сохранить макет", error=not ok
        )

    # ── точный PDF ───────────────────────────────────────────

    def _on_exact_pdf_click(self, _e=None) -> None:
        # Вся реальная работа — в async _run(), запущенном через
        # page.run_task() (тот же паттерн, что _on_import_click() ниже и
        # _print_act() в views_orders.py), генерация PDF/запуск системного
        # просмотрщика — через asyncio.to_thread() (оба блокирующие). Раньше
        # это выполнялось синхронно прямо в обработчике клика — точный
        # PDF-предпросмотр замораживал всю страницу этой браузерной сессии
        # на время генерации и запуска внешнего процесса (workflow-найденное
        # расхождение с _on_import_click(), который уже делает это правильно
        # в этом же файле).
        tpl = dict(self.templates[self.act_type])
        tpl["layout_mode"] = "canvas"
        tpl["canvas_fields"] = self._fields()

        async def _run() -> None:
            import asyncio

            try:
                gen = ActPDFGenerator(template_data=tpl)
                fd, path = tempfile.mkstemp(suffix=f"_{self.act_type}_preview.pdf")
                os.close(fd)

                def _generate() -> bool:
                    return (
                        gen.generate_completion_pdf(path, _DEMO_DEVICE)
                        if self.act_type == "completion"
                        else gen.generate_receipt_pdf(path, _DEMO_DEVICE)
                    )

                ok = await asyncio.to_thread(_generate)
                if not ok or not os.path.exists(path):
                    self.app.show_snackbar(Msg.Act.PREVIEW_GENERATE_FAILED, error=True)
                    return

                def _open_in_system_viewer() -> None:
                    # Flet-оболочка — локальный сервер + локальная вкладка
                    # браузера на той же машине (см. gui_flet/app.py
                    # docstring), поэтому открываем системным просмотрщиком,
                    # как и печать готового акта в _print_act()
                    # (views_orders.py) — тот же приём, тот же контекст.
                    if sys.platform == "win32":
                        os.startfile(path)
                    elif sys.platform == "darwin":
                        subprocess.run(["open", path], check=False)
                    else:
                        subprocess.run(["xdg-open", path], check=False)

                await asyncio.to_thread(_open_in_system_viewer)
                self.app.show_snackbar(Msg.Act.PREVIEW_OPENED)
            except Exception as e:
                logger.exception(Msg.Act.LOG_PREVIEW_FAILED.format(error=e))
                self.app.show_snackbar(Msg.Act.PREVIEW_FAILED.format(error=e), error=True)

        self.app.page.run_task(_run)

    # ── импорт из файла ──────────────────────────────────────

    def _on_import_click(self, _e=None) -> None:
        async def _run() -> None:
            # pick_files() — единственная точка отказа в этой корутине, не
            # покрытая try/except ниже (тот начинается только с чтения
            # picked.bytes). page.run_task() передаёт исключения таска только
            # в дефолтный (консольный) обработчик asyncio — никакой snackbar
            # пользователь не увидит. Реальные отказы: разрыв сессии,
            # таймаут (invoke_method ждёт до часа), отсутствие zenity на
            # Linux-десктопе. Без этого клик по кнопке "молча ничего не
            # делает" (workflow-найденный баг).
            try:
                files = await self._file_picker.pick_files(
                    dialog_title="Выберите файл акта",
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=[
                        ext.lstrip(".") for ext in sorted(SUPPORTED_EXTENSIONS)
                    ],
                    with_data=True,
                )
            except Exception as e:
                logger.exception(f"Ошибка выбора файла акта: {e}")
                self.app.show_snackbar(f"Не удалось открыть выбор файла: {e}", error=True)
                return
            if not files:
                return
            picked = files[0]
            if not picked.bytes:
                self.app.show_snackbar("Не удалось прочитать файл", error=True)
                return

            suffix = os.path.splitext(picked.name)[1] or ".pdf"
            fd, tmp_path = tempfile.mkstemp(suffix=suffix)
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(picked.bytes)

                text = extract_text(tmp_path)
                suggestion = suggest_template_from_text(text, FIELD_LABELS)
                if suggestion["match_count"] == 0:
                    self.app.show_snackbar(
                        "Не удалось распознать поля в этом файле "
                        "(возможно, это скан без текстового слоя)",
                        error=True,
                    )
                    return
                canvas_layout = suggest_canvas_layout(tmp_path, text, FIELD_LABELS)
            except ValueError as e:
                self.app.show_snackbar(str(e), error=True)
                return
            except Exception as e:
                logger.exception(f"Ошибка импорта акта: {e}")
                self.app.show_snackbar(f"Не удалось прочитать файл: {e}", error=True)
                return
            finally:
                with contextlib.suppress(OSError):
                    os.remove(tmp_path)

            tpl = self.templates[self.act_type]
            header_guess = suggestion.get("header_text_guess", "")
            if header_guess:
                tpl["header_text"] = header_guess
            tpl["layout_mode"] = "canvas"
            tpl["canvas_fields"] = canvas_layout or self._fields()
            self.selected_key = None
            self.app.show_snackbar(
                f"Распознано {suggestion['match_count']} из {suggestion['known_count']} "
                f"полей — проверьте макет и сохраните."
            )
            self.app.rerender()

        self.app.page.run_task(_run)
