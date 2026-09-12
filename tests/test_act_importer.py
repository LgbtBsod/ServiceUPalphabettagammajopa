#!/usr/bin/env python3

"""Тесты для reports/act_importer.py — импорт существующего акта
(PDF/XLSX/DOCX) в билдер шаблонов (reports/report_editor.py)."""

import os
import tempfile

import pytest

from reports.act_importer import extract_text, suggest_template_from_text

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
