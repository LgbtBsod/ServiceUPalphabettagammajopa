#!/usr/bin/env python3
"""WindowMixin — окно верхнего уровня: геометрия, полноэкранный режим,
тема, часы, статус-бар. См. AUDIT_REPORT_v25.md, Task T (перенесено из
main_window.py без изменения поведения)."""

from __future__ import annotations

import contextlib
from datetime import datetime

import customtkinter as ctk

from utils.colors import get_colors
from utils.window_effects import apply_rounded_corners


class WindowMixin:
    """Требует от финального класса ServiceCenterApp: self.settings,
    self.theme, self.colors, self.root (root создаётся здесь же, в
    setup_main_window)."""

    def setup_main_window(self):
        """Настройка главного окна"""
        self.root = ctk.CTk()
        self.root.title("Сервисный центр - Учет ремонта техники")

        with contextlib.suppress(Exception):
            self.root.iconbitmap("icon.ico")

        width = self.settings.get("window_width", 1400)
        height = self.settings.get("window_height", 800)
        x = self.settings.get("window_x")
        y = self.settings.get("window_y")

        # Ограничиваем сохранённый/дефолтный размер габаритами экрана,
        # чтобы окно всегда помещалось (важно для 1280x720).
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            width = min(width, sw)
            height = min(height, sh)
        except Exception:
            pass

        if x is not None and y is not None:
            # Корректируем позицию, чтобы окно не уезжало за экран
            try:
                sw = self.root.winfo_screenwidth()
                sh = self.root.winfo_screenheight()
                x = max(0, min(int(x), sw - int(width)))
                y = max(0, min(int(y), sh - int(height)))
            except Exception:
                pass
            self.root.geometry(f"{width}x{height}+{x}+{y}")
        else:
            self.root.geometry(f"{width}x{height}")
            self.root.update_idletasks()
            width = self.root.winfo_width()
            height = self.root.winfo_height()
            x = (self.root.winfo_screenwidth() // 2) - (width // 2)
            y = (self.root.winfo_screenheight() // 2) - (height // 2)
            self.root.geometry(f"{width}x{height}+{x}+{y}")

        self.root.minsize(1000, 600)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.bind("<Configure>", self.on_window_configure)

        # Прозрачность отключена по запросу — только скругление углов окна
        with contextlib.suppress(Exception):
            apply_rounded_corners(self.root)

    def on_window_configure(self, event):
        """Обработка изменения размера окна"""
        if event.widget == self.root and self.root.state() == "normal":
            self.settings.set("window_width", event.width)
            self.settings.set("window_height", event.height)
            self.settings.set("window_x", event.x)
            self.settings.set("window_y", event.y)

    def toggle_fullscreen(self, fullscreen: bool | None = None):
        """Переключение полноэкранного режима"""
        if fullscreen is not None:
            self.root.attributes("-fullscreen", fullscreen)
            self.settings.set("fullscreen", fullscreen)
        else:
            current = self.root.attributes("-fullscreen")
            self.root.attributes("-fullscreen", not current)
            self.settings.set("fullscreen", not current)

    def update_theme(self, theme: str):
        """Обновление темы"""
        self.theme = theme
        self.colors = get_colors(theme, self.settings.get("accent_color", "#0078d4"))
        ctk.set_appearance_mode("dark" if theme == "dark" else "light")
        self.refresh_ui()

    def update_datetime(self):
        """Обновление времени"""
        try:
            now = datetime.now().strftime("%d.%m.%Y %H:%M")
            self.datetime_label.configure(text=now)
            self.root.after(1000, self.update_datetime)
        except Exception:
            pass

    def update_status_bar(self, message: str):
        """Обновление статусной строки"""
        with contextlib.suppress(Exception):
            self.status_label.configure(text=f"✅ {message}")
