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

import atexit
import contextlib
import logging
import os
import tempfile
from datetime import datetime
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from utils.formatters import (
    format_date,
    format_order_number_for_display,
    format_phone,
    format_price,
    parse_price_to_float,
)

# Раньше в этом файле не было логирования вообще — все ошибки уходили в
# bare print(), который в frozen-сборке (--windowed, без консоли) и в CI не
# попадает никуда: PDF молча возвращался как False/недоступный без единой
# строчки в логах приложения (см. workflow-найденный баг о шрифтах).
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Константы оформления (соответствуют .fr3)
# ---------------------------------------------------------------------------

# A5 в пунктах (1 мм ~= 2.83465 pt). 148x210 мм — половина A4.
MM_TO_PT = 2.83465
A5 = (148 * MM_TO_PT, 210 * MM_TO_PT)
MARGIN = 6 * MM_TO_PT  # 6 мм поля — компактнее, больше места под контент

# ---------------------------------------------------------------------------
# Свободный макет (canvas layout_mode) — поля/блоки, которые можно
# произвольно позиционировать на странице в билдере акта, вместо
# фиксированного проточного (flow) порядка. См. _build_canvas_flowable().
# ---------------------------------------------------------------------------

# Простые поля заказа — каждое можно перетащить на канвасе как отдельный бокс.
CANVAS_SIMPLE_FIELDS = (
    "order_number",
    "receipt_date",
    "completion_date",
    "client_name",
    "phone",
    "device_type",
    "brand",
    "model",
    "serial_number",
    "completeness",
    "appearance",
    "defect",
    "total_price",
    "prepayment",
    "warranty",
    "engineer",
    "client_status",
)

# Составные блоки (переиспользуют существующую вёрстку — рамки, таблицы) —
# тоже перетаскиваемые боксы, но их внутреннее содержимое строится
# методом-построителем, а не просто "label: value".
CANVAS_COMPOSITE_FIELDS = {
    "header": {
        "label": "Шапка (лого + организация)",
        "act_types": ("receipt", "completion"),
    },
    "title": {"label": "Заголовок документа", "act_types": ("receipt", "completion")},
    "field_table": {
        "label": "Таблица полей (список ниже)",
        "act_types": ("receipt", "completion"),
    },
    "defect_box": {"label": "Блок «Неисправность»", "act_types": ("receipt",)},
    "price_box": {"label": "Блок «Стоимость ремонта»", "act_types": ("receipt",)},
    "conditions_box": {"label": "Условия ремонта", "act_types": ("receipt",)},
    "works_table": {
        "label": "Таблица выполненных работ",
        "act_types": ("completion",),
    },
    "warranty_box": {
        "label": "Гарантийные обязательства",
        "act_types": ("completion",),
    },
    "qr": {"label": "QR-код", "act_types": ("completion",)},
    "signatures": {"label": "Подписи сторон", "act_types": ("receipt", "completion")},
}

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


def _first_existing(paths: tuple[str, ...]) -> str | None:
    return next((p for p in paths if os.path.exists(p)), None)


# Маппинг: имя шрифта в UI → (варианты TTF-regular, варианты TTF-bold, имя
# regular для reportlab, имя bold для reportlab). Каждый шрифт даёт СПИСОК
# путей-кандидатов, а не один: раньше здесь был единственный жёстко зашитый
# C:\Windows\Fonts\... путь на семейство — на любом non-Windows CI-раннере
# (ubuntu-latest/macos-latest в .github/workflows/build.yml, и на любой
# Linux/macOS машине пользователя) НИ ОДИН такой путь не существует, поэтому
# _register_act_font() ниже молча откатывался на core-Helvetica — стандартный
# PDF-шрифт, вообще не способный отрисовать кириллицу (см. workflow-найденный
# баг). Первый реально существующий путь в списке побеждает; Trebuchet MS —
# проприетарный шрифт Microsoft, которого на Linux/macOS обычно нет вовсе,
# поэтому и для него, и для остальных семейств добавлены типичные
# предустановленные Cyrillic-совместимые замены (DejaVu Sans — Ubuntu/Debian
# по умолчанию, Liberation Sans — частый пакет на Linux, Arial из
# /System/Library/Fonts/Supplemental — macOS).
_LINUX_MAC_SANS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
)
_LINUX_MAC_SANS_BOLD = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
)

_FONT_TTF_MAP = {
    "Trebuchet MS": (
        (r"C:\Windows\Fonts\trebuc.ttf", *_LINUX_MAC_SANS),
        (r"C:\Windows\Fonts\trebucbd.ttf", *_LINUX_MAC_SANS_BOLD),
        "TrebuchetMS",
        "TrebuchetMS-Bold",
    ),
    "Arial": (
        (r"C:\Windows\Fonts\arial.ttf", *_LINUX_MAC_SANS),
        (r"C:\Windows\Fonts\arialbd.ttf", *_LINUX_MAC_SANS_BOLD),
        "ActArial",
        "ActArial-Bold",
    ),
    "Times New Roman": (
        (r"C:\Windows\Fonts\times.ttf", *_LINUX_MAC_SANS),
        (r"C:\Windows\Fonts\timesbd.ttf", *_LINUX_MAC_SANS_BOLD),
        "ActTimes",
        "ActTimes-Bold",
    ),
    "Helvetica": (
        (r"C:\Windows\Fonts\arial.ttf", *_LINUX_MAC_SANS),
        (r"C:\Windows\Fonts\arialbd.ttf", *_LINUX_MAC_SANS_BOLD),
        "ActArial",
        "ActArial-Bold",
    ),
    # Tahoma и Verdana как альтернативы
    "Tahoma": (
        (r"C:\Windows\Fonts\tahoma.ttf", *_LINUX_MAC_SANS),
        (r"C:\Windows\Fonts\tahomabd.ttf", *_LINUX_MAC_SANS_BOLD),
        "ActTahoma",
        "ActTahoma-Bold",
    ),
    "Verdana": (
        (r"C:\Windows\Fonts\verdana.ttf", *_LINUX_MAC_SANS),
        (r"C:\Windows\Fonts\verdanab.ttf", *_LINUX_MAC_SANS_BOLD),
        "ActVerdana",
        "ActVerdana-Bold",
    ),
}


def _font() -> str:
    """Возвращает имя доступного шрифта (Trebuchet MS/кросс-платформенная
    замена, либо fallback) — используется только как последний рубеж внутри
    _register_act_font() ниже."""
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        names = pdfmetrics.getRegisteredFontNames()
        if "TrebuchetMS" in names:
            return "TrebuchetMS"
        ttf_candidates, _bold, name_reg, _name_bold = _FONT_TTF_MAP["Trebuchet MS"]
        path = _first_existing(ttf_candidates)
        if path:
            pdfmetrics.registerFont(TTFont(name_reg, path))
            return name_reg
        return FONT_FALLBACK
    except Exception:
        return FONT_FALLBACK


def _register_act_font(font_name: str):
    """Регистрирует TTF-шрифты (regular + bold) для кириллицы.

    Возвращает (font_regular, font_bold) — имена для reportlab.
    Стандартные PDF-шрифты (Helvetica/Times-Roman) НЕ поддерживают кириллицу,
    поэтому ВСЕ шрифты регистрируем через TTF-файлы — первый существующий
    путь-кандидат для текущей ОС (см. _FONT_TTF_MAP).
    """
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except Exception:
        return FONT_FALLBACK, "Helvetica-Bold"

    entry = _FONT_TTF_MAP.get(font_name) or _FONT_TTF_MAP["Trebuchet MS"]
    ttf_reg_candidates, ttf_bold_candidates, name_reg, name_bold = entry

    names = pdfmetrics.getRegisteredFontNames()
    try:
        if name_reg not in names:
            path = _first_existing(ttf_reg_candidates)
            if path:
                pdfmetrics.registerFont(TTFont(name_reg, path))
        if name_bold not in names:
            path = _first_existing(ttf_bold_candidates)
            if path:
                pdfmetrics.registerFont(TTFont(name_bold, path))
        if name_reg in pdfmetrics.getRegisteredFontNames():
            bold = (
                name_bold
                if name_bold in pdfmetrics.getRegisteredFontNames()
                else name_reg
            )
            return name_reg, bold
    except Exception as e:
        logger.error(f"Не удалось зарегистрировать шрифт {font_name}: {e}", exc_info=True)

    # Ни один кандидат для запрошенного семейства не найден — последний
    # рубеж: попытаться зарегистрировать хоть что-то Cyrillic-совместимое.
    # Один и тот же зарегистрированный TTF и на regular, и на bold слот —
    # жирный текст выйдет визуально не жирным, но НЕ упадёт на неизвестном
    # имени шрифта (в отличие от прежнего `_font() + "-Bold"`, которое
    # возвращало имя, никогда фактически не зарегистрированное).
    fallback = _font()
    if fallback == FONT_FALLBACK:
        return FONT_FALLBACK, "Helvetica-Bold"
    return fallback, fallback


# ---------------------------------------------------------------------------
# Изображения (логотип/QR) — поддержка .bmp через PIL
# ---------------------------------------------------------------------------


# Кэш конвертированных логотипов/QR: path -> (mtime на момент конвертации,
# путь к временному PNG). Раньше _prepare_image() создавал НОВЫЙ temp PNG на
# КАЖДЫЙ вызов (то есть на каждую печать акта) без какой-либо очистки — при
# печати дюжины актов в день неделями (обычный режим работы для этого
# desktop+PWA сервиса) в temp-каталоге пользователя копились сотни
# orphan-файлов act_img_*.png (см. workflow-найденный баг). Теперь один и тот
# же исходник конвертируется один раз за время работы процесса; mtime в
# ключе — чтобы заменённый пользователем логотип не отдавал стухший кэш.
_image_cache: dict[str, tuple[float, str]] = {}


def _cleanup_image_cache() -> None:
    for _mtime, tmp_png in _image_cache.values():
        with contextlib.suppress(OSError):
            os.remove(tmp_png)
    _image_cache.clear()


atexit.register(_cleanup_image_cache)


def _prepare_image(path: str) -> str | None:
    """Готовит изображение для ReportLab.

    ReportLab плохо переваривает BMP. Конвертируем любой формат (.bmp/.gif/...)
    через PIL во временный PNG. Возвращает путь к PNG либо None при ошибке.
    Повторные вызовы с тем же path (тем же mtime) отдают уже сконвертированный
    файл из _image_cache вместо создания нового — временные PNG удаляются при
    завершении процесса через _cleanup_image_cache(), а не живут вечно."""
    if not path or not os.path.exists(path):
        return None
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    cached = _image_cache.get(path)
    if cached and cached[0] == mtime and os.path.exists(cached[1]):
        return cached[1]
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
        if cached:
            with contextlib.suppress(OSError):
                os.remove(cached[1])
        _image_cache[path] = (mtime, tmp_png)
        return tmp_png
    except Exception as e:
        logger.error(f"Не удалось подготовить изображение {path}: {e}", exc_info=True)
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
        logger.error(f"Ошибка разбора work_items: {e}", exc_info=True)
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
            if self.template.get("layout_mode") == "canvas":
                return self._build_canvas_pdf(filepath, device, "receipt")
            story = self._build_receipt_story(device)
            return self._save_pdf(filepath, story)
        except Exception as e:
            logger.error(f"Ошибка генерации акта приёма (PDF): {e}", exc_info=True)
            return False

    def generate_completion_pdf(self, filepath: str, device: dict[str, Any]) -> bool:
        try:
            if self.template.get("layout_mode") == "canvas":
                return self._build_canvas_pdf(filepath, device, "completion")
            story = self._build_completion_story(device)
            return self._save_pdf(filepath, story)
        except Exception as e:
            logger.error(f"Ошибка генерации акта выполненных работ (PDF): {e}", exc_info=True)
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

    # ------------------------------------------------------------------
    # Свободный макет (canvas layout_mode)
    # ------------------------------------------------------------------

    def default_canvas_layout(self, act_type: str) -> dict[str, dict[str, float]]:
        """Стартовая раскладка canvas-полей для нового/сконвертированного
        шаблона — те же элементы и тот же порядок, что и в проточной
        вёрстке, просто разложенные сверху вниз в одну колонку. Пользователь
        начинает от знакомого вида и подвигает то, что нужно, а не с
        пустой страницы."""
        page_w_mm = A5[0] / MM_TO_PT
        margin_mm = self.margin / MM_TO_PT
        box_w = page_w_mm - 2 * margin_mm
        y = margin_mm
        layout: dict[str, dict[str, float]] = {}

        order = ["header", "title", "order_number", "field_table"]
        if act_type == "receipt":
            order += ["defect_box", "price_box", "conditions_box", "signatures"]
        else:
            order += ["works_table", "warranty_box", "qr", "signatures"]

        heights_mm = {
            "header": 22,
            "title": 10,
            "order_number": 8,
            "field_table": 40,
            "defect_box": 16,
            "price_box": 10,
            "conditions_box": 20,
            "works_table": 35,
            "warranty_box": 18,
            "qr": 20,
            "signatures": 14,
        }
        for key in order:
            layout[key] = {"x_mm": margin_mm, "y_mm": y, "w_mm": box_w}
            y += heights_mm.get(key, 15) + 3
        return layout

    def _canvas_fields(self) -> dict[str, dict[str, Any]]:
        cfg = self.template.get("canvas_fields")
        return cfg if isinstance(cfg, dict) else {}

    def _build_canvas_flowable(self, key: str, device: dict[str, Any], styles, act_type: str):
        """Возвращает Flowable (или список Flowable) для одного canvas-бокса,
        либо None, если бокс нечего рисовать (пустое значение и т.п.).
        Переиспользует ТЕ ЖЕ методы построения блоков, что и проточная
        вёрстка — макет свободный, но визуал блоков идентичен."""
        from reportlab.lib.styles import ParagraphStyle

        cfg = self._canvas_fields().get(key, {})

        if key == "order_number":
            value = self._field_value("order_number", device)
            return Paragraph(
                f"<b>{xml_escape(FIELD_LABELS.get(key, key))}:</b> {xml_escape(value)}",
                styles["cell_value_bold"],
            )

        if key in CANVAS_SIMPLE_FIELDS:
            value = self._field_value(key, device)
            if not value:
                return None
            show_label = cfg.get("show_label", True)
            label = FIELD_LABELS.get(key, key)
            text = (
                f"<b>{xml_escape(label)}:</b> {xml_escape(value)}"
                if show_label
                else xml_escape(value)
            )
            style = styles["cell_value_bold"] if cfg.get("bold") else styles["cell_value"]
            font_size = cfg.get("font_size")
            if font_size:
                style = ParagraphStyle(
                    f"canvas_{key}",
                    parent=style,
                    fontSize=font_size,
                    leading=font_size * 1.25,
                )
            return Paragraph(text, style)

        if key == "header":
            return self._header_block(styles)
        if key == "title":
            return self._title(styles)
        if key == "field_table":
            rows = self._rows_from_template(device)
            return self._field_table(rows, styles) if rows else None
        if key == "defect_box" and act_type == "receipt":
            return self._defect_block(device, styles) or None
        if key == "price_box" and act_type == "receipt":
            return self._price_block(device, styles) or None
        if key == "conditions_box" and act_type == "receipt":
            return self._conditions_block(styles) or None
        if key == "works_table" and act_type == "completion":
            return self._works_table(device, styles)
        if key == "warranty_box" and act_type == "completion":
            return self._warranty_block(styles) or None
        if key == "qr" and act_type == "completion":
            return self._qr_block(styles) or None
        if key == "signatures":
            return self._signatures_block(styles, with_date=True)
        return None

    def _draw_canvas_act(
        self,
        c,
        device: dict[str, Any],
        act_type: str,
        origin_x_pt: float,
        origin_y_pt: float,
        scale: float = 1.0,
    ) -> None:
        """Рисует все canvas-боксы акта на низкоуровневом reportlab Canvas.

        origin_x_pt/origin_y_pt — левый нижний угол страницы A5 в абсолютных
        координатах ЦЕЛЕВОЙ страницы (0,0 для одиночного акта; для парного
        A4-листа — граница верхней/нижней половины); scale позволяет
        уместить A5-макет в меньшую область (парный акт делит A4 пополам)
        без переписывания координат самих боксов.
        """
        styles = self._styles()
        layout = self._canvas_fields() or self.default_canvas_layout(act_type)
        c.saveState()
        c.translate(origin_x_pt, origin_y_pt)
        c.scale(scale, scale)
        for key, cfg in layout.items():
            if key in CANVAS_COMPOSITE_FIELDS and act_type not in CANVAS_COMPOSITE_FIELDS[key]["act_types"]:
                continue
            if cfg.get("visible") is False:
                continue
            flowable = self._build_canvas_flowable(key, device, styles, act_type)
            if flowable is None:
                continue
            if isinstance(flowable, list):
                if not flowable:
                    continue
                from reportlab.platypus import KeepInFrame

                width_pt = float(cfg.get("w_mm", 60)) * MM_TO_PT
                flowable = KeepInFrame(
                    width_pt, 4000, flowable, mode="shrink", hAlign="LEFT"
                )
            width_pt = float(cfg.get("w_mm", 60)) * MM_TO_PT
            try:
                # wrapOn() (не голый wrap()) обязателен для составных блоков:
                # KeepInFrame.wrap() лезет в self.canv, который выставляет
                # только wrapOn() — на простом Paragraph/Table разницы нет
                # (Flowable.wrapOn — это просто self.canv=canv; return
                # self.wrap(...)), так что безопасно использовать для всех.
                _w, h = flowable.wrapOn(c, width_pt, 4000)
            except Exception as e:
                logger.warning(f"Не удалось измерить canvas-бокс '{key}': {e}")
                continue
            x_pt = float(cfg.get("x_mm", 0)) * MM_TO_PT
            y_top_pt = float(cfg.get("y_mm", 0)) * MM_TO_PT
            y_pt = A5[1] - y_top_pt - h
            try:
                flowable.drawOn(c, x_pt, y_pt)
            except Exception as e:
                logger.warning(f"Не удалось отрисовать canvas-бокс '{key}': {e}")
        c.restoreState()

    def _build_canvas_pdf(self, filepath: str, device: dict[str, Any], act_type: str) -> bool:
        from reportlab.pdfgen import canvas as pdfcanvas

        c = pdfcanvas.Canvas(filepath, pagesize=A5)
        c.setTitle("Акт")
        c.setAuthor(self.company.get("name", "Сервисный центр"))
        self._draw_canvas_act(c, device, act_type, origin_x_pt=0, origin_y_pt=0, scale=1.0)
        c.save()
        return True

    def generate_dual_pdf(
        self,
        filepath: str,
        device1: dict[str, Any],
        device2: dict[str, Any] | None = None,
        act_type1: str = "receipt",
        act_type2: str = "completion",
        template_data2: dict[str, Any] | None = None,
    ) -> bool:
        """Генерирует PDF с двумя актами на одном листе A4 (каждый A5).

        Параметры:
            device1, device2 — данные заказов для актов (device2=None → один акт).
            act_type1, act_type2 — 'receipt' или 'completion' для каждого акта.
                По умолчанию: receipt (верх) + completion (низ).
                Для двух одинаковых: act_type1='receipt', act_type2='receipt'.
            template_data2 — шаблон ВТОРОГО акта, если он отличается от типа
                первого (act_type1 != act_type2) — акт приёма и акт
                выполненных работ настраиваются в редакторе НЕЗАВИСИМО
                (разный header_text/fields/warranty_text, см.
                reports/report_editor.py::_DEFAULT_TEMPLATES), поэтому
                смешанная пара "приём+работы" не может честно рендериться из
                одного self.template. Если не передан, акт 2 рендерится тем
                же генератором/шаблоном, что и акт 1 (старое поведение —
                корректно, когда act_type1 == act_type2).
        """
        gen2 = (
            ActPDFGenerator(self.company, template_data=template_data2)
            if template_data2 is not None
            else self
        )
        canvas_mode = (
            self.template.get("layout_mode") == "canvas"
            or gen2.template.get("layout_mode") == "canvas"
        )
        if canvas_mode:
            return self._generate_dual_pdf_canvas(
                filepath, device1, device2, act_type1, act_type2, gen2
            )
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

            def _build_story(gen: ActPDFGenerator, device, act_type):
                """Выбирает нужный story по типу акта, из указанного генератора
                (у каждого — свой self.template)."""
                if act_type == "completion":
                    return gen._build_completion_story(device)
                return gen._build_receipt_story(device)

            story = []
            # Акт 1
            story1 = _build_story(self, device1, act_type1)
            story.append(KeepInFrame(content_w, half_h, story1, mode="shrink"))
            story.append(Spacer(1, 8))

            # Акт 2 (если есть)
            if device2:
                story2 = _build_story(gen2, device2, act_type2)
                story.append(KeepInFrame(content_w, half_h, story2, mode="shrink"))

            doc.build(story)
            return True
        except Exception as e:
            logger.error(f"Ошибка генерации двойного акта (PDF): {e}", exc_info=True)
            return False

    def _generate_dual_pdf_canvas(
        self,
        filepath: str,
        device1: dict[str, Any],
        device2: dict[str, Any] | None,
        act_type1: str,
        act_type2: str,
        gen2: ActPDFGenerator,
    ) -> bool:
        """Парный акт (A4, два A5 друг под другом), когда хотя бы один из
        актов использует свободный макет (canvas). Каждый акт рисуется
        своим генератором (свой template/layout_mode — flow ИЛИ canvas)
        через общий _draw_canvas_act(), отмасштабированный в свою половину
        листа — так пара работает даже если один акт canvas, а другой flow."""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas as pdfcanvas
            from reportlab.platypus import KeepInFrame

            a4_w, a4_h = A4
            content_w = a4_w - 2 * self.margin
            half_h = (a4_h - 2 * self.margin) / 2 - 10
            scale = min(content_w / A5[0], half_h / A5[1])

            c = pdfcanvas.Canvas(filepath, pagesize=A4)
            c.setTitle("Акты")
            c.setAuthor(self.company.get("name", "Сервисный центр"))

            def _draw_slot(gen: ActPDFGenerator, device, act_type, origin_y_pt):
                if gen.template.get("layout_mode") == "canvas":
                    gen._draw_canvas_act(
                        c, device, act_type, self.margin, origin_y_pt, scale
                    )
                else:
                    story = (
                        gen._build_completion_story(device)
                        if act_type == "completion"
                        else gen._build_receipt_story(device)
                    )
                    frame = KeepInFrame(content_w, half_h, story, mode="shrink")
                    frame.wrapOn(c, content_w, half_h)
                    frame.drawOn(c, self.margin, origin_y_pt)

            top_origin_y = a4_h - self.margin - half_h
            _draw_slot(self, device1, act_type1, top_origin_y)
            if device2:
                bottom_origin_y = top_origin_y - half_h - 8
                _draw_slot(gen2, device2, act_type2, bottom_origin_y)

            c.save()
            return True
        except Exception as e:
            logger.error(f"Ошибка генерации двойного акта (canvas, PDF): {e}", exc_info=True)
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
            logger.error(f"Не удалось вставить логотип: {e}", exc_info=True)
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
        story.extend(self._defect_block(device, styles))
        story.extend(self._price_block(device, styles))
        story.extend(self._conditions_block(styles))
        story.extend(self._signatures_block(styles, with_date=True))
        return story

    def _defect_block(self, device: dict[str, Any], styles) -> list:
        """Блок «Неисправность со слов клиента» — акцентный блок с рамкой.

        Показывается, если defect отмечен в шаблоне (или шаблона нет — дефолт).
        Используется и проточной вёрсткой, и свободным макетом (canvas) —
        общий метод, чтобы визуально они не расходились.
        """
        template_fields = self.template.get("fields") or []
        show_defect = (not template_fields) or ("defect" in template_fields)
        if not show_defect:
            return []
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
        return [
            Spacer(1, 3),
            Paragraph("Неисправность со слов клиента", styles["section"]),
            defect_tbl,
        ]

    def _price_block(self, device: dict[str, Any], styles) -> list:
        """Предварительная стоимость — акцентный блок, если total_price отмечен."""
        total = device.get("total_price", "")
        template_fields = self.template.get("fields") or []
        show_price = (not template_fields) or ("total_price" in template_fields)
        if not (total and show_price):
            return []
        prepay = device.get("prepayment", "")
        price_line = f"Стоимость ремонта — {format_price(total)}"
        if parse_price_to_float(prepay) > 0:
            price_line += f"  (предоплата {format_price(_prepayment_to_str(prepay))})"
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
        return [Spacer(1, 3), price_tbl]

    def _conditions_block(self, styles) -> list:
        """Условия ремонта из шаблона (если есть)."""
        conditions = self.template.get("conditions", "")
        if not conditions:
            return []
        cond_lines = [
            [Paragraph(xml_escape(line.strip()), styles["note_text"])]
            for line in conditions.split("\n")
            if line.strip()
        ]
        if not cond_lines:
            return []
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
        return [
            Spacer(1, 3),
            Paragraph("Условия ремонта", styles["section"]),
            cond_tbl,
        ]

    # ------------------------------------------------------------------
    # Акт выполненных работ
    # ------------------------------------------------------------------

    def _build_completion_story(self, device: dict[str, Any]) -> list:
        from reportlab.platypus import Paragraph, Spacer

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

        story.extend(self._warranty_block(styles))
        story.extend(self._qr_block(styles))
        story.extend(self._signatures_block(styles, with_date=True))
        return story

    def _warranty_block(self, styles) -> list:
        """Гарантийные обязательства из шаблона (если есть)."""
        warranty_text = self.template.get("warranty_text", "")
        if not warranty_text:
            return []
        war_lines = [
            [Paragraph(xml_escape(line.strip()), styles["note_text"])]
            for line in warranty_text.split("\n")
            if line.strip()
        ]
        if not war_lines:
            return []
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
        return [
            Spacer(1, 3),
            Paragraph("Гарантийные обязательства", styles["section"]),
            war_tbl,
        ]

    def _qr_block(self, styles) -> list:
        """QR-код из шаблона (если включён)."""
        qr_path = self.template.get("qr_path", "")
        if not (self.template.get("show_qr", False) and qr_path):
            return []
        png = _prepare_image(qr_path)
        if not png:
            return []
        try:
            from reportlab.platypus import Image as RLImage

            qr_img = RLImage(png, width=40, height=40, kind="proportional")
            qr_img.hAlign = "CENTER"
            return [Spacer(1, 4), qr_img]
        except Exception:
            return []

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
