#!/usr/bin/env python3

"""Тесты для reports/act_canvas_builder.py::ActCanvasEditor — свободный
(canvas) макет акта в классическом GUI.

Использует РЕАЛЬНЫЙ (но скрытый, withdraw()) Tk/customtkinter root, а не
стабы — виджет создаёт настоящий tkinter.Canvas и настоящие customtkinter
контролы, так что только конструирование объекта уже покрывает реальный
Tk-API. НО: на CI-раннере ubuntu-latest (.github/workflows/build.yml, job
test) нет X-дисплея, и tk.Tk() падает с TclError — тот же класс проблемы,
что уже ловили на os.rename-пробнике блокировки файла в
tests/test_print_utils.py. Поэтому весь модуль пропускается, если Tk
поднять не удалось, вместо жёсткого skipif на платформу (это ещё надёжнее:
Windows CI-раннер с недоступным дисплеем — тоже "нет Tk", а не "не Windows")."""

from __future__ import annotations

import types

import pytest

pytest.importorskip("customtkinter")

from reports.act_canvas_builder import ActCanvasEditor

# tk_root fixture — см. tests/conftest.py (общая для всех classic-GUI
# виджет-тестов: реальный, но скрытый Tk root, с ретраями и skip, если
# X-дисплей недоступен).

_COLORS = {
    "accent": "#0078d4",
    "bg_secondary": "#ffffff",
    "bg_tertiary": "#ececef",
    "text_primary": "#1d1d1f",
    "text_secondary": "#6e6e73",
    "border": "#d2d2d7",
    "error": "#ff3b30",
}


def _event(x, y):
    return types.SimpleNamespace(x=x, y=y)


class TestActCanvasEditorBasics:
    def test_starts_empty_with_all_fields_in_palette(self, tk_root):
        editor = ActCanvasEditor(tk_root, _COLORS, "receipt", {}, on_change=lambda: None)
        assert editor.get_canvas_fields() == {}

    def test_loads_existing_canvas_fields_on_construction(self, tk_root):
        initial = {"client_name": {"x_mm": 10.0, "y_mm": 20.0, "w_mm": 80.0}}
        editor = ActCanvasEditor(
            tk_root, _COLORS, "receipt", initial, on_change=lambda: None
        )
        assert editor.get_canvas_fields() == initial

    def test_add_field_places_it_and_removes_it_from_palette(self, tk_root):
        calls = []
        editor = ActCanvasEditor(
            tk_root, _COLORS, "receipt", {}, on_change=lambda: calls.append(1)
        )
        editor._add_field("client_name")
        fields = editor.get_canvas_fields()
        assert "client_name" in fields
        assert fields["client_name"]["x_mm"] >= 0
        assert calls, "on_change должен сработать при добавлении поля"

    def test_composite_field_only_offered_for_matching_act_type(self, tk_root):
        """works_table — только для completion, defect_box — только для receipt."""
        receipt_editor = ActCanvasEditor(
            tk_root, _COLORS, "receipt", {}, on_change=lambda: None
        )
        from reports.act_canvas_builder import _palette_keys

        assert "defect_box" in _palette_keys("receipt")
        assert "works_table" not in _palette_keys("receipt")
        assert "works_table" in _palette_keys("completion")
        assert "defect_box" not in _palette_keys("completion")
        receipt_editor.destroy()


class TestActCanvasEditorDragAndResize:
    def test_move_drag_updates_position_within_page_bounds(self, tk_root):
        editor = ActCanvasEditor(
            tk_root,
            _COLORS,
            "receipt",
            {"client_name": {"x_mm": 10.0, "y_mm": 10.0, "w_mm": 60.0}},
            on_change=lambda: None,
        )
        from reports.act_canvas_builder import PX_PER_MM

        start_x = int(10.0 * PX_PER_MM) + 5
        start_y = int(10.0 * PX_PER_MM) + 5
        editor._on_press(_event(start_x, start_y))
        assert editor._drag is not None
        assert editor._drag["mode"] == "move"
        editor._on_drag(_event(start_x + int(20 * PX_PER_MM), start_y + int(5 * PX_PER_MM)))
        editor._on_release(_event(0, 0))

        cfg = editor.get_canvas_fields()["client_name"]
        assert cfg["x_mm"] == pytest.approx(30.0, abs=1.0)
        assert cfg["y_mm"] == pytest.approx(15.0, abs=1.0)

    def test_move_drag_is_clamped_to_page_bounds(self, tk_root):
        """Перетаскивание далеко за левый/верхний край не должно уводить
        поле в отрицательные координаты (обрезание за пределы страницы —
        баг, который легко допустить без явного clamp)."""
        editor = ActCanvasEditor(
            tk_root,
            _COLORS,
            "receipt",
            {"client_name": {"x_mm": 10.0, "y_mm": 10.0, "w_mm": 60.0}},
            on_change=lambda: None,
        )
        from reports.act_canvas_builder import PX_PER_MM

        start_x = int(10.0 * PX_PER_MM) + 5
        start_y = int(10.0 * PX_PER_MM) + 5
        editor._on_press(_event(start_x, start_y))
        editor._on_drag(_event(start_x - 10_000, start_y - 10_000))
        editor._on_release(_event(0, 0))

        cfg = editor.get_canvas_fields()["client_name"]
        assert cfg["x_mm"] == 0.0
        assert cfg["y_mm"] == 0.0

    def test_resize_drag_changes_width_not_position(self, tk_root):
        editor = ActCanvasEditor(
            tk_root,
            _COLORS,
            "receipt",
            {"client_name": {"x_mm": 10.0, "y_mm": 10.0, "w_mm": 60.0}},
            on_change=lambda: None,
        )
        from reports.act_canvas_builder import PX_PER_MM, SIMPLE_FIELD_HEIGHT_MM

        x1 = int((10.0 + 60.0) * PX_PER_MM)
        y1 = int((10.0 + SIMPLE_FIELD_HEIGHT_MM) * PX_PER_MM)
        editor._on_press(_event(x1 - 2, y1 - 2))
        assert editor._drag["mode"] == "resize"
        editor._on_drag(_event(x1 - 2 + int(20 * PX_PER_MM), y1 - 2))
        editor._on_release(_event(0, 0))

        cfg = editor.get_canvas_fields()["client_name"]
        assert cfg["w_mm"] == pytest.approx(80.0, abs=1.0)
        assert cfg["x_mm"] == 10.0

    def test_resize_never_goes_below_minimum_width(self, tk_root):
        editor = ActCanvasEditor(
            tk_root,
            _COLORS,
            "receipt",
            {"client_name": {"x_mm": 10.0, "y_mm": 10.0, "w_mm": 60.0}},
            on_change=lambda: None,
        )
        from reports.act_canvas_builder import (
            MIN_WIDTH_MM,
            PX_PER_MM,
            SIMPLE_FIELD_HEIGHT_MM,
        )

        x1 = int((10.0 + 60.0) * PX_PER_MM)
        y1 = int((10.0 + SIMPLE_FIELD_HEIGHT_MM) * PX_PER_MM)
        editor._on_press(_event(x1 - 2, y1 - 2))
        editor._on_drag(_event(x1 - 2 - 10_000, y1 - 2))
        editor._on_release(_event(0, 0))

        cfg = editor.get_canvas_fields()["client_name"]
        assert cfg["w_mm"] == MIN_WIDTH_MM


class TestActCanvasEditorSelectionAndRemoval:
    def test_click_selects_field_and_shows_its_properties(self, tk_root):
        editor = ActCanvasEditor(
            tk_root,
            _COLORS,
            "receipt",
            {"client_name": {"x_mm": 10.0, "y_mm": 10.0, "w_mm": 60.0}},
            on_change=lambda: None,
        )
        from reports.act_canvas_builder import PX_PER_MM

        editor._on_press(_event(int(15 * PX_PER_MM), int(12 * PX_PER_MM)))
        editor._on_release(_event(0, 0))
        assert editor.selected_key == "client_name"

    def test_remove_selected_returns_field_to_palette(self, tk_root):
        editor = ActCanvasEditor(
            tk_root,
            _COLORS,
            "receipt",
            {"client_name": {"x_mm": 10.0, "y_mm": 10.0, "w_mm": 60.0}},
            on_change=lambda: None,
        )
        editor._select("client_name")
        editor._remove_selected()
        assert "client_name" not in editor.get_canvas_fields()

    def test_load_canvas_fields_replaces_state_and_notifies(self, tk_root):
        calls = []
        editor = ActCanvasEditor(
            tk_root,
            _COLORS,
            "receipt",
            {"client_name": {"x_mm": 10.0, "y_mm": 10.0, "w_mm": 60.0}},
            on_change=lambda: calls.append(1),
        )
        new_layout = {"phone": {"x_mm": 5.0, "y_mm": 5.0, "w_mm": 50.0}}
        editor.load_canvas_fields(new_layout)
        assert editor.get_canvas_fields() == new_layout
        assert calls


class TestActCanvasEditorRendersRealPdf:
    """Сквозная проверка: то, что редактор возвращает через
    get_canvas_fields(), реально рендерится в PDF ActPDFGenerator'ом (не
    только "не падает на уровне виджета")."""

    def test_layout_from_editor_round_trips_through_pdf_generation(
        self, tk_root, tmp_path
    ):
        from reports.report_renderer import ActPDFGenerator

        editor = ActCanvasEditor(tk_root, _COLORS, "receipt", {}, on_change=lambda: None)
        editor._add_field("title")
        editor._add_field("client_name")
        editor._add_field("defect_box")

        template = {
            "layout_mode": "canvas",
            "header_text": "ПРОВЕРКА РЕДАКТОРА",
            "canvas_fields": editor.get_canvas_fields(),
        }
        gen = ActPDFGenerator(template_data=template)
        out = tmp_path / "from_editor.pdf"
        ok = gen.generate_receipt_pdf(
            str(out), {"client_name": "Петров П.П.", "defect": "Трещина на экране"}
        )
        assert ok
        assert out.exists()

        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(out))
        text = pdf[0].get_textpage().get_text_range()
        del pdf
        assert "ПРОВЕРКА РЕДАКТОРА" in text
        assert "Петров П.П." in text
        assert "Трещина на экране" in text
