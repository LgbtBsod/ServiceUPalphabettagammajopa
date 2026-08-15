#!/usr/bin/env python3

"""Комплексный генератор PDF-актов (формат A5, половина A4).

Параметризуется шаблоном (template_data) из редактора актов:
- header_text — заголовок акта
- footer_text — офис/адрес в шапке
- logo_path / qr_path — логотип и QR (любой формат, включая .bmp, через PIL)
- primary_color — акцентный цвет рамок
- fields — какие поля заказа выводить
- conditions / warranty_text — текст условий/гарантии

Размер страницы — A5 (148x210 мм), поля 10 мм. Контент уплотнён, чтобы
помещаться в половину A4 без удаления блоков. Весь пользовательский текст
экранируется для XML/ReportLab Paragraph.
"""

import os
import tempfile
from datetime import datetime
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from reportlab.platypus import Paragraph, Table, TableStyle

from utils.formatters import (
    format_date,
    format_order_number_for_display,
    format_phone,
    format_price,
    parse_price_to_float,
)

# ---------------------------------------------------------------------------
# Константы оформления (соответствуют .fr3)
# ---------------------------------------------------------------------------

# A5 в пунктах (1 мм ~= 2.83465 pt). 148x210 мм — половина A4.
A5 = (148 * 2.83465, 210 * 2.83465)
MARGIN = 6 * 2.83465  # 6 мм поля — компактнее, больше места под контент

FONT_FALLBACK = "Helvetica"  # fallback если Trebuchet MS недоступен

DEFAULT_COMPANY = {
    "name": "Сервисный центр",
    "address": "",
    "phone": "",
    "schedule": "",
}

# Метки полей заказа (используется редактором и генератором)
FIELD_LABELS = {
    "order_number": "Номер заказа",
    "receipt_date": "Дата приема",
    "completion_date": "Дата выдачи",
    "client_name": "Имя и фамилия клиента",
    "phone": "Телефон клиента",
    "device_type": "Тип устройства",
    "brand": "Бренд",
    "model": "Модель",
    "serial_number": "Серийный номер",
    "completeness": "Комплектность",
    "appearance": "Внешний вид",
    "defect": "Неисправность",
    "completed_work": "Выполненные работы",
    "total_price": "Общая стоимость",
    "prepayment": "Предоплата",
    "warranty": "Гарантия",
    "engineer": "Инженер",
    "client_status": "Статус клиента",
}


def _color(hex_str: str):
    """Безопасное создание цвета reportlab."""
    try:
        from reportlab.lib.colors import HexColor

        return HexColor(hex_str)
    except Exception:
        from reportlab.lib.colors import black

        return black


def _font() -> str:
    """Возвращает имя доступного шрифта (Trebuchet MS или fallback)."""
    try:
        import glob

        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        names = pdfmetrics.getRegisteredFontNames()
        if "TrebuchetMS" not in names:
            candidates = glob.glob(r"C:\Windows\Fonts\trebuc.ttf")
            if candidates:
                pdfmetrics.registerFont(TTFont("TrebuchetMS", candidates[0]))
                return "TrebuchetMS"
        if "TrebuchetMS" in pdfmetrics.getRegisteredFontNames():
            return "TrebuchetMS"
        return FONT_FALLBACK
    except Exception:
        return FONT_FALLBACK


# Маппинг: имя шрифта в UI → (TTF-regular, TTF-bold, имя для reportlab)
_FONT_TTF_MAP = {
    "Trebuchet MS": (
        r"C:\Windows\Fonts\trebuc.ttf",
        r"C:\Windows\Fonts\trebucbd.ttf",
        "TrebuchetMS",
        "TrebuchetMS-Bold",
    ),
    "Arial": (
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        "ActArial",
        "ActArial-Bold",
    ),
    "Times New Roman": (
        r"C:\Windows\Fonts\times.ttf",
        r"C:\Windows\Fonts\timesbd.ttf",
        "ActTimes",
        "ActTimes-Bold",
    ),
    "Helvetica": (
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        "ActArial",
        "ActArial-Bold",
    ),
    # Tahoma и Verdana как альтернативы
    "Tahoma": (
        r"C:\Windows\Fonts\tahoma.ttf",
        r"C:\Windows\Fonts\tahomabd.ttf",
        "ActTahoma",
        "ActTahoma-Bold",
    ),
    "Verdana": (
        r"C:\Windows\Fonts\verdana.ttf",
        r"C:\Windows\Fonts\verdanab.ttf",
        "ActVerdana",
        "ActVerdana-Bold",
    ),
}


def _register_act_font(font_name: str):
    """Регистрирует TTF-шрифты (regular + bold) для кириллицы.

    Возвращает (font_regular, font_bold) — имена для reportlab.
    Стандартные PDF-шрифты (Helvetica/Times-Roman) НЕ поддерживают кириллицу,
    поэтому ВСЕ шрифты регистрируем через TTF-файлы Windows.
    Fallback на Trebuchet MS, если файл не найден.
    """
    import os

    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except Exception:
        return FONT_FALLBACK, "Helvetica-Bold"

    entry = _FONT_TTF_MAP.get(font_name) or _FONT_TTF_MAP["Trebuchet MS"]
    ttf_reg, ttf_bold, name_reg, name_bold = entry

    names = pdfmetrics.getRegisteredFontNames()
    try:
        if name_reg not in names and os.path.exists(ttf_reg):
            pdfmetrics.registerFont(TTFont(name_reg, ttf_reg))
        if name_bold not in names and os.path.exists(ttf_bold):
            pdfmetrics.registerFont(TTFont(name_bold, ttf_bold))
        if name_reg in pdfmetrics.getRegisteredFontNames():
            bold = (
                name_bold
                if name_bold in pdfmetrics.getRegisteredFontNames()
                else name_reg
            )
            return name_reg, bold
    except Exception as e:
        print(f"Не удалось зарегистрировать шрифт {font_name}: {e}")

    # Fallback на Trebuchet MS
    return _font(), _font() + "-Bold" if _font() != FONT_FALLBACK else FONT_FALLBACK


# ---------------------------------------------------------------------------
# Изображения (логотип/QR) — поддержка .bmp через PIL
# ---------------------------------------------------------------------------


def _prepare_image(path: str) -> str | None:
    """Готовит изображение для ReportLab.

    ReportLab плохо переваривает BMP. Конвертируем любой формат (.bmp/.gif/...)
    через PIL во временный PNG. Возвращает путь к PNG либо None при ошибке.
    Original не удаляется. Временный PNG живёт до завершения процесса.
    """
    if not path or not os.path.exists(path):
        return None
    try:
        from PIL import Image as _PILImage
    except Exception:
        return None
    try:
        img = _PILImage.open(path)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        fd, tmp_png = tempfile.mkstemp(suffix=".png", prefix="act_img_")
        os.close(fd)
        img.save(tmp_png, "PNG")
        return tmp_png
    except Exception as e:
        print(f"Не удалось подготовить изображение {path}: {e}")
        return None


# ---------------------------------------------------------------------------
# Парсер work_items (JSON-список работ из Device)
# ---------------------------------------------------------------------------


def _parse_work_items(work_items_json: str) -> list[dict[str, Any]]:
    """Разбирает JSON-список выполненных работ в список словарей."""
    import json

    if not work_items_json:
        return []
    try:
        data = json.loads(work_items_json)
        if not isinstance(data, list):
            return []
        result = []
        for item in data:
            if not isinstance(item, dict):
                continue
            qty = item.get("quantity", 1)
            try:
                qty = int(qty)
            except (ValueError, TypeError):
                qty = 1
            price = parse_price_to_float(item.get("price", 0))
            qty = max(qty, 1)
            result.append(
                {
                    "description": str(item.get("description", "")).strip(),
                    "quantity": qty,
                    "price": price,
                    "total": price * qty,
                }
            )
        return result
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        print(f"Ошибка разбора work_items: {e}")
        return []


def _prepayment_to_str(prepay) -> str:
    """Утилита приведения предоплаты к строке для format_price."""
    return str(prepay) if prepay is not None else "0"


# ---------------------------------------------------------------------------
# Основной генератор
# ---------------------------------------------------------------------------


class ActPDFGenerator:
    """Генератор PDF-актов формата A5 по образцу .fr3, параметризуемый шаблоном."""

    def __init__(
        self,
        company_info: dict[str, str] | None = None,
        template_data: dict[str, Any] | None = None,
    ):
        self.template = template_data or {}
        # Реквизиты организации. Приоритет: явный company_info > поля шаблона
        # (name/footer_text, как их сохраняет редактор актов) > дефолт.
        # Раньше company_info полностью затирал template — из-за этого «название»
        # и «офис» из редактора не применялись при печати из формы заказа.
        self.company = {
            "name": (company_info or {}).get("name")
            or self.template.get("company_name")
            or self.template.get("name")
            or DEFAULT_COMPANY["name"],
            "address": (company_info or {}).get("address")
            or self.template.get("company_address")
            or self.template.get("footer_text")
            or DEFAULT_COMPANY["address"],
            "phone": (company_info or {}).get("phone")
            or self.template.get("company_phone")
            or DEFAULT_COMPANY["phone"],
            "schedule": (company_info or {}).get("schedule")
            or self.template.get("company_schedule")
            or DEFAULT_COMPANY["schedule"],
        }
        # Шрифт акта из шаблона. Все шрифты регистрируем через TTF-файлы
        # (стандартные PDF-шрифты Helvetica/Times НЕ поддерживают кириллицу —
        # вместо букв будут чёрные квадраты).
        tpl_font = self.template.get("font_name", "Trebuchet MS")
        self.font, self.font_bold = _register_act_font(tpl_font)

        self.accent = _color(self.template.get("primary_color", "#0078d4"))
        # Поля страницы из шаблона (мм → pt), по умолчанию 6мм
        try:
            margin_mm = int(self.template.get("page_margin_mm", 6))
        except (ValueError, TypeError):
            margin_mm = 6
        self.margin = margin_mm * 2.83465

    def _field_value(self, field: str, device: dict[str, Any]) -> str:
        """Форматированное значение поля заказа для вывода в акт."""
        v = device.get(field, "")
        if field == "phone":
            return format_phone(v)
        if field in ("total_price", "prepayment"):
            return format_price(v) if v else ""
        if field in ("receipt_date", "completion_date"):
            return format_date(v)
        if field == "order_number":
            return format_order_number_for_display(v)
        if field in ("completeness", "appearance", "warranty"):
            return str(v) if v else ""
        return str(v) if v else ""

    # ------------------------------------------------------------------
    # Публичные методы генерации
    # ------------------------------------------------------------------

    def generate_receipt_pdf(self, filepath: str, device: dict[str, Any]) -> bool:
        try:
            story = self._build_receipt_story(device)
            return self._save_pdf(filepath, story)
        except Exception as e:
            print(f"Ошибка генерации акта приёма (PDF): {e}")
            return False

    def generate_completion_pdf(self, filepath: str, device: dict[str, Any]) -> bool:
        try:
            story = self._build_completion_story(device)
            return self._save_pdf(filepath, story)
        except Exception as e:
            print(f"Ошибка генерации акта выполненных работ (PDF): {e}")
            return False

    def render_receipt_text(self, device: dict[str, Any]) -> str:
        return self._receipt_text(device)

    def render_completion_text(self, device: dict[str, Any]) -> str:
        return self._completion_text(device)

    # ------------------------------------------------------------------
    # Сборка story для ReportLab
    # ------------------------------------------------------------------

    def _save_pdf(self, filepath: str, story: list) -> bool:
        from reportlab.platypus import SimpleDocTemplate

        doc = SimpleDocTemplate(
            filepath,
            pagesize=A5,
            leftMargin=self.margin,
            rightMargin=self.margin,
            topMargin=self.margin,
            bottomMargin=self.margin,
            title="Акт",
            author=self.company.get("name", "Сервисный центр"),
        )
        doc.build(story)
        return True

    def generate_dual_pdf(
        self,
        filepath: str,
        device1: dict[str, Any],
        device2: dict[str, Any] | None = None,
        act_type1: str = "receipt",
        act_type2: str = "completion",
    ) -> bool:
        """Генерирует PDF с двумя актами на одном листе A4 (каждый A5).

        Параметры:
            device1, device2 — данные заказов для актов (device2=None → один акт).
            act_type1, act_type2 — 'receipt' или 'completion' для каждого акта.
                По умолчанию: receipt (верх) + completion (низ).
                Для двух одинаковых: act_type1='receipt', act_type2='receipt'.
        """
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import KeepInFrame, SimpleDocTemplate, Spacer

            a4_w, a4_h = A4
            doc = SimpleDocTemplate(
                filepath,
                pagesize=A4,
                leftMargin=self.margin,
                rightMargin=self.margin,
                topMargin=self.margin,
                bottomMargin=self.margin,
                title="Акты",
                author=self.company.get("name", "Сервисный центр"),
            )
            content_w = a4_w - 2 * self.margin
            half_h = (a4_h - 2 * self.margin) / 2 - 10

            def _build_story(device, act_type):
                """Выбирает нужный story по типу акта."""
                if act_type == "completion":
                    return self._build_completion_story(device)
                return self._build_receipt_story(device)

            story = []
            # Акт 1
            story1 = _build_story(device1, act_type1)
            story.append(KeepInFrame(content_w, half_h, story1, mode="shrink"))
            story.append(Spacer(1, 8))

            # Акт 2 (если есть)
            if device2:
                story2 = _build_story(device2, act_type2)
                story.append(KeepInFrame(content_w, half_h, story2, mode="shrink"))

            doc.build(story)
            return True
        except Exception as e:
            print(f"Ошибка генерации двойного акта (PDF): {e}")
            return False

    def _styles(self):
        """Уплотнённые стили для A5 (половина A4)."""
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.lib.styles import ParagraphStyle

        f = self.font
        fb = self.font_bold
        return {
            "logo_note": ParagraphStyle(
                "logo_note", fontName=f, fontSize=7, alignment=TA_CENTER, leading=9
            ),
            "company": ParagraphStyle(
                "company",
                fontName=fb,
                fontSize=11,
                alignment=TA_CENTER,
                leading=13,
                spaceAfter=1,
            ),
            "company_sub": ParagraphStyle(
                "company_sub", fontName=f, fontSize=7.5, alignment=TA_CENTER, leading=9
            ),
            "schedule": ParagraphStyle(
                "schedule",
                fontName=fb,
                fontSize=7,
                alignment=TA_CENTER,
                leading=8,
                spaceAfter=2,
            ),
            "title": ParagraphStyle(
                "title",
                fontName=fb,
                fontSize=11,
                alignment=TA_CENTER,
                leading=13,
                spaceBefore=1,
                spaceAfter=2,
            ),
            "section": ParagraphStyle(
                "section",
                fontName=fb,
                fontSize=9,
                alignment=TA_CENTER,
                leading=11,
                spaceBefore=1,
                spaceAfter=1,
                backColor=_color("#F0F0F0"),
            ),
            "cell_label": ParagraphStyle(
                "cell_label", fontName=f, fontSize=7.5, alignment=TA_RIGHT, leading=9
            ),
            "cell_value": ParagraphStyle(
                "cell_value", fontName=f, fontSize=7.5, alignment=TA_LEFT, leading=9
            ),
            "cell_value_bold": ParagraphStyle(
                "cell_value_bold",
                fontName=fb,
                fontSize=9,
                alignment=TA_LEFT,
                leading=11,
            ),
            "defect": ParagraphStyle(
                "defect", fontName=f, fontSize=7.5, alignment=TA_LEFT, leading=10
            ),
            "footer": ParagraphStyle(
                "footer",
                fontName=f,
                fontSize=7,
                alignment=TA_CENTER,
                leading=8,
                spaceBefore=2,
            ),
            "sign": ParagraphStyle(
                "sign", fontName=f, fontSize=7, alignment=TA_LEFT, leading=9
            ),
            "th": ParagraphStyle(
                "th", fontName=fb, fontSize=7, alignment=TA_CENTER, leading=8
            ),
            "td": ParagraphStyle(
                "td", fontName=f, fontSize=7, alignment=TA_LEFT, leading=8
            ),
            "td_num": ParagraphStyle(
                "td_num", fontName=f, fontSize=7, alignment=TA_CENTER, leading=8
            ),
            "total_label": ParagraphStyle(
                "total_label", fontName=fb, fontSize=8.5, alignment=TA_RIGHT, leading=10
            ),
            "total_value": ParagraphStyle(
                "total_value",
                fontName=fb,
                fontSize=8.5,
                alignment=TA_CENTER,
                leading=10,
            ),
            "note_text": ParagraphStyle(
                "note_text", fontName=f, fontSize=7, alignment=TA_LEFT, leading=9
            ),
        }

    def _logo_block(self, styles) -> list:
        """Логотип в шапке (если задан в шаблоне). Поддержка .bmp через PIL.

        Размер и позиция берутся из шаблона (logo_size, logo_position).
        """
        story = []
        logo_path = self.template.get("logo_path", "")
        if not logo_path:
            return story
        png = _prepare_image(logo_path)
        if not png:
            return story
        try:
            from reportlab.platypus import Image as RLImage

            # Размер логотипа из шаблона (по умолчанию 50pt)
            size = self.template.get("logo_size", 50)
            try:
                size = int(size)
            except (ValueError, TypeError):
                size = 50
            size = max(20, min(size, 120))
            img = RLImage(png, width=size, height=size, kind="proportional")
            # Позиция логотипа из шаблона
            position = self.template.get("logo_position", "По центру")
            if "Слева" in str(position):
                img.hAlign = "LEFT"
            elif "Справа" in str(position):
                img.hAlign = "RIGHT"
            else:
                img.hAlign = "CENTER"
            story.append(img)
        except Exception as e:
            print(f"Не удалось вставить логотип: {e}")
        return story

    def _header_block(self, styles) -> list:
        """Шапка организации (логотип, название, адрес, телефон, график)."""
        from reportlab.platypus import Paragraph

        story = []
        story.extend(self._logo_block(styles))
        story.append(
            Paragraph(xml_escape(self.company.get("name", "")), styles["company"])
        )
        sub = f"{xml_escape(self.company.get('address', ''))}   {xml_escape(self.company.get('phone', ''))}"
        story.append(Paragraph(sub, styles["company_sub"]))
        schedule = self.company.get("schedule", "")
        if schedule:
            story.append(Paragraph(xml_escape(schedule), styles["schedule"]))
        return story

    def _title(self, styles) -> list:
        """Заголовок документа в рамке — берётся из шаблона."""
        from reportlab.platypus import Paragraph, Table, TableStyle

        text = self.template.get("header_text", "") or "Акт"
        p = Paragraph(xml_escape(text), styles["title"])
        t = Table([[p]], colWidths=[A5[0] - 2 * self.margin])
        t.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.5, self.accent),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        return [t]

    def _field_table(self, rows: list[tuple], styles) -> Table:
        """Таблица «метка | значение»."""
        label_w = (A5[0] - 2 * self.margin) * 0.34
        value_w = (A5[0] - 2 * self.margin) * 0.66
        data = []
        for label, value in rows:
            label_para = Paragraph(xml_escape(str(label)), styles["cell_label"])
            value_para = Paragraph(xml_escape(str(value)), styles["cell_value"])
            data.append([label_para, value_para])

        t = Table(data, colWidths=[label_w, value_w])
        t.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, _color("#000000")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]
            )
        )
        return t

    def _order_row(self, order_no: str, styles) -> Table:
        """Подсвеченная строка с номером заказа."""
        total_w = A5[0] - 2 * self.margin
        t = Table(
            [
                [
                    Paragraph("Номер заказа", styles["cell_label"]),
                    Paragraph(xml_escape(str(order_no)), styles["cell_value_bold"]),
                ]
            ],
            colWidths=[total_w * 0.34, total_w * 0.66],
        )
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _color("#D9E2F3")),
                    ("BOX", (0, 0), (-1, -1), 0.4, _color("#000000")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, _color("#000000")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        return t

    def _rows_from_template(
        self, device: dict[str, Any], exclude=("order_number",)
    ) -> list[tuple]:
        """Строит список (label, value) по полям из шаблона.

        Спецполя (defect, total_price, prepayment, completed_work) исключаются
        из общей таблицы — они выводятся отдельными акцентными блоками
        (рамка «Неисправность», «Стоимость ремонта», таблица работ),
        чтобы акт выглядел как в оригинальных шаблонах .fr3.
        """
        fields = self.template.get("fields")
        if not fields:
            return []
        # Поля, идущие в отдельные блоки — не дублируем в таблице
        special_fields = (
            "order_number",
            "defect",
            "total_price",
            "prepayment",
            "completed_work",
        )
        rows = []
        for field in fields:
            if field in exclude or field in special_fields:
                continue
            label = FIELD_LABELS.get(field, field)
            value = self._field_value(field, device)
            rows.append((label, value))
        return rows

    # ------------------------------------------------------------------
    # Акт приёма
    # ------------------------------------------------------------------

    def _build_receipt_story(self, device: dict[str, Any]) -> list:
        from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

        styles = self._styles()
        story = []

        story.extend(self._header_block(styles))
        story.extend(self._title(styles))

        order_no = self._field_value("order_number", device)
        story.append(self._order_row(order_no, styles))

        rows = self._rows_from_template(device)
        if not rows:
            device_name = self._device_full_name(device)
            rows = [
                ("Дата приема", format_date(device.get("receipt_date", ""))),
                ("Имя и фамилия клиента", device.get("client_name", "")),
                ("Телефон клиента", format_phone(device.get("phone", ""))),
                ("Устройство", device_name),
                ("Серийный номер", device.get("serial_number", "") or "не указан"),
                ("Комплектность", device.get("completeness", "") or "не указана"),
                ("Внешний вид", device.get("appearance", "") or "не указан"),
            ]
        story.append(self._field_table(rows, styles))

        # Блок «Неисправность со слов клиента» — акцентный блок с рамкой.
        # Показывается, если defect отмечен в шаблоне (или шаблона нет — дефолт).
        template_fields = self.template.get("fields") or []
        show_defect = (not template_fields) or ("defect" in template_fields)
        if show_defect:
            story.append(Spacer(1, 3))
            story.append(Paragraph("Неисправность со слов клиента", styles["section"]))
            defect_text = xml_escape(str(device.get("defect", "") or "—"))
            defect_tbl = Table(
                [[Paragraph(defect_text, styles["defect"])]],
                colWidths=[A5[0] - 2 * self.margin],
            )
            defect_tbl.setStyle(
                TableStyle(
                    [
                        ("BOX", (0, 0), (-1, -1), 0.4, _color("#000000")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )
            story.append(defect_tbl)

        # Предварительная стоимость — акцентный блок, если total_price отмечен.
        total = device.get("total_price", "")
        show_price = (not template_fields) or ("total_price" in template_fields)
        if total and show_price:
            story.append(Spacer(1, 3))
            prepay = device.get("prepayment", "")
            price_line = f"Стоимость ремонта — {format_price(total)}"
            if parse_price_to_float(prepay) > 0:
                price_line += (
                    f"  (предоплата {format_price(_prepayment_to_str(prepay))})"
                )
            price_tbl = Table(
                [[Paragraph(xml_escape(price_line), styles["defect"])]],
                colWidths=[A5[0] - 2 * self.margin],
            )
            price_tbl.setStyle(
                TableStyle(
                    [
                        ("BOX", (0, 0), (-1, -1), 0.4, _color("#000000")),
                        ("BACKGROUND", (0, 0), (-1, -1), _color("#F0F0F0")),
                        ("TOPPADDING", (0, 0), (-1, -1), 2),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ]
                )
            )
            story.append(price_tbl)

        # Условия ремонта из шаблона (если есть)
        conditions = self.template.get("conditions", "")
        if conditions:
            story.append(Spacer(1, 3))
            story.append(Paragraph("Условия ремонта", styles["section"]))
            cond_lines = []
            for line in conditions.split("\n"):
                if line.strip():
                    cond_lines.append(
                        [Paragraph(xml_escape(line.strip()), styles["note_text"])]
                    )
            if cond_lines:
                cond_tbl = Table(cond_lines, colWidths=[A5[0] - 2 * self.margin])
                cond_tbl.setStyle(
                    TableStyle(
                        [
                            ("LEFTPADDING", (0, 0), (-1, -1), 4),
                            ("TOPPADDING", (0, 0), (-1, -1), 0),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ]
                    )
                )
                story.append(cond_tbl)

        story.extend(self._signatures_block(styles, with_date=True))
        return story

    # ------------------------------------------------------------------
    # Акт выполненных работ
    # ------------------------------------------------------------------

    def _build_completion_story(self, device: dict[str, Any]) -> list:
        from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

        styles = self._styles()
        story = []

        story.extend(self._header_block(styles))
        story.extend(self._title(styles))

        order_no = self._field_value("order_number", device)
        story.append(self._order_row(order_no, styles))

        rows = self._rows_from_template(device)
        if not rows:
            device_name = self._device_full_name(device)
            completion_date = device.get("completion_date", "")
            rows = [
                ("Имя и фамилия клиента", device.get("client_name", "")),
                ("Телефон клиента", format_phone(device.get("phone", ""))),
                ("Устройство", device_name),
                ("Серийный номер", device.get("serial_number", "") or "не указан"),
                ("Дата приема", format_date(device.get("receipt_date", ""))),
                (
                    "Дата выдачи",
                    format_date(completion_date)
                    if completion_date
                    else datetime.now().strftime("%d.%m.%Y"),
                ),
                ("Гарантия", device.get("warranty", "") or "не указана"),
            ]
        story.append(self._field_table(rows, styles))

        # Таблица выполненных работ
        story.append(Spacer(1, 3))
        story.append(Paragraph("Выполненные работы", styles["section"]))
        story.append(self._works_table(device, styles))

        # Гарантийные обязательства из шаблона (если есть)
        warranty_text = self.template.get("warranty_text", "")
        if warranty_text:
            story.append(Spacer(1, 3))
            story.append(Paragraph("Гарантийные обязательства", styles["section"]))
            war_lines = []
            for line in warranty_text.split("\n"):
                if line.strip():
                    war_lines.append(
                        [Paragraph(xml_escape(line.strip()), styles["note_text"])]
                    )
            if war_lines:
                war_tbl = Table(war_lines, colWidths=[A5[0] - 2 * self.margin])
                war_tbl.setStyle(
                    TableStyle(
                        [
                            ("LEFTPADDING", (0, 0), (-1, -1), 4),
                            ("TOPPADDING", (0, 0), (-1, -1), 0),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ]
                    )
                )
                story.append(war_tbl)

        # QR-код из шаблона (внизу)
        qr_path = self.template.get("qr_path", "")
        if self.template.get("show_qr", False) and qr_path:
            png = _prepare_image(qr_path)
            if png:
                try:
                    from reportlab.platypus import Image as RLImage

                    story.append(Spacer(1, 4))
                    qr_img = RLImage(png, width=40, height=40, kind="proportional")
                    qr_img.hAlign = "CENTER"
                    story.append(qr_img)
                except Exception:
                    pass

        story.extend(self._signatures_block(styles, with_date=True))
        return story

    def _works_table(self, device: dict[str, Any], styles) -> Table:
        """Таблица выполненных работ: Наименование | Кол-во | Цена за ед. | Сумма + итог."""

        total_w = A5[0] - 2 * self.margin
        col_widths = [total_w * 0.46, total_w * 0.14, total_w * 0.20, total_w * 0.20]

        work_items = _parse_work_items(device.get("work_items", ""))
        if not work_items:
            cw = str(device.get("completed_work", "") or "").strip()
            if cw:
                total = parse_price_to_float(device.get("total_price", 0))
                work_items = [
                    {"description": cw, "quantity": 1, "price": total, "total": total}
                ]

        header = [
            Paragraph("Наименование", styles["th"]),
            Paragraph("Кол-во", styles["th"]),
            Paragraph("Цена за ед.", styles["th"]),
            Paragraph("Сумма", styles["th"]),
        ]
        data = [header]
        grand_total = 0.0
        for item in work_items:
            grand_total += item["total"]
            data.append(
                [
                    Paragraph(xml_escape(item["description"] or "—"), styles["td"]),
                    Paragraph(str(item["quantity"]), styles["td_num"]),
                    Paragraph(
                        format_price(item["price"]).replace(" ₽", " р."),
                        styles["td_num"],
                    ),
                    Paragraph(
                        format_price(item["total"]).replace(" ₽", " р."),
                        styles["td_num"],
                    ),
                ]
            )

        data.append(
            [
                Paragraph("", styles["td"]),
                Paragraph("", styles["td_num"]),
                Paragraph("Итого к оплате:", styles["total_label"]),
                Paragraph(
                    f"{format_price(grand_total).replace(' ₽', '')} р.",
                    styles["total_value"],
                ),
            ]
        )

        n_rows = len(data)
        last = n_rows - 1
        tbl = Table(data, colWidths=col_widths, repeatRows=1)
        cmds = [
            ("GRID", (0, 0), (-1, last), 0.4, _color("#000000")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("BACKGROUND", (0, 0), (-1, 0), _color("#F0F0F0")),
            ("SPAN", (0, last), (1, last)),
            ("BACKGROUND", (0, last), (-1, last), _color("#D9E2F3")),
            ("LINEABOVE", (0, last), (-1, last), 0.7, _color("#000000")),
        ]
        tbl.setStyle(TableStyle(cmds))
        return tbl

    # ------------------------------------------------------------------
    # Общие вспомогательные блоки
    # ------------------------------------------------------------------

    def _device_full_name(self, device: dict[str, Any]) -> str:
        parts = [
            str(device.get("device_type", "")).strip(),
            str(device.get("brand", "")).strip(),
            str(device.get("model", "")).strip(),
        ]
        return " ".join(p for p in parts if p) or "—"

    def _signatures_block(self, styles, with_date: bool = False) -> list:
        """Блок подписей сторон. «Инженер» вместо «Мастер». Дата убрана из актов."""
        from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

        story = [Spacer(1, 3)]
        cell = "Инженер: ____________________<br/><font size=6>(подпись)</font>"
        cell2 = "Клиент: ____________________<br/><font size=6>(подпись)</font>"
        p1 = Paragraph(cell, styles["sign"])
        p2 = Paragraph(cell2, styles["sign"])
        total_w = A5[0] - 2 * self.margin
        tbl = Table([[p1, p2]], colWidths=[total_w * 0.5, total_w * 0.5])
        tbl.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(tbl)
        return story

    # ------------------------------------------------------------------
    # Текстовый предпросмотр (fallback, если pypdfium2 недоступен)
    # ------------------------------------------------------------------

    def _receipt_text(self, device: dict[str, Any]) -> str:
        order_no = format_order_number_for_display(device.get("order_number", ""))
        device_name = self._device_full_name(device)
        total = format_price(device.get("total_price", ""))
        prepay = device.get("prepayment", "")
        lines = [
            "=" * 60,
            self.company.get("name", "").center(60),
            f"{self.company.get('address', '')}   {self.company.get('phone', '')}".center(
                60
            ),
            self.company.get("schedule", "").center(60),
            "=" * 60,
            "Акт приема оборудования в ремонт".center(60),
            "-" * 60,
            f"{'Номер заказа':.<30} {order_no}",
            f"{'Дата приема':.<30} {format_date(device.get('receipt_date', ''))}",
            f"{'Имя и фамилия клиента':.<30} {device.get('client_name', '')}",
            f"{'Телефон клиента':.<30} {format_phone(device.get('phone', ''))}",
            f"{'Устройство':.<30} {device_name}",
            f"{'Серийный номер':.<30} {device.get('serial_number', '') or 'не указан'}",
            f"{'Комплектность':.<30} {device.get('completeness', '') or 'не указана'}",
            f"{'Внешний вид':.<30} {device.get('appearance', '') or 'не указан'}",
            "-" * 60,
            "Неисправность со слов клиента:".center(60),
            f"  {device.get('defect', '') or '—'}",
            "-" * 60,
            f"Стоимость ремонта — {total}",
        ]
        if parse_price_to_float(prepay) > 0:
            lines.append(f"Предоплата — {format_price(_prepayment_to_str(prepay))}")
        lines += [
            "=" * 60,
            "Инженер: __________________   Клиент: __________________",
            "=" * 60,
        ]
        return "\n".join(lines)

    def _completion_text(self, device: dict[str, Any]) -> str:
        order_no = format_order_number_for_display(device.get("order_number", ""))
        device_name = self._device_full_name(device)
        work_items = _parse_work_items(device.get("work_items", ""))
        lines = [
            "=" * 60,
            self.company.get("name", "").center(60),
            f"{self.company.get('address', '')}   {self.company.get('phone', '')}".center(
                60
            ),
            self.company.get("schedule", "").center(60),
            "=" * 60,
            "Акт выполненных работ".center(60),
            "-" * 60,
            f"{'Номер заказа':.<30} {order_no}",
            f"{'Имя и фамилия клиента':.<30} {device.get('client_name', '')}",
            f"{'Телефон клиента':.<30} {format_phone(device.get('phone', ''))}",
            f"{'Устройство':.<30} {device_name}",
            f"{'Серийный номер':.<30} {device.get('serial_number', '') or 'не указан'}",
            f"{'Дата приема':.<30} {format_date(device.get('receipt_date', ''))}",
            f"{'Дата выдачи':.<30} {format_date(device.get('completion_date', '')) or datetime.now().strftime('%d.%m.%Y')}",
            f"{'Гарантия':.<30} {device.get('warranty', '') or 'не указана'}",
            "-" * 60,
            "Выполненные работы:".center(60),
            f"{'Наименование':<40}{'Кол-во':>6}{'Цена':>7}{'Сумма':>7}",
            "-" * 60,
        ]
        grand_total = 0.0
        for item in work_items:
            grand_total += item["total"]
            lines.append(
                f"{(item['description'] or '—')[:38]:<40}"
                f"{item['quantity']!s:>6}"
                f"{int(item['price']):>6}р"
                f"{int(item['total']):>7}р"
            )
        if not work_items:
            lines.append("  Работы не указаны")
        lines += [
            "-" * 60,
            f"{'Итого к оплате:':>53} {int(grand_total)} р.",
            "=" * 60,
            "Инженер: __________________   Клиент: __________________",
            "=" * 60,
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Совместимость со старым API (PDFRenderer)
# ---------------------------------------------------------------------------


class PDFRenderer:
    """Тонкая обёртка над ActPDFGenerator для обратной совместимости."""

    def __init__(
        self,
        template_data: dict[str, Any] | None = None,
        colors: dict[str, str] | None = None,
        act_type: str = "receipt",
    ):
        self.template = template_data or {}
        self.colors = colors or {}
        self.act_type = self.template.get("act_type", act_type)
        self.generator = ActPDFGenerator(template_data=self.template)

    def export_to_pdf(self, filepath: str, data: dict[str, Any] | None = None) -> bool:
        data = data or {}
        if self.act_type == "completion":
            return self.generator.generate_completion_pdf(filepath, data)
        return self.generator.generate_receipt_pdf(filepath, data)

    def render_act(self, data: dict[str, Any] | None = None) -> str:
        data = data or {}
        if self.act_type == "completion":
            return self.generator.render_completion_text(data)
        return self.generator.render_receipt_text(data)

    def preview(self) -> str:
        return self.render_act({})
