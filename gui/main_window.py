#!/usr/bin/env python3

"""Главное окно приложения - Современный интерфейс.

Реализация разбита на mixin'ы (gui/main_window_parts/*_mixin.py) по
разделу ответственности — окно/хром, построение виджетов, таблица заказов,
диалоги заказа, акты, финансы, PWA, периодический бэкап, прочие диалоги —
тем же способом, каким core/base.py уже собирает BaseService. Этот файл —
только "сборка" (__init__ + жизненный цикл: on_closing/run), см.
AUDIT_REPORT_v25.md (Task T). Ни один внешний вызов не изменился —
ServiceCenterApp() конструируется и используется ровно так же, как раньше."""

import logging

import customtkinter as ctk

from config import DB_PATH
from database import WorkItemsManager
from gui.main_window_parts.acts_mixin import ActsMixin
from gui.main_window_parts.async_load_mixin import AsyncLoadMixin
from gui.main_window_parts.backup_mixin import BackupMixin
from gui.main_window_parts.basis_cockpit_mixin import BasisCockpitMixin
from gui.main_window_parts.device_dialogs_mixin import DeviceDialogsMixin
from gui.main_window_parts.devices_table_mixin import DevicesTableMixin
from gui.main_window_parts.dialogs_mixin import DialogsMixin
from gui.main_window_parts.finance_mixin import FinanceMixin
from gui.main_window_parts.pwa_mixin import PwaMixin
from gui.main_window_parts.widgets_mixin import WidgetsMixin
from gui.main_window_parts.window_mixin import WindowMixin
from utils.colors import get_colors

logger = logging.getLogger(__name__)

__all__ = ["ServiceCenterApp"]


class ServiceCenterApp(
    WindowMixin,
    AsyncLoadMixin,
    WidgetsMixin,
    DevicesTableMixin,
    DeviceDialogsMixin,
    ActsMixin,
    FinanceMixin,
    PwaMixin,
    BackupMixin,
    DialogsMixin,
    BasisCockpitMixin,
):
    """Главное окно приложения"""

    def __init__(self):
        # Все зависимости приходят из Kernel DI (см. bootstrap.initialize_kernel) —
        # единая точка сборки вместо самостоятельного создания каждого объекта.
        # Kernel уже инициализирован bootstrap-ом до создания этого окна; если
        # почему-то нет (например, прямой запуск без main.py) — инициализируем сами.
        from core.kernel import get_core

        core = get_core()
        if not core.is_initialized:
            import bootstrap

            core = bootstrap.initialize_kernel()
        self._core = core

        self.settings = core.get_module_api("settings")
        self.theme = self.settings.get("theme", "light")
        self.colors = get_colors(
            self.theme, self.settings.get("accent_color", "#0078d4")
        )

        ctk.set_appearance_mode("dark" if self.theme == "dark" else "light")
        ctk.set_default_color_theme("blue")

        # Доступ к БД — только через core.get_db_access(), никогда напрямую.
        self.db = core.get_db_access()
        self.client_db = core.get_module_api("client_history")
        # Авто-миграция клиентских БД при первом запуске
        try:
            self.db.migrate_client_dbs()
        except Exception as e:
            logger.error(f"Авто-миграция клиентских БД не удалась: {e}", exc_info=True)
        self.report_gen = core.get_module_api("reports")
        self.backup_manager = core.get_module_api("backup")
        self.integration_manager = core.get_module_api("integrations")
        self.photo_manager = core.get_module_api("photos")
        self.employees_api = core.get_module_api("employees")
        self.lock_api = core.get_module_api("locking")

        self.device_entries = {}
        self.current_edit_id = None
        self.sort_column = None
        self.sort_reverse = False
        self.show_completed = False
        self.current_photos = []
        self.thumbnail_widgets = []
        self.work_manager = WorkItemsManager()
        self.pwa_manager = None  # менеджер PWA-сервера (создаётся лениво)

        self.setup_main_window()
        self.create_widgets()
        self.load_devices()

        if self.settings.get("fullscreen", False):
            self.root.after(100, lambda: self.root.attributes("-fullscreen", True))

        self.root.bind("<F11>", lambda e: self.toggle_fullscreen())
        self.root.bind(
            "<Escape>",
            lambda e: (
                self.toggle_fullscreen(False)
                if self.root.attributes("-fullscreen")
                else None
            ),
        )
        self.root.bind("<F5>", lambda e: self.refresh_orders())
        # Горячие клавиши
        self.root.bind("<Control-n>", lambda e: self.open_add_device_window())
        self.root.bind("<Control-N>", lambda e: self.open_add_device_window())
        self.root.bind(
            "<Control-f>",
            lambda e: (
                self.search_entry.focus_set() if hasattr(self, "search_entry") else None
            ),
        )
        self.root.bind(
            "<Control-F>",
            lambda e: (
                self.search_entry.focus_set() if hasattr(self, "search_entry") else None
            ),
        )
        self.root.bind("<Control-r>", lambda e: self.refresh_orders())
        self.root.bind("<Control-R>", lambda e: self.refresh_orders())
        self.root.bind("<Control-p>", lambda e: self.print_receipt_act())
        self.root.bind("<Control-P>", lambda e: self.print_receipt_act())
        self.root.bind("<Delete>", lambda e: self._quick_delete_selected())
        self.root.bind(
            "<Return>", lambda e: self.edit_device() if self.tree.selection() else None
        )

        # Авто-запуск PWA-сервера при старте (если включено в настройках)
        if self.settings.get("pwa.auto_start", False):
            self.root.after(800, self._auto_start_pwa)

        # Авто-синхронизация списка заказов (чтобы видеть изменения из PWA)
        self.root.after(2000, self._start_auto_sync)
        # Периодический бэкап (см. AUDIT_REPORT_v25.md — backup_interval
        # раньше ни на что не влиял)
        self.root.after(3000, self._start_periodic_backup)

    def on_closing(self):
        """Обработка закрытия приложения"""
        # Раньше настройка "Подтверждать выход" (confirm_exit) сохранялась,
        # но нигде не читалась — приложение всегда закрывалось сразу, см.
        # AUDIT_REPORT_v25.md.
        from tkinter import messagebox

        if self.settings.get("confirm_exit", False) and not messagebox.askyesno(
            "Выход", "Закрыть ServiceUP?"
        ):
            return
        try:
            # Останавливаем авто-синхронизацию
            self._stop_auto_sync()
            self._stop_periodic_backup()
            # Останавливаем PWA-сервер, если активен
            if hasattr(self, "pwa_manager") and self.pwa_manager is not None:
                self.pwa_manager.stop()

            if self.settings.get("auto_backup", True):
                self.backup_manager.create_backup(DB_PATH)

            self.settings.save_settings()
            self.db.close()
            self.root.destroy()
        except Exception as e:
            logger.exception(f"Ошибка при закрытии: {e}")
            self.root.destroy()

    def run(self):
        """Запуск приложения"""
        try:
            self.dashboard.update_stats()
            # Финансы загружаются лениво — не вызываем update_finance_display
            # пока вкладка не открыта
            if getattr(self, "_finance_loaded", False):
                self.update_finance_display()
            self.root.mainloop()
        except KeyboardInterrupt:
            self.on_closing()
        except Exception as e:
            logger.exception(f"Ошибка выполнения: {e}")
            self.on_closing()
