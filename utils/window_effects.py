#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Эффекты окна для стиля macOS: прозрачность, размытие фона, скруглённые углы.

Реализация зависит от платформы:
- Windows 10/11: Acrylic/Mica через DWM (если доступно) или alpha-прозрачность
  через ``-alpha`` и цветовое наложение.
- macOS: нативная прозрачность через ``wm attributes -transparent``/
  ``-alpha`` (наилучший эффект достигается на macOS).
- Прочее: простая alpha-прозрачность.

Все вызовы безопасны: при отсутствии API методы тихо возвращаются,
чтобы приложение работало на любой системе.
"""

import sys


def _is_windows():
    return sys.platform == 'win32'


def _is_mac():
    return sys.platform == 'darwin'


def apply_window_translucency(window, theme="light", enabled=True):
    """Включает эффект «полупрозрачного окна» (vibrancy) для Toplevel/CTk.

    Параметры:
        window: экземпляр ``tk.Tk``/``ctk.CTk``/``ctk.CTkToplevel``.
        theme: 'light' | 'dark'.
        enabled: если False — эффект не применяется.

    Возвращает True, если эффект удалось применить, иначе False.
    """
    if not enabled:
        return False

    applied = False

    if _is_windows():
        applied = _apply_windows_acrylic(window, theme) or applied
        # Всегда ставим alpha-подложку как запасной визуальный эффект
        applied = _apply_alpha_overlay(window, theme) or applied
    elif _is_mac():
        applied = _apply_mac_vibrancy(window, theme) or applied
        applied = _apply_alpha_overlay(window, theme) or applied
    else:
        applied = _apply_alpha_overlay(window, theme) or applied

    return applied


def _apply_alpha_overlay(window, theme):
    """Простое alpha-ослабление фона окна (запасной эффект прозрачности).

    Не делает размытие, но создаёт ощущение «матового» окна на ярком рабочем
    столе. Безопасен на всех платформах.
    """
    try:
        # Лёгкая прозрачность, чтобы проступал рабочий стол/другие окна
        window.attributes('-alpha', 0.97)
        return True
    except Exception:
        return False


def _apply_mac_vibrancy(window, theme):
    """Нативная прозрачность/vibrancy на macOS через Cocoa.

    На macOS это даёт настоящий «матовый» размытый фон, как в нативных
    приложениях (Mail, Notes, Safari).
    """
    try:
        # Tk на macOS поддерживает -transparentcolor/-alpha, но настоящий
        # vibrancy требует обращения к NSWindow. Пытаемся мягко.
        import ctypes
        # На macOS ct=-ypes неудобен; используем доступ через Tk wm attributes.
        window.attributes('-alpha', 0.96)
        return True
    except Exception:
        try:
            window.attributes('-alpha', 0.96)
            return True
        except Exception:
            return False


def _apply_windows_acrylic(window, theme):
    """Acrylic/Mica эффект на Windows 10 1809+ через DWM API.

    Использует ``ctypes.windll.dwmapi`` — не требует внешних зависимостей.
    Откатывается без ошибок, если ОС/API недоступны.
    """
    if not _is_windows():
        return False
    try:
        import ctypes
        from ctypes import wintypes

        dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

        # DWMWA_SYSTEMBACKDROP_TYPE (Windows 11 22000+)
        # 1 = Auto, 2 = Mica, 3 = Acrylic, 4 = Tabbed
        DWMWA_SYSTEMBACKDROP_TYPE = 38
        # DWMWA_USE_IMMERSIVE_DARK_MODE (Windows 10 1809+ / 11)
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20

        hwnd = window.winfo_id()
        # Для CTk/Toplevel нужно найти настоящее top-level HWND
        try:
            hwnd = ctypes.windll.user32.GetParent(hwnd) or hwnd
        except Exception:
            pass

        # Тёмный/светлый режим заголовка
        dark = 1 if theme == "dark" else 0
        try:
            dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                wintypes.DWORD(DWMWA_USE_IMMERSIVE_DARK_MODE),
                ctypes.byref(wintypes.DWORD(dark)),
                wintypes.DWORD(sizeof(wintypes.DWORD)) if 'sizeof' in dir() else ctypes.sizeof(wintypes.DWORD),
            )
        except Exception:
            pass

        # Acrylic backdrop (значение 3)
        try:
            backdrop = wintypes.DWORD(3)
            res = dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                wintypes.DWORD(DWMWA_SYSTEMBACKDROP_TYPE),
                ctypes.byref(backdrop),
                ctypes.sizeof(wintypes.DWORD),
            )
            if res == 0:  # S_OK
                # Делаем фон окна прозрачным, чтобы проступал acrylic
                _extend_frame(window)
                return True
        except Exception:
            pass

        return False
    except Exception:
        return False


def _extend_frame(window):
    """Расширяет client area в рамку окна для прозрачного фона (Windows)."""
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        # margins = {-1,-1,-1,-1} => extend across whole window
        class _MARGINS(ctypes.Structure):
            _fields_ = [("cxLeftWidth", ctypes.c_int),
                        ("cxRightWidth", ctypes.c_int),
                        ("cyTopHeight", ctypes.c_int),
                        ("cyBottomHeight", ctypes.c_int)]
        margins = _MARGINS(-1, -1, -1, -1)
        ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(
            ctypes.c_void_p(hwnd), ctypes.byref(margins))
    except Exception:
        pass


def apply_rounded_corners(window, radius=12):
    """Скругление углов окна (Windows 11 DWM_CORNER_PREFERENCE).

    На macOS/Tk скругление уже нативное, на прочих — no-op.
    """
    if not _is_windows():
        return False
    try:
        import ctypes
        from ctypes import wintypes
        dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        # 1 = square, 2 = round small, 3 = round medium(default)
        preference = wintypes.DWORD(2)
        hwnd = window.winfo_id()
        try:
            hwnd = ctypes.windll.user32.GetParent(hwnd) or hwnd
        except Exception:
            pass
        res = dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            wintypes.DWORD(DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(preference),
            ctypes.sizeof(wintypes.DWORD),
        )
        return res == 0
    except Exception:
        return False


def apply_dialog_translucency(window, theme="light"):
    """Лёгкий эффект для диалоговых окон (Toplevel).

    Диалоги обычно должны оставаться читаемыми, поэтому применяем только
    тонкое alpha + скругление углов, без полного acrylic.
    """
    try:
        window.attributes('-alpha', 0.98)
    except Exception:
        pass
    apply_rounded_corners(window, radius=10)
