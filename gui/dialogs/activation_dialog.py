#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Окно активации лицензии.

Показывается при истечении пробного периода или при ручном запуске.
Содержит HWID (с копированием), поле ввода ключа и информацию о триале.
"""

import customtkinter as ctk
from tkinter import messagebox

from gui.widgets.modern import ModernCard, ModernButton, ModernLabel, ModernEntry


class ActivationDialog(ctk.CTkToplevel):
    """Диалог активации лицензии."""

    def __init__(self, parent, license_manager, colors: dict = None):
        super().__init__(parent)
        self.parent = parent
        self.lic = license_manager
        self.colors = colors or {
            'bg_primary': '#f5f5f7',
            'bg_secondary': '#ffffff',
            'bg_tertiary': '#ececef',
            'bg_hover': '#e5e5ea',
            'accent': '#007aff',
            'accent_hover': '#0051d5',
            'text_primary': '#1d1d1f',
            'text_secondary': '#6e6e73',
            'border': '#d1d1d6',
            'success': '#34c759',
            'error': '#ff3b30',
        }
        self.activated = False

        self.title("🔐 Активация ServiceUP")
        self.geometry("480x580")
        self.minsize(420, 520)
        self.transient(parent)
        self.grab_set()

        # Центрируем
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - 480) // 2
        y = max(0, (sh - 580) // 2 - 30)
        self.geometry(f"+{x}+{y}")

        self.create_widgets()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def create_widgets(self):
        """Создание интерфейса."""
        main = ctk.CTkFrame(self, fg_color=self.colors['bg_primary'])
        main.pack(fill="both", expand=True, padx=15, pady=15)

        # Иконка + заголовок
        ctk.CTkLabel(main, text="🔐", font=ctk.CTkFont(size=40)).pack(pady=(10, 5))

        # Безопасная проверка лицензии
        try:
            status = self.lic.check_license()
        except Exception:
            status = 'error'
        try:
            days_left = self.lic.get_trial_days_left()
        except Exception:
            days_left = 0

        if status == 'activated':
            header = "Программа активирована"
            subtext = "Лицензия активна на этом устройстве"
            header_color = self.colors['success']
        elif status == 'trial_active':
            header = f"Пробный период: {days_left} дн."
            subtext = f"Осталось {days_left} дней пробного периода"
            header_color = self.colors['accent'] if days_left > 3 else self.colors.get('error', '#ff3b30')
        elif status == 'corrupted':
            header = "⚠️ Нарушение целостности"
            subtext = "Обнаружен откат системного времени. Требуется активация."
            header_color = self.colors.get('error', '#ff3b30')
        elif status == 'error':
            header = "⚠️ Ошибка проверки"
            subtext = "Не удалось проверить лицензию. Введите ключ вручную."
            header_color = self.colors.get('error', '#ff3b30')
        else:
            header = "Пробный период истёк"
            subtext = "Введите ключ активации для продолжения работы"
            header_color = self.colors.get('error', '#ff3b30')

        ctk.CTkLabel(main, text=header,
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=header_color).pack(pady=(5, 2))

        ctk.CTkLabel(main, text=subtext,
                     font=ctk.CTkFont(size=12),
                     text_color=self.colors['text_secondary']).pack(pady=(0, 15))

        # Карточка с HWID
        hwid_card = ModernCard(main, self.colors)
        hwid_card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(hwid_card, text="🆔 ID устройства (HWID)",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=self.colors['accent']).pack(anchor="w", padx=12, pady=(8, 4))

        hwid = self.lic.get_hwid()
        hwid_frame = ctk.CTkFrame(hwid_card, fg_color="transparent")
        hwid_frame.pack(fill="x", padx=12, pady=(0, 8))

        self.hwid_label = ctk.CTkLabel(hwid_frame, text=hwid,
                                       font=ctk.CTkFont(size=15, weight="bold"),
                                       text_color=self.colors['text_primary'])
        self.hwid_label.pack(side="left", padx=(0, 8))

        ModernButton(hwid_frame, self.colors, variant="secondary", text="📋 Копировать",
                     command=self._copy_hwid, height=30, width=100).pack(side="left")

        # Инструкция
        ctk.CTkLabel(main,
                     text="📋 Отправьте HWID разработчику,\nполучите ключ активации и введите его ниже:",
                     font=ctk.CTkFont(size=11),
                     text_color=self.colors['text_secondary'],
                     justify="left").pack(anchor="w", pady=(5, 8), padx=15)

        # Поле ввода ключа
        key_card = ModernCard(main, self.colors)
        key_card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(key_card, text="🔑 Ключ активации",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=self.colors['accent']).pack(anchor="w", padx=12, pady=(8, 4))

        self.key_entry = ctk.CTkEntry(key_card, width=350, height=38,
                                      placeholder_text="XXXX-XXXX-XXXX-XXXX",
                                      font=ctk.CTkFont(size=16),
                                      justify="center",
                                      fg_color=self.colors['bg_tertiary'],
                                      border_color=self.colors['border'],
                                      border_width=1)
        self.key_entry.pack(fill="x", padx=12, pady=(0, 8))

        # Кнопка активации
        ModernButton(key_card, self.colors, variant="primary", text="✅ Активировать",
                     command=self._try_activate, height=38).pack(fill="x", padx=12, pady=(0, 8))

        # Кнопки внизу
        btn_frame = ctk.CTkFrame(main, fg_color="transparent")
        btn_frame.pack(fill="x", side="bottom", pady=(5, 0))

        if status == 'trial_active':
            ModernButton(btn_frame, self.colors, variant="secondary", text="Продолжить пробный период",
                         command=self._continue_trial, height=36).pack(side="left", fill="x", expand=True, padx=2)
        elif status == 'activated':
            ModernButton(btn_frame, self.colors, variant="secondary", text="✖ Закрыть",
                         command=self._on_close, height=36).pack(side="left", fill="x", expand=True, padx=2)
        else:
            ModernButton(btn_frame, self.colors, variant="secondary", text="✖ Закрыть",
                         command=self._on_close, height=36).pack(side="left", fill="x", expand=True, padx=2)

    def _copy_hwid(self):
        """Копирует HWID в буфер обмена."""
        try:
            self.clipboard_clear()
            self.clipboard_append(self.lic.get_hwid())
            messagebox.showinfo("Скопировано", "HWID скопирован в буфер обмена!")
        except Exception:
            pass

    def _try_activate(self):
        """Пытается активировать лицензию."""
        key = self.key_entry.get().strip()
        if not key:
            messagebox.showwarning("Внимание", "Введите ключ активации")
            return

        if self.lic.activate(key):
            self.activated = True
            messagebox.showinfo("Успех", "✅ Программа успешно активирована!\nСпасибо за покупку!")
            self.destroy()
        else:
            messagebox.showerror("Ошибка",
                                 "❌ Неверный ключ активации.\n"
                                 "Проверьте правильность ввода и HWID.")

    def _continue_trial(self):
        """Закрывает окно, продолжая пробный период."""
        self.destroy()

    def _on_close(self):
        """Закрытие окна."""
        self.destroy()
