#!/usr/bin/env python3

"""Тесты для reports/report_renderer.py — покрывает три бага, найденные
design-review workflow'ом и не имевшие до этого ни одного теста:

1. Шрифт для кириллицы регистрировался ТОЛЬКО по путям C:\\Windows\\Fonts\\...
   — на любом non-Windows CI-раннере (ubuntu-latest/macos-latest,
   .github/workflows/build.yml) ни один путь не существовал, и генерация
   молча откатывалась на core-Helvetica (кириллицу не поддерживает вообще).
2. _prepare_image() создавал новый temp PNG на КАЖДЫЙ вызов без очистки —
   утечка файлов при печати многих актов за время работы процесса.
3. generate_dual_pdf() для пары "приём + выполненные работы" рендерил ОБЕ
   половины из одного шаблона (шаблон акта приёма), теряя
   header_text/fields/warranty_text второго акта.
"""

from __future__ import annotations

import os

import pytest

from reports.report_renderer import (
    _FONT_TTF_MAP,
    ActPDFGenerator,
    _first_existing,
    _image_cache,
    _prepare_image,
    _register_act_font,
)


@pytest.fixture
def demo_device():
    return {
        "order_number": "1",
        "client_name": "Иван Иванов",
        "phone": "+79990000000",
        "device_type": "Ноутбук",
        "total_price": "1000",
    }


class TestFontRegistration:
    def test_every_known_font_family_resolves_to_a_registered_pair(self):
        """На этой (Windows) машине системные TTF реально существуют — но
        тест бьёт по каждой записи _FONT_TTF_MAP, а не только по дефолтной,
        чтобы поймать опечатку в любом из путей-кандидатов."""
        for family in _FONT_TTF_MAP:
            reg, bold = _register_act_font(family)
            assert reg, f"{family}: пустое имя шрифта"
            assert bold, f"{family}: пустое имя bold-шрифта"

    def test_unknown_font_family_falls_back_without_crashing(self):
        reg, bold = _register_act_font("Какой-то Несуществующий Шрифт")
        assert reg
        assert bold

    def test_no_candidate_path_exists_falls_back_to_helvetica_not_a_crash(self, monkeypatch):
        """Симулирует non-Windows CI-раннер: НИ ОДИН путь-кандидат (ни
        Windows, ни Linux/macOS) не существует. Раньше на Windows это было
        недостижимо (C:\\Windows\\Fonts всегда есть), поэтому баг ни разу не
        всплывал локально — только на реальном ubuntu-latest/macos-latest.

        Также патчит getRegisteredFontNames() на пустой список — reportlab
        хранит зарегистрированные шрифты в общем процесс-глобальном реестре,
        а предыдущий тест в этом же файле уже успел зарегистрировать
        TrebuchetMS по реальному Windows-пути; без этого патча
        _register_act_font() увидел бы шрифт "уже зарегистрированным" и
        вернулся бы раньше, чем дошёл бы до проверки путей-кандидатов."""
        from reportlab.pdfbase import pdfmetrics

        monkeypatch.setattr(pdfmetrics, "getRegisteredFontNames", lambda: [])
        monkeypatch.setattr(os.path, "exists", lambda _p: False)
        reg, bold = _register_act_font("Trebuchet MS")
        assert reg == "Helvetica"
        assert bold == "Helvetica-Bold"

    def test_first_existing_returns_first_match_not_last(self, tmp_path):
        real_file = tmp_path / "real.ttf"
        real_file.write_bytes(b"\x00")
        result = _first_existing((str(tmp_path / "missing.ttf"), str(real_file)))
        assert result == str(real_file)

    def test_first_existing_returns_none_when_nothing_exists(self):
        assert _first_existing(("/no/such/path/a.ttf", "/no/such/path/b.ttf")) is None


class TestImageCacheNoLeak:
    def test_repeated_calls_with_same_path_reuse_the_same_temp_file(self, tmp_path):
        from PIL import Image

        src = tmp_path / "logo.png"
        Image.new("RGB", (4, 4)).save(src)

        try:
            first = _prepare_image(str(src))
            second = _prepare_image(str(src))
            assert first is not None
            assert first == second, "повторный вызов создал ВТОРОЙ temp-файл вместо переиспользования"
            assert os.path.exists(first)
        finally:
            _image_cache.pop(str(src), None)
            if first and os.path.exists(first):
                os.remove(first)

    def test_changed_source_invalidates_cache_and_removes_old_temp_file(self, tmp_path):
        import time

        from PIL import Image

        src = tmp_path / "logo.png"
        Image.new("RGB", (4, 4), color=(255, 0, 0)).save(src)
        first = _prepare_image(str(src))
        assert first is not None

        time.sleep(0.05)
        Image.new("RGB", (4, 4), color=(0, 255, 0)).save(src)
        os.utime(src, None)  # гарантирует другой mtime на грубых ФС

        try:
            second = _prepare_image(str(src))
            assert second is not None
            assert not os.path.exists(first), "старый temp PNG не удалён после инвалидации кэша"
        finally:
            _image_cache.pop(str(src), None)
            if second and os.path.exists(second):
                os.remove(second)

    def test_missing_source_returns_none_and_touches_no_cache(self):
        assert _prepare_image("/no/such/file.png") is None
        assert "/no/such/file.png" not in _image_cache


class TestDualPdfDifferentTemplates:
    def test_receipt_and_completion_use_their_own_templates(self, demo_device, tmp_path):
        receipt_tpl = {
            "name": "Test",
            "header_text": "АКТ ПРИЁМА ЗАГОЛОВОК",
            "fields": ["order_number"],
        }
        completion_tpl = {
            "name": "Test",
            "header_text": "АКТ РАБОТ ЗАГОЛОВОК",
            "fields": ["order_number"],
            "warranty_text": "Гарантия 30 дней на работы",
        }
        gen = ActPDFGenerator(template_data=receipt_tpl)
        out = tmp_path / "dual.pdf"
        ok = gen.generate_dual_pdf(
            str(out),
            demo_device,
            demo_device,
            act_type1="receipt",
            act_type2="completion",
            template_data2=completion_tpl,
        )
        assert ok
        assert out.exists()

        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(out))
        text = pdf[0].get_textpage().get_text_range()
        assert "АКТ ПРИЁМА ЗАГОЛОВОК" in text
        assert "АКТ РАБОТ ЗАГОЛОВОК" in text
        assert "Гарантия 30 дней на работы" in text

    def test_without_template_data2_both_halves_use_the_same_template(self, demo_device, tmp_path):
        """Обратная совместимость: act_type1 == act_type2 (2 одинаковых
        акта на листе) не обязан передавать template_data2."""
        tpl = {"name": "Test", "header_text": "ОДИН ШАБЛОН НА ОБА", "fields": ["order_number"]}
        gen = ActPDFGenerator(template_data=tpl)
        out = tmp_path / "dual_same.pdf"
        ok = gen.generate_dual_pdf(
            str(out), demo_device, demo_device, act_type1="receipt", act_type2="receipt"
        )
        assert ok
        assert out.exists()


class TestCanvasLayout:
    """Свободный макет (layout_mode='canvas') — билдер акта позволяет
    произвольно позиционировать поля/блоки на странице вместо
    фиксированного проточного порядка. Старые (flow) шаблоны без
    layout_mode должны продолжать рендериться как раньше — проверено
    остальными тестами этого файла (ни один не задаёт layout_mode)."""

    def test_canvas_mode_renders_fields_at_their_configured_content(
        self, demo_device, tmp_path
    ):
        tpl = {
            "layout_mode": "canvas",
            "header_text": "СВОБОДНЫЙ МАКЕТ",
            "canvas_fields": {
                "title": {"x_mm": 6, "y_mm": 6, "w_mm": 136},
                "client_name": {"x_mm": 6, "y_mm": 30, "w_mm": 136},
                "device_type": {
                    "x_mm": 6,
                    "y_mm": 45,
                    "w_mm": 60,
                    "bold": True,
                    "show_label": False,
                },
            },
        }
        gen = ActPDFGenerator(template_data=tpl)
        out = tmp_path / "canvas.pdf"
        ok = gen.generate_receipt_pdf(str(out), demo_device)
        assert ok
        assert out.exists()

        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(out))
        assert len(pdf) == 1
        text = pdf[0].get_textpage().get_text_range()
        del pdf
        assert "СВОБОДНЫЙ МАКЕТ" in text
        assert demo_device["client_name"] in text
        # show_label=False на device_type — само значение есть, а подписи
        # поля ("Тип устройства:") быть не должно.
        assert demo_device["device_type"] in text
        assert "Тип устройства" not in text

    def test_canvas_mode_skips_fields_with_empty_values(self, tmp_path):
        """Поле без значения в заказе просто не рисуется (а не падает и не
        оставляет пустую подпись «Гарантия:»)."""
        tpl = {
            "layout_mode": "canvas",
            "canvas_fields": {
                "warranty": {"x_mm": 6, "y_mm": 6, "w_mm": 100},
            },
        }
        gen = ActPDFGenerator(template_data=tpl)
        out = tmp_path / "canvas_empty.pdf"
        ok = gen.generate_receipt_pdf(str(out), {"order_number": "1"})
        assert ok
        assert out.exists()

    def test_canvas_mode_with_no_canvas_fields_falls_back_to_default_layout(
        self, demo_device, tmp_path
    ):
        """layout_mode='canvas' без сохранённых позиций (например, только
        что переключили режим) — не падает и не даёт пустой PDF, использует
        default_canvas_layout()."""
        tpl = {"layout_mode": "canvas", "header_text": "БЕЗ ПОЗИЦИЙ"}
        gen = ActPDFGenerator(template_data=tpl)
        out = tmp_path / "canvas_default.pdf"
        ok = gen.generate_receipt_pdf(str(out), demo_device)
        assert ok

        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(out))
        text = pdf[0].get_textpage().get_text_range()
        del pdf
        assert "БЕЗ ПОЗИЦИЙ" in text

    def test_default_canvas_layout_only_includes_relevant_composite_blocks(self):
        gen = ActPDFGenerator(template_data={})
        receipt_layout = gen.default_canvas_layout("receipt")
        completion_layout = gen.default_canvas_layout("completion")
        assert "defect_box" in receipt_layout
        assert "works_table" not in receipt_layout
        assert "works_table" in completion_layout
        assert "defect_box" not in completion_layout

    def test_dual_pdf_mixes_canvas_and_flow_templates(self, demo_device, tmp_path):
        """Один акт свободного макета + один проточный на одном листе A4 —
        оба генератора рисуются через общий путь без взаимной порчи."""
        canvas_tpl = {
            "layout_mode": "canvas",
            "canvas_fields": {
                "title": {"x_mm": 6, "y_mm": 6, "w_mm": 130},
                "client_name": {"x_mm": 6, "y_mm": 25, "w_mm": 130},
            },
            "header_text": "CANVAS ЗАГОЛОВОК",
        }
        flow_tpl = {
            "header_text": "FLOW ЗАГОЛОВОК",
            "fields": ["order_number"],
            "warranty_text": "Гарантия 14 дней",
        }
        gen = ActPDFGenerator(template_data=canvas_tpl)
        out = tmp_path / "dual_mixed.pdf"
        ok = gen.generate_dual_pdf(
            str(out),
            demo_device,
            demo_device,
            act_type1="receipt",
            act_type2="completion",
            template_data2=flow_tpl,
        )
        assert ok
        assert out.exists()

        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(out))
        assert len(pdf) == 1
        text = pdf[0].get_textpage().get_text_range()
        del pdf
        assert "CANVAS ЗАГОЛОВОК" in text
        assert "FLOW ЗАГОЛОВОК" in text
        assert "Гарантия 14 дней" in text

    def test_canvas_field_font_size_and_bold_are_applied(self, demo_device, tmp_path):
        """font_size/bold в конфиге поля не должны падать при построении
        Paragraph (регрессия на ParagraphStyle(parent=...) с fontSize)."""
        tpl = {
            "layout_mode": "canvas",
            "canvas_fields": {
                "client_name": {
                    "x_mm": 6,
                    "y_mm": 6,
                    "w_mm": 130,
                    "font_size": 14,
                    "bold": True,
                },
            },
        }
        gen = ActPDFGenerator(template_data=tpl)
        out = tmp_path / "canvas_style.pdf"
        ok = gen.generate_receipt_pdf(str(out), demo_device)
        assert ok
        assert out.exists()
