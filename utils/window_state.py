#!/usr/bin/env python3

"""Сохранение/восстановление геометрии окон в config-файле.

Геометрия каждого окна хранится в настройках по ключу
``window_geometry.<window_key>`` в формате Tk: ``"WxH+X+Y"``.

Использование в диалоге (CTkToplevel)::

    from utils.window_state import restore_window_geometry, save_window_geometry

    class MyDialog(ctk.CTkToplevel):
        def __init__(self, parent, settings, ...):
            ...
            restore_window_geometry(settings, "my_dialog", self,
                                    default_w=600, default_h=400)
            # при закрытии — сохранить
            self.protocol("WM_DELETE_WINDOW", self._on_close)

        def _on_close(self):
            save_window_geometry(self.settings, "my_dialog", self)
            self.destroy()

Все размеры ограничиваются габаритами текущего экрана, чтобы окно всегда
помещалось (важно для 1280x720 и при смене монитора).
"""

import contextlib
import logging
import re

logger = logging.getLogger(__name__)

# Ключ в настройках, под которым хранятся все геометрии окон
GEOMETRY_KEY = "window_geometry"

_GEOMETRY_RE = re.compile(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$")


def _parse_geometry(geo: str):
    """Разбирает 'WxH+X+Y' -> (w, h, x, y) или None."""
    if not geo:
        return None
    m = _GEOMETRY_RE.match(str(geo).strip())
    if not m:
        return None
    try:
        return int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    except (ValueError, TypeError):
        return None


def _screen_size(window) -> tuple:
    """Возвращает (screen_width, screen_height) безопасно."""
    try:
        return window.winfo_screenwidth(), window.winfo_screenheight()
    except Exception:
        return 1920, 1080


def restore_window_geometry(
    settings,
    window_key: str,
    window,
    default_w: int = 800,
    default_h: int = 600,
    min_w: int | None = None,
    min_h: int | None = None,
) -> None:
    """Восстанавливает геометрию окна из настроек или применяет дефолт.

    Ограничивает размер экраном и центрирует при первом запуске.
    Должна вызываться ПОСЛЕ создания окна, но ДО pack/grid виджетов.
    """
    sw, sh = _screen_size(window)

    # Ограничиваем дефолтные размеры экраном
    default_w = min(default_w, sw)
    default_h = min(default_h, sh)

    saved = None
    try:
        saved_geo = settings.get(f"{GEOMETRY_KEY}.{window_key}", "")
        saved = _parse_geometry(saved_geo)
    except Exception:
        pass

    if saved:
        w, h, x, y = saved
        # Ограничиваем сохранённые размеры текущим экраном (монитор мог смениться)
        w = min(w, sw)
        h = min(h, sh)
        # Корректируем позицию, чтобы окно не уехало за пределы экрана
        x = max(0, min(x, sw - w))
        y = max(0, min(y, sh - h))
    else:
        # Центрируем на экране
        w, h = default_w, default_h
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2 - 20)

    with contextlib.suppress(Exception):
        window.geometry(f"{w}x{h}+{x}+{y}")

    if min_w is not None or min_h is not None:
        with contextlib.suppress(Exception):
            window.minsize(min_w or 100, min_h or 100)


def save_window_geometry(settings, window_key: str, window) -> None:
    """Сохраняет текущую геометрию окна в настройки.

    Должна вызываться ПЕРЕД destroy() — иначе winfo_* вернёт 1x1.
    """
    try:
        geo = window.geometry()
        # Нормализуем: Tk может вернуть 'WxH+X+Y' или 'WxH'
        if "+" not in geo:
            # Нет позиции — добавим текущую
            x = window.winfo_x()
            y = window.winfo_y()
            geo = f"{geo}+{x}+{y}"
        settings.set(f"{GEOMETRY_KEY}.{window_key}", geo)
    except Exception as e:
        logger.warning(f"Не удалось сохранить геометрию окна {window_key}: {e}")


def fit_window_to_screen(
    window,
    default_w: int,
    default_h: int,
    min_w: int,
    min_h: int,
    width_ratio: float = 0.92,
    height_ratio: float = 0.92,
) -> None:
    """Подбирает размер окна под текущий экран и центрирует его.

    Общая реализация для ``_fit_window``, ранее независимо продублированного
    в act_preview.py (width_ratio=0.55) и report_editor.py (width_ratio=0.96)
    с идентичной логикой при разных ratio, см. AUDIT_REPORT_v21.md.
    """
    sw, sh = _screen_size(window)
    w = min(default_w, int(sw * width_ratio))
    h = min(default_h, int(sh * height_ratio))
    w = max(min_w, min(w, sw))
    h = max(min_h, min(h, sh))
    x = (sw - w) // 2
    y = max(0, (sh - h) // 2 - 20)
    with contextlib.suppress(Exception):
        window.geometry(f"{w}x{h}+{x}+{y}")
        window.minsize(min_w, min_h)


def close_dialog_with_geometry(dialog, settings, window_key: str) -> None:
    """Сохраняет геометрию окна и закрывает диалог — общая реализация для
    ``_close_with_geometry``, которая раньше была независимо продублирована
    в 8 диалогах (settings/dictionaries/device_form/client_history/
    report_editor/work_item_dialog/photo_viewer/act_preview), см.
    AUDIT_REPORT_v21.md. Каждый диалог по-прежнему определяет свой
    ``_close_with_geometry`` (это Tk-колбэк, привязанный к кнопке/протоколу
    закрытия), но тело метода теперь делегирует сюда.
    """
    with contextlib.suppress(Exception):
        save_window_geometry(settings, window_key, dialog)
    dialog.destroy()
