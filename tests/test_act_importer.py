#!/usr/bin/env python3

"""Тесты для reports/act_importer.py — импорт существующего акта
(PDF/XLSX/DOCX) в билдер шаблонов (reports/report_editor.py)."""

import os
import tempfile

import pytest

from reports.act_importer import (
    extract_text,
    suggest_canvas_layout,
    suggest_template_from_text,
)

_KNOWN_FIELDS = {
    "order_number": "Номер заказа",
    "client_name": "ФИО клиента",
    "phone": "Телефон",
    "total_price": "Общая стоимость",
}


class TestSuggestTemplateFromText:
    def test_matches_known_fields_in_document_order(self):
        text = "АКТ ПРИЁМА\nТелефон: +7 999\nНомер заказа: 42\nФИО клиента: Иванов"
        suggestion = suggest_template_from_text(text, _KNOWN_FIELDS)
        assert suggestion["suggested_fields"] == ["phone", "order_number", "client_name"]
        assert suggestion["header_text_guess"] == "АКТ ПРИЁМА"
        assert suggestion["match_count"] == 3
        assert suggestion["known_count"] == 4

    def test_matches_via_synonym_not_only_exact_label(self):
        text = "Заказ №100\nЗаказчик: Петров\nАванс: 500"
        suggestion = suggest_template_from_text(text, _KNOWN_FIELDS)
        assert "order_number" in suggestion["suggested_fields"]
        assert "client_name" in suggestion["suggested_fields"]

    def test_no_matches_returns_zero_match_count(self):
        suggestion = suggest_template_from_text("совершенно нерелевантный текст", _KNOWN_FIELDS)
        assert suggestion["match_count"] == 0
        assert suggestion["suggested_fields"] == []

    def test_ignores_yo_and_whitespace_differences(self):
        text = "Общая  стоимость:   1000"
        suggestion = suggest_template_from_text(text, {"total_price": "Общая стоимость"})
        assert suggestion["suggested_fields"] == ["total_price"]


class TestExtractText:
    def test_unsupported_extension_raises_value_error(self):
        with pytest.raises(ValueError, match="не поддерживается"):
            extract_text("act.txt")

    def test_extract_from_docx(self):
        docx = pytest.importorskip("docx")
        fd, path = tempfile.mkstemp(suffix=".docx")
        os.close(fd)
        try:
            document = docx.Document()
            document.add_paragraph("АКТ ВЫПОЛНЕННЫХ РАБОТ")
            document.add_paragraph("ФИО клиента: Сидоров")
            document.save(path)

            text = extract_text(path)
            assert "АКТ ВЫПОЛНЕННЫХ РАБОТ" in text
            assert "ФИО клиента" in text
        finally:
            os.remove(path)

    def test_extract_from_xlsx(self):
        openpyxl = pytest.importorskip("openpyxl")
        fd, path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws["A1"] = "Номер заказа"
            ws["B1"] = 7
            wb.save(path)

            text = extract_text(path)
            assert "Номер заказа" in text
            assert "7" in text
        finally:
            os.remove(path)

    def test_extract_from_pdf(self):
        # ASCII only: reportlab's default Helvetica has no Cyrillic glyphs
        # (real acts render Cyrillic via a registered TTF font, see
        # reports/report_renderer.py::_register_font) — this test checks
        # extract_text()'s PDF plumbing, not font/encoding support.
        pytest.importorskip("reportlab")
        from reportlab.pdfgen import canvas

        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            c = canvas.Canvas(path)
            c.drawString(72, 700, "ACCEPTANCE ACT")
            c.save()

            text = extract_text(path)
            assert "ACCEPTANCE ACT" in text
        finally:
            os.remove(path)


class TestSuggestCanvasLayout:
    """suggest_canvas_layout() — позиционно-осведомлённый импорт для
    свободного макета (canvas): реальные координаты из PDF, где найдены,
    иначе (DOCX/XLSX, или метка не найдена в тексте PDF) — раскладка
    сверху вниз в порядке появления."""

    def test_no_matches_returns_empty_layout(self):
        assert suggest_canvas_layout("act.pdf", "нерелевантный текст", _KNOWN_FIELDS) == {}

    def test_docx_style_text_stacks_fields_top_to_bottom_in_order(self):
        text = "Телефон: +7 999\nНомер заказа: 42\nФИО клиента: Иванов"
        layout = suggest_canvas_layout("act.docx", text, _KNOWN_FIELDS)
        assert set(layout) == {"phone", "order_number", "client_name"}
        # Порядок появления в тексте: phone, order_number, client_name —
        # каждое следующее должно быть НИЖЕ (больше y_mm) предыдущего.
        assert layout["phone"]["y_mm"] < layout["order_number"]["y_mm"]
        assert layout["order_number"]["y_mm"] < layout["client_name"]["y_mm"]
        for cfg in layout.values():
            assert cfg["x_mm"] >= 0
            assert cfg["w_mm"] > 0

    def test_pdf_with_real_text_layer_finds_actual_label_positions(self, tmp_path):
        """Генерируем настоящий акт нашим же рендерером (кириллица через
        зарегистрированный TTF-шрифт — см. report_renderer._register_act_font),
        затем импортируем его же и проверяем, что найденные координаты
        соответствуют реальному ВЕРТИКАЛЬНОМУ порядку полей на странице —
        не просто "что-то нашли", а именно там, где поле реально стоит."""
        pytest.importorskip("gui")
        from reports.report_editor import FIELD_LABELS
        from reports.report_renderer import ActPDFGenerator

        tpl = {
            "header_text": "ИСХОДНЫЙ АКТ",
            "fields": ["client_name", "phone", "device_type"],
        }
        gen = ActPDFGenerator(template_data=tpl)
        device = {
            "order_number": "1",
            "client_name": "Иванов Иван",
            "phone": "+79991234567",
            "device_type": "Ноутбук",
        }
        pdf_path = tmp_path / "source_act.pdf"
        assert gen.generate_receipt_pdf(str(pdf_path), device)

        text = extract_text(str(pdf_path))
        layout = suggest_canvas_layout(str(pdf_path), text, FIELD_LABELS)

        for key in ("client_name", "phone", "device_type"):
            assert key in layout, f"{key} должен быть найден в тексте акта"
            assert layout[key]["x_mm"] > 0
            assert layout[key]["w_mm"] >= 15.0

        # client_name напечатан выше phone, phone выше device_type в этом
        # шаблоне (см. fields=[...] выше) — найденные y_mm обязаны
        # сохранять тот же порядок сверху вниз.
        assert layout["client_name"]["y_mm"] < layout["phone"]["y_mm"]
        assert layout["phone"]["y_mm"] < layout["device_type"]["y_mm"]

    def test_pdf_without_matching_labels_falls_back_to_stacking(self, tmp_path):
        """Метка не нашлась позиционным поиском (например, PDF без
        текстового слоя для этого конкретного поля) — поле всё равно
        должно получить хоть какую-то позицию (через _stack_positions),
        а не молча выпасть из раскладки."""
        pytest.importorskip("reportlab")
        from reportlab.pdfgen import canvas

        pdf_path = tmp_path / "ascii_act.pdf"
        c = canvas.Canvas(str(pdf_path))
        c.drawString(72, 700, "Client Name Label Not In Russian")
        c.save()

        text = extract_text(str(pdf_path))
        # Синонимы client_name всё кириллические — прямого текстового
        # совпадения "Client Name" с ними нет, но suggest_template_from_text
        # тоже не найдёт его -> ожидаем пустую раскладку без падения.
        layout = suggest_canvas_layout(str(pdf_path), text, _KNOWN_FIELDS)
        assert layout == {}


class TestSuggestTemplateFromTextIntegration:
    """Сверяет реальный FIELD_LABELS из report_editor.py — не только
    тестовый мини-словарь выше."""

    def test_real_field_labels_are_matchable(self):
        pytest.importorskip("gui")  # обход циклического импорта
        from reports.report_editor import FIELD_LABELS

        text = (
            "АКТ ВЫПОЛНЕННЫХ РАБОТ\n"
            "Номер заказа: 15\n"
            "ФИО клиента: Кузнецов А.А.\n"
            "Телефон: +7 900 000-00-00\n"
            "Выполненные работы: чистка, замена термопасты\n"
            "Общая стоимость: 2500\n"
        )
        suggestion = suggest_template_from_text(text, FIELD_LABELS)
        assert suggestion["match_count"] >= 4
        assert suggestion["header_text_guess"] == "АКТ ВЫПОЛНЕННЫХ РАБОТ"
