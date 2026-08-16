#!/usr/bin/env python3

"""Окно настроек приложения"""

import logging
from tkinter import colorchooser, messagebox

import customtkinter as ctk

from domain.constants import PRIORITIES, STATUSES

logger = logging.getLogger(__name__)


class SettingsWindow(ctk.CTkToplevel):
    """Окно настроек"""

    def __init__(self, parent, settings_manager, app):
        super().__init__(parent)
        self.parent = parent
        self.settings = settings_manager
        self.app = app
        self.selected_color = self.settings.get("accent_color", "#0078d4")

        self.title("Настройки")
        from utils.window_state import restore_window_geometry

        restore_window_geometry(
            self.settings,
            "settings",
            self,
            default_w=800,
            default_h=600,
            min_w=700,
            min_h=500,
        )

        self.transient(parent)
        self.grab_set()

        # Сохраняем геометрию при закрытии
        self.protocol("WM_DELETE_WINDOW", self._close_with_geometry)

        self.create_widgets()

    def _close_with_geometry(self):
        """Сохраняет геометрию окна в config и закрывает его."""
        from utils.window_state import close_dialog_with_geometry

        close_dialog_with_geometry(self, self.settings, "settings")

    def create_widgets(self):
        """Создание виджетов"""
        # Основной контейнер
        main_frame = ctk.CTkFrame(self, fg_color=self.app.colors["bg_primary"])
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Заголовок
        title_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            title_frame,
            text="⚙️ Настройки приложения",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.app.colors["accent"],
        ).pack(side="left")

        # Создаем вкладки
        self.tabview = ctk.CTkTabview(main_frame)
        self.tabview.pack(fill="both", expand=True, pady=10)

        # Вкладка "Общие"
        self.general_tab = self.tabview.add("Общие")
        self.create_general_tab()

        # Вкладка "Внешний вид"
        self.appearance_tab = self.tabview.add("Внешний вид")
        self.create_appearance_tab()

        # Вкладка "База данных"
        self.db_tab = self.tabview.add("База данных")
        self.create_db_tab()

        # Вкладка "Мобильная версия (PWA)"
        self.pwa_tab = self.tabview.add("📱 Мобильная версия")
        self.create_pwa_tab()

        # Кнопки внизу
        buttons_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        buttons_frame.pack(fill="x", pady=(10, 0))

        ctk.CTkButton(
            buttons_frame,
            text="Сохранить",
            command=self.save_settings,
            width=100,
            height=35,
            corner_radius=6,
            fg_color=self.app.colors["accent"],
            hover_color=self.app.colors["accent_hover"],
        ).pack(side="right", padx=5)

        ctk.CTkButton(
            buttons_frame,
            text="Отмена",
            command=self.destroy,
            width=100,
            height=35,
            corner_radius=6,
            fg_color=self.app.colors["bg_tertiary"],
            text_color=self.app.colors["text_primary"],
            hover_color=self.app.colors["bg_hover"],
            border_width=1,
            border_color=self.app.colors["border"],
        ).pack(side="right", padx=5)

        ctk.CTkButton(
            buttons_frame,
            text="Сбросить",
            command=self.reset_settings,
            width=100,
            height=35,
            corner_radius=6,
            fg_color="#d13438",
            text_color="white",
            hover_color="#b32d30",
        ).pack(side="right", padx=5)

    def create_general_tab(self):
        """Создание вкладки общих настроек"""
        scroll = ctk.CTkScrollableFrame(self.general_tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # Поведение
        behavior_frame = self.create_section(scroll, "Поведение")

        self.confirm_delete_var = ctk.BooleanVar(
            value=self.settings.get("confirm_delete", True)
        )
        ctk.CTkCheckBox(
            behavior_frame,
            text="Подтверждать удаление",
            variable=self.confirm_delete_var,
            fg_color=self.app.colors["accent"],
        ).pack(anchor="w", pady=3)

        self.confirm_exit_var = ctk.BooleanVar(
            value=self.settings.get("confirm_exit", False)
        )
        ctk.CTkCheckBox(
            behavior_frame,
            text="Подтверждать выход",
            variable=self.confirm_exit_var,
            fg_color=self.app.colors["accent"],
        ).pack(anchor="w", pady=3)

        # "Авто-сохранение при закрытии" сознательно убрано (не просто не
        # реализовано) — в приложении нет понятия "черновик"/несохранённые
        # изменения формы: каждый Save в device_form.py и т.п. сразу и
        # безусловно пишет в БД, отменить нечего. Настройка обещала бы
        # поведение, для которого в архитектуре приложения нет объекта
        # применения, см. AUDIT_REPORT_v25.md.

        # Значения по умолчанию
        defaults_frame = self.create_section(scroll, "Значения по умолчанию")

        ctk.CTkLabel(defaults_frame, text="Статус по умолчанию:").pack(
            anchor="w", pady=(0, 3)
        )
        self.default_status_combo = ctk.CTkComboBox(
            defaults_frame,
            values=STATUSES,
            state="readonly",
            fg_color=self.app.colors["bg_tertiary"],
        )
        self.default_status_combo.set(
            self.settings.get("default_status", "Диагностика")
        )
        self.default_status_combo.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(defaults_frame, text="Приоритет по умолчанию:").pack(
            anchor="w", pady=(0, 3)
        )
        self.default_priority_combo = ctk.CTkComboBox(
            defaults_frame,
            values=PRIORITIES,
            state="readonly",
            fg_color=self.app.colors["bg_tertiary"],
        )
        self.default_priority_combo.set(
            self.settings.get("default_priority", "Обычный")
        )
        self.default_priority_combo.pack(fill="x", pady=(0, 10))

        # Уведомления
        notify_frame = self.create_section(scroll, "Уведомления")

        self.remind_overdue_var = ctk.BooleanVar(
            value=self.settings.get("remind_overdue", True)
        )
        ctk.CTkCheckBox(
            notify_frame,
            text="Напоминать о просроченных заказах",
            variable=self.remind_overdue_var,
            fg_color=self.app.colors["accent"],
        ).pack(anchor="w", pady=3)

        days_frame = ctk.CTkFrame(notify_frame, fg_color="transparent")
        days_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(days_frame, text="Порог просрочки (дней):").pack(side="left")
        self.overdue_days_entry = ctk.CTkEntry(days_frame, width=60)
        self.overdue_days_entry.insert(0, str(self.settings.get("overdue_days", 14)))
        self.overdue_days_entry.pack(side="right")

        self.notify_ready_var = ctk.BooleanVar(
            value=self.settings.get("notify_on_ready", True)
        )
        ctk.CTkCheckBox(
            notify_frame,
            text="Уведомлять о готовности",
            variable=self.notify_ready_var,
            fg_color=self.app.colors["accent"],
        ).pack(anchor="w", pady=3)

        # Каналы уведомления о готовности — раньше send_sms/send_email были
        # заглушками БЕЗ единого поля для учётных данных в UI (пользователь,
        # включивший галочку выше, не мог их даже ввести), см.
        # AUDIT_REPORT_v25.md. Telegram уже был реально реализован — просто
        # не настраивался. Здесь — настройка всех трёх каналов.
        channels_frame = self.create_section(scroll, "Каналы уведомлений")

        self.sms_notify_var = ctk.BooleanVar(value=self.settings.get("sms_notifications", False))
        ctk.CTkCheckBox(
            channels_frame,
            text="SMS (через SMS.ru)",
            variable=self.sms_notify_var,
            fg_color=self.app.colors["accent"],
        ).pack(anchor="w", pady=(3, 0))
        self.sms_api_key_entry = self._labeled_entry(
            channels_frame, "API-ключ SMS.ru:", "sms_api_key", show="*"
        )

        self.email_notify_var = ctk.BooleanVar(
            value=self.settings.get("email_notifications", False)
        )
        ctk.CTkCheckBox(
            channels_frame,
            text="Email (через SMTP)",
            variable=self.email_notify_var,
            fg_color=self.app.colors["accent"],
        ).pack(anchor="w", pady=(10, 0))
        self.smtp_host_entry = self._labeled_entry(channels_frame, "SMTP-сервер:", "smtp_host")
        self.smtp_port_entry = self._labeled_entry(
            channels_frame, "SMTP-порт:", "smtp_port", default="587"
        )
        self.email_login_entry = self._labeled_entry(
            channels_frame, "Email-логин:", "email_login"
        )
        self.email_password_entry = self._labeled_entry(
            channels_frame, "Email-пароль:", "email_password", show="*"
        )
        self.smtp_tls_var = ctk.BooleanVar(value=self.settings.get("smtp_use_tls", True))
        ctk.CTkCheckBox(
            channels_frame,
            text="Использовать STARTTLS",
            variable=self.smtp_tls_var,
            fg_color=self.app.colors["accent"],
        ).pack(anchor="w", pady=3)

        self.telegram_bot_var = ctk.BooleanVar(value=self.settings.get("telegram_bot", False))
        ctk.CTkCheckBox(
            channels_frame,
            text="Telegram-бот",
            variable=self.telegram_bot_var,
            fg_color=self.app.colors["accent"],
        ).pack(anchor="w", pady=(10, 0))
        self.telegram_token_entry = self._labeled_entry(
            channels_frame, "Токен бота:", "telegram_token", show="*"
        )
        self.telegram_chat_id_entry = self._labeled_entry(
            channels_frame, "Chat ID:", "telegram_chat_id"
        )

    def _labeled_entry(
        self, parent, label: str, settings_key: str, default: str = "", show: str | None = None
    ) -> ctk.CTkEntry:
        """Строка "подпись + однострочное поле" — общая для 7 полей канала
        уведомлений выше (SMS/Email/Telegram), чтобы не повторять
        Frame+Label+Entry+pack вручную для каждого."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text=label, width=140, anchor="w").pack(side="left")
        entry = ctk.CTkEntry(row, show=show or "")
        entry.insert(0, str(self.settings.get(settings_key, default)))
        entry.pack(side="left", fill="x", expand=True)
        return entry

    def create_appearance_tab(self):
        """Создание вкладки внешнего вида"""
        scroll = ctk.CTkScrollableFrame(self.appearance_tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # Тема
        theme_frame = self.create_section(scroll, "Тема оформления")

        self.theme_var = ctk.StringVar(value=self.settings.get("theme", "light"))

        ctk.CTkRadioButton(
            theme_frame,
            text="Светлая",
            variable=self.theme_var,
            value="light",
            fg_color=self.app.colors["accent"],
        ).pack(anchor="w", pady=3)

        ctk.CTkRadioButton(
            theme_frame,
            text="Темная",
            variable=self.theme_var,
            value="dark",
            fg_color=self.app.colors["accent"],
        ).pack(anchor="w", pady=3)

        # Акцентный цвет
        accent_frame = self.create_section(scroll, "Акцентный цвет")

        color_container = ctk.CTkFrame(accent_frame, fg_color="transparent")
        color_container.pack(fill="x")

        self.color_preview = ctk.CTkFrame(
            color_container,
            width=40,
            height=40,
            corner_radius=8,
            fg_color=self.selected_color,
        )
        self.color_preview.pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            color_container,
            text="Выбрать цвет",
            command=self.choose_color,
            width=100,
            height=32,
            corner_radius=6,
            fg_color=self.app.colors["bg_tertiary"],
            text_color=self.app.colors["text_primary"],
        ).pack(side="left")

        # Полноэкранный режим
        fullscreen_frame = self.create_section(scroll, "Режим окна")

        self.fullscreen_var = ctk.BooleanVar(
            value=self.settings.get("fullscreen", False)
        )
        ctk.CTkCheckBox(
            fullscreen_frame,
            text="Запускать в полноэкранном режиме",
            variable=self.fullscreen_var,
            fg_color=self.app.colors["accent"],
        ).pack(anchor="w", pady=3)

        ctk.CTkLabel(
            fullscreen_frame,
            text="F11 - переключение полноэкранного режима",
            font=ctk.CTkFont(size=11),
            text_color=self.app.colors["text_secondary"],
        ).pack(anchor="w")

    def create_db_tab(self):
        """Создание вкладки базы данных"""
        scroll = ctk.CTkScrollableFrame(self.db_tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # Резервное копирование
        backup_frame = self.create_section(scroll, "Резервное копирование")

        self.auto_backup_var = ctk.BooleanVar(
            value=self.settings.get("auto_backup", True)
        )
        ctk.CTkCheckBox(
            backup_frame,
            text="Автоматическое резервное копирование",
            variable=self.auto_backup_var,
            fg_color=self.app.colors["accent"],
        ).pack(anchor="w", pady=3)

        # Путь сохранения бэкапов
        path_frame = ctk.CTkFrame(backup_frame, fg_color="transparent")
        path_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(path_frame, text="Папка для бэкапов:").pack(anchor="w")
        path_row = ctk.CTkFrame(path_frame, fg_color="transparent")
        path_row.pack(fill="x", pady=(2, 0))
        from config import BACKUP_DIR

        current_backup_path = self.settings.get("backup_path", "") or BACKUP_DIR
        self.backup_path_entry = ctk.CTkEntry(path_row, width=320)
        self.backup_path_entry.insert(0, current_backup_path)
        self.backup_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        def choose_backup_dir():
            from tkinter import filedialog

            chosen = filedialog.askdirectory(
                title="Выберите папку для сохранения бэкапов",
                initialdir=current_backup_path,
            )
            if chosen:
                self.backup_path_entry.delete(0, "end")
                self.backup_path_entry.insert(0, chosen)

        ctk.CTkButton(
            path_row,
            text="📂 Обзор",
            command=choose_backup_dir,
            width=90,
            height=30,
            corner_radius=6,
            fg_color=self.app.colors["bg_tertiary"],
            text_color=self.app.colors["text_primary"],
        ).pack(side="left")

        interval_frame = ctk.CTkFrame(backup_frame, fg_color="transparent")
        interval_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(interval_frame, text="Интервал (часов):").pack(side="left")
        self.backup_interval_entry = ctk.CTkEntry(interval_frame, width=80)
        self.backup_interval_entry.insert(
            0, str(self.settings.get("backup_interval", 24))
        )
        self.backup_interval_entry.pack(side="right")

        count_frame = ctk.CTkFrame(backup_frame, fg_color="transparent")
        count_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(count_frame, text="Хранить копий:").pack(side="left")
        self.backup_count_entry = ctk.CTkEntry(count_frame, width=80)
        self.backup_count_entry.insert(0, str(self.settings.get("backup_count", 10)))
        self.backup_count_entry.pack(side="right")

        self.compress_backups_var = ctk.BooleanVar(
            value=self.settings.get("compress_backups", True)
        )
        ctk.CTkCheckBox(
            backup_frame,
            text="Сжимать архивы",
            variable=self.compress_backups_var,
            fg_color=self.app.colors["accent"],
        ).pack(anchor="w", pady=3)

        # Фотографии
        photos_frame = self.create_section(scroll, "Фотографии")

        quality_frame = ctk.CTkFrame(photos_frame, fg_color="transparent")
        quality_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(quality_frame, text="Качество фото (%):").pack(side="left")
        self.photo_quality_entry = ctk.CTkEntry(quality_frame, width=80)
        self.photo_quality_entry.insert(0, str(self.settings.get("photo_quality", 85)))
        self.photo_quality_entry.pack(side="right")

        self.create_thumbs_var = ctk.BooleanVar(
            value=self.settings.get("create_thumbnails", True)
        )
        ctk.CTkCheckBox(
            photos_frame,
            text="Создавать миниатюры",
            variable=self.create_thumbs_var,
            fg_color=self.app.colors["accent"],
        ).pack(anchor="w", pady=3)

        # Подключение к БД / полномочия / блокировки — переехали в отдельную
        # вкладку "🔧 Базис" главного окна (см. gui/main_window_parts/
        # basis_cockpit_mixin.py, AUDIT_REPORT_v25.md Task U) — технические/
        # административные настройки, не предназначенные для обычного
        # сотрудника, отделены от повседневных пользовательских настроек
        # этого диалога.

    def create_pwa_tab(self):
        """Вкладка настроек мобильной версии (PWA) и синхронизации."""
        scroll = ctk.CTkScrollableFrame(self.pwa_tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # --- Сервер ---
        server_frame = self.create_section(scroll, "🌐 Сервер мобильной версии")

        self.pwa_auto_start_var = ctk.BooleanVar(
            value=self.settings.get("pwa.auto_start", False)
        )
        ctk.CTkCheckBox(
            server_frame,
            text="Запускать сервер при старте программы",
            variable=self.pwa_auto_start_var,
            fg_color=self.app.colors["accent"],
        ).pack(anchor="w", pady=3)

        port_frame = ctk.CTkFrame(server_frame, fg_color="transparent")
        port_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(port_frame, text="Порт сервера:").pack(side="left")
        self.pwa_port_entry = ctk.CTkEntry(port_frame, width=80)
        self.pwa_port_entry.insert(0, str(self.settings.get("pwa.port", 5000)))
        self.pwa_port_entry.pack(side="right")

        ctk.CTkLabel(
            server_frame,
            text="💡 QR-код доступен по кнопке «📱 Мобильная версия» в главном окне.\n"
            "Телефон и ПК должны быть в одной Wi-Fi сети.",
            font=ctk.CTkFont(size=11),
            text_color=self.app.colors["text_secondary"],
            justify="left",
            anchor="w",
        ).pack(anchor="w", pady=(4, 0))

        # --- Синхронизация ---
        sync_frame = self.create_section(scroll, "🔄 Синхронизация с PWA")

        self.pwa_auto_sync_var = ctk.BooleanVar(
            value=self.settings.get("pwa.auto_sync", True)
        )
        ctk.CTkCheckBox(
            sync_frame,
            text="Автоматически обновлять список заказов",
            variable=self.pwa_auto_sync_var,
            fg_color=self.app.colors["accent"],
        ).pack(anchor="w", pady=3)

        interval_frame = ctk.CTkFrame(sync_frame, fg_color="transparent")
        interval_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(interval_frame, text="Интервал обновления (секунд):").pack(
            side="left"
        )
        self.pwa_sync_interval_entry = ctk.CTkEntry(interval_frame, width=80)
        self.pwa_sync_interval_entry.insert(
            0, str(self.settings.get("pwa.sync_interval", 30))
        )
        self.pwa_sync_interval_entry.pack(side="right")

        ctk.CTkLabel(
            sync_frame,
            text="💡 При включении — список заказов на ПК автоматически\n"
            "обновляется каждые N секунд. Например, если вы добавили\n"
            "фото через телефон — оно появится на ПК без перезапуска.\n\n"
            "Рекомендуется: 15–60 секунд. 0 = выключено.",
            font=ctk.CTkFont(size=11),
            text_color=self.app.colors["text_secondary"],
            justify="left",
            anchor="w",
        ).pack(anchor="w", pady=(4, 0))

    def create_section(self, parent, title):
        """Создание секции с заголовком"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=10)

        ctk.CTkLabel(
            frame,
            text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.app.colors["accent"],
        ).pack(anchor="w", pady=(0, 5))

        ctk.CTkFrame(frame, height=1, fg_color=self.app.colors["border"]).pack(
            fill="x", pady=(0, 8)
        )

        content = ctk.CTkFrame(frame, fg_color="transparent")
        content.pack(fill="x", padx=10)

        return content

    def choose_color(self):
        """Выбор цвета"""
        color = colorchooser.askcolor(
            title="Выберите акцентный цвет", initialcolor=self.selected_color
        )
        if color and color[1]:
            self.selected_color = color[1]
            self.color_preview.configure(fg_color=self.selected_color)

    def _safe_int(self, value, default, lo=None, hi=None):
        """Безопасное преобразование строки в int с проверкой диапазона."""
        try:
            v = int(value)
        except (ValueError, TypeError):
            return default
        if lo is not None and v < lo:
            return lo
        if hi is not None and v > hi:
            return hi
        return v

    def save_settings(self):
        """Сохранение настроек"""
        try:
            # Общие настройки
            self.settings.set("confirm_delete", self.confirm_delete_var.get())
            self.settings.set("confirm_exit", self.confirm_exit_var.get())
            self.settings.set("default_status", self.default_status_combo.get())
            self.settings.set("default_priority", self.default_priority_combo.get())
            self.settings.set("remind_overdue", self.remind_overdue_var.get())
            self.settings.set(
                "overdue_days",
                self._safe_int(self.overdue_days_entry.get(), 14, lo=1, hi=365),
            )
            self.settings.set("notify_on_ready", self.notify_ready_var.get())
            self.settings.set("sms_notifications", self.sms_notify_var.get())
            self.settings.set("sms_api_key", self.sms_api_key_entry.get().strip())
            self.settings.set("email_notifications", self.email_notify_var.get())
            self.settings.set("smtp_host", self.smtp_host_entry.get().strip())
            self.settings.set(
                "smtp_port", self._safe_int(self.smtp_port_entry.get(), 587, lo=1, hi=65535)
            )
            self.settings.set("email_login", self.email_login_entry.get().strip())
            self.settings.set("email_password", self.email_password_entry.get())
            self.settings.set("smtp_use_tls", self.smtp_tls_var.get())
            self.settings.set("telegram_bot", self.telegram_bot_var.get())
            self.settings.set("telegram_token", self.telegram_token_entry.get().strip())
            self.settings.set("telegram_chat_id", self.telegram_chat_id_entry.get().strip())
            # pessimistic_locking_enabled/lock_ttl_seconds сохраняются из
            # вкладки "🔧 Базис" главного окна, не отсюда — см.
            # gui/main_window_parts/basis_cockpit_mixin.py.

            # Внешний вид
            new_theme = self.theme_var.get()
            self.settings.set("theme", new_theme)
            self.settings.set("fullscreen", self.fullscreen_var.get())
            self.settings.set("accent_color", self.selected_color)

            # База данных
            self.settings.set("auto_backup", self.auto_backup_var.get())
            self.settings.set(
                "backup_interval",
                self._safe_int(self.backup_interval_entry.get(), 24, lo=1, hi=720),
            )
            self.settings.set(
                "backup_count",
                self._safe_int(self.backup_count_entry.get(), 10, lo=1, hi=100),
            )
            # Путь для бэкапов (создаём папку, если её нет)
            backup_path = self.backup_path_entry.get().strip()
            if backup_path:
                try:
                    import os

                    os.makedirs(backup_path, exist_ok=True)
                except Exception as e:
                    logger.error(
                        f"Не удалось создать папку бэкапов {backup_path}: {e}",
                        exc_info=True,
                    )
            self.settings.set("backup_path", backup_path)
            self.settings.set("compress_backups", self.compress_backups_var.get())
            self.settings.set(
                "photo_quality",
                self._safe_int(self.photo_quality_entry.get(), 85, lo=1, hi=100),
            )
            self.settings.set("create_thumbnails", self.create_thumbs_var.get())

            # Мобильная версия (PWA)
            self.settings.set("pwa.auto_start", self.pwa_auto_start_var.get())
            self.settings.set(
                "pwa.port",
                self._safe_int(self.pwa_port_entry.get(), 5000, lo=1024, hi=65535),
            )
            self.settings.set("pwa.auto_sync", self.pwa_auto_sync_var.get())
            self.settings.set(
                "pwa.sync_interval",
                self._safe_int(self.pwa_sync_interval_entry.get(), 30, lo=0, hi=3600),
            )

            messagebox.showinfo(
                "Успех",
                "Настройки сохранены!\nНекоторые изменения вступят после перезапуска.",
            )

            # Применяем тему если изменилась
            if new_theme != self.app.theme:
                self.app.update_theme(new_theme)

            self._close_with_geometry()

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить настройки: {e}")

    def reset_settings(self):
        """Сброс настроек"""
        if messagebox.askyesno(
            "Подтверждение", "Сбросить все настройки к значениям по умолчанию?"
        ):
            self.settings.reset_to_defaults()
            messagebox.showinfo(
                "Успех", "Настройки сброшены. Перезапустите программу для применения."
            )
            self._close_with_geometry()
