#!/usr/bin/env python3

"""Главное окно приложения - Современный интерфейс"""

import contextlib
import logging
import os
import sys
from datetime import datetime, timedelta
from tkinter import messagebox, ttk
from typing import Any

import customtkinter as ctk

from config import APP_VERSION, DB_PATH
from database import ClientDatabaseManager, Database, WorkItemsManager
from gui.dialogs.act_preview import ActPreviewWindow
from gui.dialogs.client_history import ClientHistoryWindow
from gui.dialogs.device_form import DeviceFormDialog
from gui.dialogs.dictionaries import DictionariesManagerWindow
from gui.dialogs.settings import SettingsWindow
from gui.widgets import (
    ModernButton,
    ModernCard,
    ModernCombobox,
    ModernEntry,
    ModernLabel,
    ModernSwitch,
)
from gui.widgets.dashboard import PremiumDashboard
from managers import (
    BackupManager,
    IntegrationManager,
    PhotoManager,
    ReportGenerator,
    SettingsManager,
)
from utils.colors import get_colors
from utils.constants import PRIORITIES, STATUSES
from utils.formatters import (
    format_date,
    format_order_number_for_db,
    format_order_number_for_display,
    format_phone,
    format_price,
    get_days_since_receipt,
)
from utils.window_effects import apply_rounded_corners

logger = logging.getLogger(__name__)


class ServiceCenterApp:
    """Главное окно приложения"""

    def __init__(self):
        self.settings = SettingsManager()
        self.theme = self.settings.get("theme", "light")
        self.colors = get_colors(
            self.theme, self.settings.get("accent_color", "#0078d4")
        )

        ctk.set_appearance_mode("dark" if self.theme == "dark" else "light")
        ctk.set_default_color_theme("blue")

        self.db = Database(DB_PATH)
        self.client_db = ClientDatabaseManager(main_db=self.db)
        # Авто-миграция клиентских БД при первом запуске
        try:
            self.db.migrate_client_dbs()
        except Exception as e:
            logger.error(f"Авто-миграция клиентских БД не удалась: {e}", exc_info=True)
        self.report_gen = ReportGenerator()
        self.backup_manager = BackupManager(self.settings)
        self.integration_manager = IntegrationManager(self.settings)
        self.photo_manager = PhotoManager()

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

    def _auto_start_pwa(self):
        """Авто-запуск PWA-сервера при старте программы (без показа QR-диалога)."""
        try:
            from pwa.server import PWAServerManager

            if self.pwa_manager is None:
                self.pwa_manager = PWAServerManager()
            if not self.pwa_manager.is_running:
                port = self.settings.get("pwa.port", 5000)
                if self.pwa_manager.start(port=port):
                    url = self.pwa_manager.get_url()
                    self.update_status_bar(f"📱 Мобильная версия активна: {url}")
        except Exception as e:
            logger.error(f"Авто-запуск PWA сервера не удался: {e}", exc_info=True)

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

    def refresh_ui(self):
        """Обновление интерфейса"""
        current_status = (
            self.status_filter.get() if hasattr(self, "status_filter") else "Все"
        )
        current_priority = (
            self.priority_filter.get() if hasattr(self, "priority_filter") else "Все"
        )
        current_device_type = (
            self.device_type_filter.get()
            if hasattr(self, "device_type_filter")
            else "Все"
        )
        current_brand = (
            self.brand_filter.get() if hasattr(self, "brand_filter") else "Все"
        )
        current_hide = (
            self.hide_completed_var.get()
            if hasattr(self, "hide_completed_var")
            else True
        )

        for widget in self.root.winfo_children():
            widget.destroy()

        self.create_widgets()

        if hasattr(self, "status_filter"):
            self.status_filter.set(current_status)
        if hasattr(self, "priority_filter"):
            self.priority_filter.set(current_priority)
        if hasattr(self, "device_type_filter"):
            self.device_type_filter.set(current_device_type)
        if hasattr(self, "brand_filter"):
            self.brand_filter.set(current_brand)
        if hasattr(self, "hide_completed_var"):
            self.hide_completed_var.set(current_hide)

        self.load_devices()

    def create_widgets(self):
        """Создание виджетов главного окна.

        Layout (pack сверху вниз):
          header          (top)
          top_panel       (top) — дашборд + поиск
          bottom_bar      (bottom) — action_panel + status_bar (фиксированная)
          tabview         (fill both, expand) — занимает ОСТАТОК между top и bottom
        """
        self.main_container = ctk.CTkFrame(
            self.root, fg_color=self.colors["bg_primary"], corner_radius=0
        )
        self.main_container.pack(fill="both", expand=True, padx=0, pady=0)

        self.create_header()

        top_panel = ctk.CTkFrame(self.main_container, fg_color="transparent")
        top_panel.pack(fill="x", padx=12, pady=(0, 12))

        self.dashboard = PremiumDashboard(
            top_panel,
            self.db,
            self.colors,
            on_overdue_click=self.show_overdue_orders,
            fg_color="transparent",
        )
        self.dashboard.pack(side="left", fill="x", expand=True)

        self.create_search_panel(top_panel)

        # --- Нижняя фиксированная панель (pack ПЕРВЫМ с side=bottom) ---
        # Это гарантирует, что tabview(expand) не вытеснит кнопки за пределы.
        bottom_bar = ctk.CTkFrame(self.main_container, fg_color="transparent")
        bottom_bar.pack(side="bottom", fill="x")
        # Создаём action_panel и status_bar ВНУТРИ bottom_bar
        self._create_action_panel_in(bottom_bar)
        self._create_status_bar_in(bottom_bar)

        # --- Вкладки (pack последним, expand — занимает остаток) ---
        self.tabview = ctk.CTkTabview(
            self.main_container, fg_color=self.colors["bg_primary"]
        )
        self.tabview.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # Вкладка "Заказы"
        orders_tab = self.tabview.add("📋 Заказы")
        self.create_devices_table(orders_tab)

        # Вкладка "Финансы" — контейнер, контент загружается лениво
        self._finance_tab = self.tabview.add("💰 Финансы")
        self._finance_loaded = False
        self.tabview.configure(command=self._on_tab_changed)

    def _on_tab_changed(self):
        """Ленивая загрузка вкладки Финансы при первом переключении."""
        try:
            current = self.tabview.get()
            if current == "💰 Финансы" and not self._finance_loaded:
                self.create_finance_tab(self._finance_tab)
                self._finance_loaded = True
                self.update_finance_display()
            # Обновляем фильтры при возврате на Заказы
            if hasattr(self, "_old_filter_command"):
                self._old_filter_command()
        except Exception:
            pass

    def create_header(self):
        """Создание шапки приложения"""
        header_frame = ModernCard(
            self.main_container, self.colors, height=56, corner_radius=0
        )
        header_frame.pack(fill="x", pady=(0, 12))
        header_frame.pack_propagate(False)

        left_container = ctk.CTkFrame(header_frame, fg_color="transparent")
        left_container.pack(side="left", padx=20, pady=8)

        logo_frame = ctk.CTkFrame(
            left_container,
            fg_color=self.colors["accent"],
            corner_radius=10,
            width=36,
            height=36,
        )
        logo_frame.pack(side="left", padx=(0, 12))
        logo_frame.pack_propagate(False)

        logo_label = ctk.CTkLabel(
            logo_frame, text="🔧", font=ctk.CTkFont(size=18), text_color="white"
        )
        logo_label.pack(expand=True)

        title_frame = ctk.CTkFrame(left_container, fg_color="transparent")
        title_frame.pack(side="left")

        title_label = ctk.CTkLabel(
            title_frame,
            text="ServiceUP",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.colors["text_primary"],
        )
        title_label.pack(anchor="w")

        subtitle_label = ctk.CTkLabel(
            title_frame,
            text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=11),
            text_color=self.colors["text_secondary"],
        )
        subtitle_label.pack(anchor="w")

        right_container = ctk.CTkFrame(header_frame, fg_color="transparent")
        right_container.pack(side="right", padx=20, pady=8)

        # Кнопка редактора актов (иконка + tooltip)
        editor_btn = ModernButton(
            right_container,
            self.colors,
            variant="secondary",
            text="📄",
            command=self.open_report_editor,
            width=40,
            height=34,
        )
        editor_btn.pack(side="right", padx=(8, 0))
        # Tooltip через hover
        try:
            from gui.widgets.tooltip import create_tooltip

            create_tooltip(editor_btn, "Редактор актов")
        except Exception:
            pass

        # Кнопка словарей
        dict_btn = ModernButton(
            right_container,
            self.colors,
            variant="secondary",
            text="📚",
            command=self.open_dictionaries_manager,
            width=40,
            height=34,
        )
        dict_btn.pack(side="right", padx=(8, 0))
        try:
            from gui.widgets.tooltip import create_tooltip

            create_tooltip(dict_btn, "Словари")
        except Exception:
            pass

        # Кнопка настроек
        settings_btn = ModernButton(
            right_container,
            self.colors,
            variant="secondary",
            text="⚙",
            command=self.open_settings,
            width=40,
            height=34,
        )
        settings_btn.pack(side="right", padx=(8, 0))
        try:
            from gui.widgets.tooltip import create_tooltip

            create_tooltip(settings_btn, "Настройки")
        except Exception:
            pass

        # Кнопка активации лицензии
        license_btn = ModernButton(
            right_container,
            self.colors,
            variant="secondary",
            text="🔐",
            command=self.show_activation,
            width=40,
            height=34,
        )
        license_btn.pack(side="right", padx=(8, 0))
        try:
            from gui.widgets.tooltip import create_tooltip

            create_tooltip(license_btn, "Активация лицензии")
        except Exception:
            pass

        self.datetime_label = ctk.CTkLabel(
            right_container,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.colors["accent"],
        )
        self.datetime_label.pack(side="right", padx=(0, 16))
        self.update_datetime()

    def create_search_panel(self, parent):
        """Создание панели поиска с кнопкой"""
        search_card = ModernCard(parent, self.colors, corner_radius=12)
        search_card.pack(side="right", padx=(12, 0), fill="y")

        search_container = ctk.CTkFrame(search_card, fg_color="transparent")
        search_container.pack(padx=12, pady=8)

        search_icon = ctk.CTkLabel(
            search_container,
            text="🔍",
            font=ctk.CTkFont(size=14),
            text_color=self.colors["text_secondary"],
        )
        search_icon.pack(side="left", padx=(0, 8))

        self.search_var = ctk.StringVar()

        self.search_entry = ModernEntry(
            search_container,
            self.colors,
            textvariable=self.search_var,
            placeholder_text="Поиск по заказам, клиентам...",
            width=220,
            height=34,
        )
        self.search_entry.pack(side="left", padx=(0, 8))
        self.search_entry.bind("<Return>", lambda e: self.search_devices())

        # Кнопка "Найти"
        search_btn = ModernButton(
            search_container,
            self.colors,
            variant="primary",
            text="🔍 Найти",
            command=self.search_devices,
            height=34,
            width=80,
        )
        search_btn.pack(side="left", padx=(0, 8))

        # Кнопка "Обновить" — перезагружает список заказов из БД
        refresh_btn = ModernButton(
            search_container,
            self.colors,
            variant="secondary",
            text="🔄 Обновить",
            command=self.refresh_orders,
            height=34,
            width=90,
        )
        refresh_btn.pack(side="left", padx=(0, 8))

        add_button = ModernButton(
            search_container,
            self.colors,
            variant="primary",
            text="➕ Новый заказ",
            command=self.open_add_device_window,
            height=34,
            width=120,
        )
        add_button.pack(side="left")

    def create_devices_table(self, parent):
        """Создание таблицы устройств"""
        table_card = ModernCard(parent, self.colors)
        table_card.pack(fill="both", expand=True)

        header_container = ctk.CTkFrame(table_card, fg_color="transparent")
        header_container.pack(fill="x", padx=16, pady=(12, 8))

        table_title = ModernLabel(
            header_container,
            self.colors,
            text="📋 Список заказов",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        table_title.pack(side="left")

        filter_container = ctk.CTkFrame(header_container, fg_color="transparent")
        filter_container.pack(side="right")

        ModernLabel(filter_container, self.colors, text="Статус:").pack(
            side="left", padx=(0, 8)
        )

        self.status_filter = ModernCombobox(
            filter_container,
            self.colors,
            values=["Все", *STATUSES],
            width=140,
            height=32,
            command=self._on_filter_changed,
        )
        self.status_filter.set("Все")
        self.status_filter.pack(side="left", padx=(0, 12))

        ModernLabel(filter_container, self.colors, text="Приоритет:").pack(
            side="left", padx=(0, 8)
        )

        self.priority_filter = ModernCombobox(
            filter_container,
            self.colors,
            values=["Все", *PRIORITIES],
            width=110,
            height=32,
            command=self._on_filter_changed,
        )
        self.priority_filter.set("Все")
        self.priority_filter.pack(side="left", padx=(0, 12))

        ModernLabel(filter_container, self.colors, text="Тип:").pack(
            side="left", padx=(0, 8)
        )

        # Значения типа устройства: из словаря + уникальные из заказов
        self.device_type_filter = ModernCombobox(
            filter_container,
            self.colors,
            values=["Все", *self._collect_filter_values("device_types", "device_type")],
            width=130,
            height=32,
            command=self._on_filter_changed,
        )
        self.device_type_filter.set("Все")
        self.device_type_filter.pack(side="left", padx=(0, 12))

        ModernLabel(filter_container, self.colors, text="Бренд:").pack(
            side="left", padx=(0, 8)
        )

        self.brand_filter = ModernCombobox(
            filter_container,
            self.colors,
            values=["Все", *self._collect_filter_values("brands", "brand")],
            width=120,
            height=32,
            command=self._on_filter_changed,
        )
        self.brand_filter.set("Все")
        self.brand_filter.pack(side="left", padx=(0, 12))

        self.hide_completed_var = ctk.BooleanVar(
            value=self.settings.get("show_completed", True)
        )
        hide_completed_check = ModernSwitch(
            filter_container,
            self.colors,
            text="Скрыть выполненные",
            variable=self.hide_completed_var,
            command=self.toggle_completed,
        )
        hide_completed_check.pack(side="left", padx=(12, 0))

        # --- Быстрые фильтры времени ---
        quick_frame = ctk.CTkFrame(filter_container, fg_color="transparent")
        quick_frame.pack(side="left", padx=(12, 0))

        ModernButton(
            quick_frame,
            self.colors,
            variant="outline",
            text="📅 Сегодня",
            command=self.show_today_orders,
            height=30,
            width=85,
        ).pack(side="left", padx=2)
        ModernButton(
            quick_frame,
            self.colors,
            variant="outline",
            text="📆 Неделя",
            command=self.show_week_orders,
            height=30,
            width=85,
        ).pack(side="left", padx=2)
        ModernButton(
            quick_frame,
            self.colors,
            variant="outline",
            text="⏰ Просроч.",
            command=self.show_overdue_orders,
            height=30,
            width=95,
        ).pack(side="left", padx=2)

        tree_container = ctk.CTkFrame(table_card, fg_color="transparent")
        tree_container.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        columns = (
            "Заказ №",
            "Дата приёма",
            "Дней",
            "Дата выдачи",
            "Устройство",
            "Клиент",
            "Телефон",
            "Неисправность",
            "Статус",
            "Приоритет",
            "Инженер",
            "Цена",
            "Фото",
        )

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background=self.colors["bg_secondary"],
            foreground=self.colors["text_primary"],
            fieldbackground=self.colors["bg_secondary"],
            borderwidth=0,
            font=("Segoe UI", 11),
        )
        style.configure(
            "Treeview.Heading",
            background=self.colors["bg_tertiary"],
            foreground=self.colors["text_primary"],
            borderwidth=0,
            font=("Segoe UI", 11, "bold"),
        )
        style.map("Treeview", background=[("selected", self.colors["accent"])])

        self.tree = ttk.Treeview(
            tree_container, columns=columns, show="headings", height=20
        )

        # Дефолтные ширины (с инженером)
        default_widths = {
            "Заказ №": 60,
            "Дата приёма": 90,
            "Дней": 45,
            "Дата выдачи": 80,
            "Устройство": 170,
            "Клиент": 140,
            "Телефон": 110,
            "Неисправность": 170,
            "Статус": 110,
            "Приоритет": 90,
            "Инженер": 100,
            "Цена": 80,
            "Фото": 50,
        }
        # Восстанавливаем сохранённые ширины
        saved_widths = self.settings.get("column_widths", {}) or {}
        saved_order = self.settings.get("column_order", []) or []

        # Устанавливаем порядок колонок (если сохранён)
        display_columns = columns
        if saved_order and len(saved_order) == len(columns):
            # Фильтруем только валидные
            display_columns = tuple(c for c in saved_order if c in columns)
            if len(display_columns) != len(columns):
                display_columns = columns

        for col in columns:
            width = saved_widths.get(col, default_widths.get(col, 100))
            self.tree.heading(
                col, text=col, command=lambda c=col: self.sort_treeview(c)
            )
            self.tree.column(col, width=width, minwidth=40)

        # Применяем порядок отображения
        if display_columns != columns:
            self.tree["displaycolumns"] = display_columns

        # Перетаскивание колонок сохраняется автоматически через displaycolumns
        self.tree.bind("<ButtonRelease-1>", self._save_column_state)

        # Авто-скрываемые скроллбары (скрываются, когда контент помещается)
        from gui.widgets.auto_scroll import attach_auto_scrollbars

        attach_auto_scrollbars(tree_container, self.tree)

        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        self.tree.bind("<Double-Button-1>", self.on_device_double_click)
        self.tree.bind("<Button-3>", self.show_context_menu)

        self.tree.tag_configure(
            "urgent", background=self.colors.get("urgent_light", "#4a1e1e")
        )
        self.tree.tag_configure(
            "warning", background=self.colors.get("warning_light", "#4a3a1e")
        )
        self.tree.tag_configure(
            "normal",
            background=self.colors.get("normal_light", self.colors["bg_secondary"]),
        )
        self.tree.tag_configure("completed", background=self.colors["bg_secondary"])

        self.create_context_menu()

    def create_finance_tab(self, parent):
        """Создание вкладки финансов"""
        # Карточка со сводкой
        summary_card = ModernCard(parent, self.colors)
        summary_card.pack(fill="x", pady=(0, 10))

        summary_frame = ctk.CTkFrame(summary_card, fg_color="transparent")
        summary_frame.pack(fill="x", padx=15, pady=10)

        # Кнопки периодов
        period_frame = ctk.CTkFrame(summary_frame, fg_color="transparent")
        period_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            period_frame, text="Период:", font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left", padx=(0, 10))

        self.period_var = ctk.StringVar(value="all")
        periods = [("Все время", "all"), ("Неделя", "week"), ("Месяц", "month")]

        for text, value in periods:
            btn = ctk.CTkRadioButton(
                period_frame,
                text=text,
                variable=self.period_var,
                value=value,
                command=self.update_finance_display,
                fg_color=self.colors["accent"],
            )
            btn.pack(side="left", padx=5)

        # Карточка со статистикой
        stats_frame = ctk.CTkFrame(summary_frame, fg_color="transparent")
        stats_frame.pack(fill="x")

        self.income_label = ctk.CTkLabel(
            stats_frame,
            text="💰 Доход: 0 ₽",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["success"],
        )
        self.income_label.pack(side="left", padx=(0, 20))

        self.expense_label = ctk.CTkLabel(
            stats_frame,
            text="💸 Расход: 0 ₽",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["error"],
        )
        self.expense_label.pack(side="left", padx=(0, 20))

        self.profit_label = ctk.CTkLabel(
            stats_frame,
            text="📈 Прибыль: 0 ₽",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["accent"],
        )
        self.profit_label.pack(side="left")

        # Таблица финансов
        table_card = ModernCard(parent, self.colors)
        table_card.pack(fill="both", expand=True)

        ctk.CTkLabel(
            table_card,
            text="📊 Список завершённых заказов",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=15, pady=(10, 5))

        tree_container = ctk.CTkFrame(table_card, fg_color="transparent")
        tree_container.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        # Стиль для таблицы
        style = ttk.Style()
        style.configure(
            "Finance.Treeview",
            background=self.colors["bg_secondary"],
            foreground=self.colors["text_primary"],
            fieldbackground=self.colors["bg_secondary"],
            borderwidth=0,
            font=("Segoe UI", 11),
            rowheight=30,
        )
        style.configure(
            "Finance.Treeview.Heading",
            background=self.colors["bg_tertiary"],
            foreground=self.colors["text_primary"],
            borderwidth=0,
            font=("Segoe UI", 11, "bold"),
        )

        columns = ("Заказ №", "Дата выдачи", "Доход", "Расход", "Прибыль")

        self.finance_tree = ttk.Treeview(
            tree_container,
            columns=columns,
            show="headings",
            height=15,
            style="Finance.Treeview",
        )

        column_widths = [100, 120, 120, 120, 120]
        for col, width in zip(columns, column_widths, strict=False):
            self.finance_tree.heading(col, text=col)
            self.finance_tree.column(col, width=width, minwidth=80)

        # Авто-скрываемые скроллбары
        from gui.widgets.auto_scroll import attach_auto_scrollbars

        attach_auto_scrollbars(tree_container, self.finance_tree)

        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        # Привязываем двойной клик для редактирования расхода
        self.finance_tree.bind("<Double-Button-1>", self.edit_expense)

    def update_finance_display(self):
        """Обновление отображения финансов"""
        # Ленивая загрузка: если вкладка финансов ещё не создана — пропускаем
        if not getattr(self, "_finance_loaded", False):
            return
        if not hasattr(self, "period_var"):
            return
        period = self.period_var.get()

        # Получаем сводку
        summary = self.db.get_finance_summary(period)

        self.income_label.configure(
            text=f"💰 Доход: {format_price(str(summary['total_income']))}"
        )
        self.expense_label.configure(
            text=f"💸 Расход: {format_price(str(summary['total_expense']))}"
        )
        self.profit_label.configure(
            text=f"📈 Прибыль: {format_price(str(summary['total_profit']))}"
        )

        # Получаем список заказов
        finances = self.db.get_finances(period)

        # Очищаем таблицу
        for item in self.finance_tree.get_children():
            self.finance_tree.delete(item)

        # Заполняем таблицу
        for finance in finances:
            order_number = format_order_number_for_display(
                finance.get("order_number", "_")
            )
            completion_date = format_date(finance.get("completion_date", ""))
            income = format_price(str(finance.get("income", 0)))
            expense = format_price(str(finance.get("expense", 0)))
            profit = format_price(str(finance.get("profit", 0)))

            # Определяем цвет прибыли
            tags = ()
            profit_val = finance.get("profit", 0)
            if profit_val > 0:
                tags = ("positive",)
            elif profit_val < 0:
                tags = ("negative",)

            self.finance_tree.insert(
                "",
                "end",
                values=(order_number, completion_date, income, expense, profit),
                tags=tags,
            )

        # Настройка цветов
        self.finance_tree.tag_configure(
            "positive", background=self.colors.get("success_light", "#e6f4ea")
        )
        self.finance_tree.tag_configure(
            "negative", background=self.colors.get("error_light", "#fce8e8")
        )

    def edit_expense(self, event):
        """Редактирование расхода по заказу"""
        selected = self.finance_tree.selection()
        if not selected:
            return

        item = self.finance_tree.item(selected[0])
        values = item["values"]
        order_number_display = values[0]

        # Получаем номер заказа для БД
        order_number = format_order_number_for_db(order_number_display)

        # Находим запись в финансах
        finances = self.db.get_finances("all")
        finance_record = None
        for f in finances:
            if f.get("order_number") == order_number:
                finance_record = f
                break

        if not finance_record:
            return

        # Диалог для ввода расхода
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Редактирование расхода")
        dialog.geometry("400x200")
        dialog.transient(self.root)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text=f"Заказ №{order_number_display}",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(pady=10)

        ctk.CTkLabel(dialog, text="Доход:").pack(anchor="w", padx=20)
        income_label = ctk.CTkLabel(
            dialog,
            text=format_price(str(finance_record.get("income", 0))),
            font=ctk.CTkFont(size=12),
        )
        income_label.pack(anchor="w", padx=20, pady=(0, 10))

        ctk.CTkLabel(dialog, text="Расход (₽):").pack(anchor="w", padx=20)
        expense_entry = ctk.CTkEntry(dialog, width=200)
        expense_entry.insert(0, str(finance_record.get("expense", 0)))
        expense_entry.pack(pady=(0, 10))

        def save_expense():
            try:
                expense = float(expense_entry.get().replace(",", "."))
                if self.db.update_finance_expense(order_number, expense):
                    dialog.destroy()
                    self.update_finance_display()
                    messagebox.showinfo("Успех", "Расход обновлён")
                else:
                    messagebox.showerror("Ошибка", "Не удалось обновить расход")
            except ValueError:
                messagebox.showerror("Ошибка", "Введите корректное число")

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=20)

        ctk.CTkButton(
            btn_frame, text="Сохранить", command=save_expense, width=100
        ).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Отмена", command=dialog.destroy, width=100).pack(
            side="left", padx=5
        )

    def create_context_menu(self):
        """Создание контекстного меню"""
        self.context_menu = ctk.CTkToplevel(self.root)
        self.context_menu.withdraw()
        self.context_menu.overrideredirect(True)

        menu_frame = ModernCard(self.context_menu, self.colors, corner_radius=8)
        menu_frame.pack(fill="both", expand=True)

        menu_items = [
            ("📄 Акт приема", self.print_receipt_act),
            ("🔧 Акт выполненных работ", self.print_completion_act),
            ("✏️ Редактировать", self.edit_device),
            ("👤 История клиента", self.show_client_history),
        ]

        for text, command in menu_items:
            # Обёртка: сначала скрываем меню, потом вызываем команду.
            # Без этого меню (CTkToplevel overrideredirect) остаётся поверх
            # главного окна и перекрывает нижние кнопки.
            def _make_wrapper(cmd):
                def _wrapper():
                    with contextlib.suppress(Exception):
                        self.context_menu.withdraw()
                    cmd()

                return _wrapper

            btn = ctk.CTkButton(
                menu_frame,
                text=text,
                command=_make_wrapper(command),
                fg_color="transparent",
                text_color=self.colors["text_primary"],
                hover_color=self.colors["bg_hover"],
                anchor="w",
                height=32,
                corner_radius=0,
                font=ctk.CTkFont(size=12),
            )
            btn.pack(fill="x", padx=4, pady=2)

    def _create_action_panel_in(self, parent):
        """Создание панели действий внутри указанного контейнера.

        Фиксированная высота + pack_propagate(False) гарантируют, что кнопки
        никогда не скрываются при изменении размера окна или открытии диалогов.
        """
        action_card = ModernCard(parent, self.colors, height=54)
        action_card.pack(fill="x", padx=12, pady=(0, 6))
        action_card.pack_propagate(False)

        buttons_container = ctk.CTkFrame(action_card, fg_color="transparent")
        buttons_container.pack(fill="x", padx=16, pady=10)

        action_buttons = [
            ("📄 Акт приема", self.print_receipt_act),
            ("🔧 Акт выполненных работ", self.print_completion_act),
            ("✏️ Редактировать", self.edit_device),
            ("👤 История клиента", self.show_client_history),
            ("📱 Мобильная версия", self.toggle_mobile_server),
        ]

        for text, command in action_buttons:
            btn = ModernButton(
                buttons_container,
                self.colors,
                variant="secondary",
                text=text,
                command=command,
                height=34,
                width=150,
            )
            btn.pack(side="left", padx=3)

    def toggle_mobile_server(self):
        """Запуск/просмотр мобильной версии (PWA-сервер)."""
        try:
            from gui.dialogs.pwa_qr_dialog import PWAQRDialog
            from pwa.server import PWAServerManager

            # Ленивая инициализация менеджера
            if not hasattr(self, "pwa_manager") or self.pwa_manager is None:
                self.pwa_manager = PWAServerManager()

            port = self.settings.get("pwa.port", 5000)

            # Если сервер не запущен — запускаем
            if not self.pwa_manager.is_running:
                started = self.pwa_manager.start(port=port)
                if not started:
                    messagebox.showerror(
                        "Ошибка",
                        "Не удалось запустить сервер мобильной версии.\n"
                        "Проверьте, что порт свободен.",
                    )
                    return
                # Небольшая пауза для старта Flask
                self.root.after(500, self._show_qr_dialog)

            # Если уже запущен — просто показываем QR
            else:
                self._show_qr_dialog()
        except ImportError:
            messagebox.showerror(
                "Ошибка",
                "Мобильная версия недоступна.\n"
                "Установите Flask: pip install flask qrcode",
            )
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось запустить сервер: {e}")

    def _show_qr_dialog(self):
        """Показывает диалог с QR-кодом."""
        from gui.dialogs.pwa_qr_dialog import PWAQRDialog

        if not self.pwa_manager or not self.pwa_manager.is_running:
            return
        url = self.pwa_manager.get_url()
        PWAQRDialog(
            self.root,
            url,
            self.colors,
            on_stop=self.stop_mobile_server,
            settings=self.settings,
        )

    def stop_mobile_server(self):
        """Останавливает PWA-сервер."""
        try:
            if hasattr(self, "pwa_manager") and self.pwa_manager is not None:
                self.pwa_manager.stop()
                self.update_status_bar("Мобильная версия остановлена")
        except Exception as e:
            logger.error(f"Ошибка остановки PWA-сервера: {e}", exc_info=True)

    def _create_status_bar_in(self, parent):
        """Создание статусной строки внутри указанного контейнера."""
        self.status_bar = ctk.CTkFrame(
            parent, fg_color=self.colors["bg_secondary"], height=28, corner_radius=0
        )
        self.status_bar.pack(fill="x", side="bottom")
        self.status_bar.pack_propagate(False)

        left_status = ctk.CTkFrame(self.status_bar, fg_color="transparent")
        left_status.pack(side="left", padx=16, pady=4)

        self.status_label = ModernLabel(
            left_status,
            self.colors,
            text="✅ Готово",
            font=ctk.CTkFont(size=11),
            text_color=self.colors["success"],
        )
        self.status_label.pack(side="left")

        separator = ctk.CTkFrame(
            left_status, width=1, height=14, fg_color=self.colors["border"]
        )
        separator.pack(side="left", padx=10)

        self.db_status = ModernLabel(
            left_status,
            self.colors,
            text="💾 БД активна",
            font=ctk.CTkFont(size=11),
            text_color=self.colors["success"],
        )
        self.db_status.pack(side="left")

        right_status = ctk.CTkFrame(self.status_bar, fg_color="transparent")
        right_status.pack(side="right", padx=16, pady=4)

        version_label = ModernLabel(
            right_status,
            self.colors,
            text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=10),
            text_color=self.colors["text_tertiary"],
        )
        version_label.pack(side="left")

    def show_context_menu(self, event):
        """Показ контекстного меню"""
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.geometry(f"+{event.x_root}+{event.y_root}")
            self.context_menu.deiconify()
            self.context_menu.lift()

    def _dismiss_context_menu(self, event):
        """Скрыть контекстное меню по клику"""
        with contextlib.suppress(Exception):
            self.context_menu.withdraw()

    def update_datetime(self):
        """Обновление времени"""
        try:
            now = datetime.now().strftime("%d.%m.%Y %H:%M")
            self.datetime_label.configure(text=now)
            self.root.after(1000, self.update_datetime)
        except Exception:
            pass

    def toggle_completed(self):
        """Переключение отображения выполненных заказов"""
        self.settings.set("show_completed", self.hide_completed_var.get())
        self.apply_filters()

    def _save_column_state(self, _event=None):
        """Сохраняет порядок и ширину колонок в настройки."""
        try:
            # Получаем текущий порядок displaycolumns
            dc = self.tree["displaycolumns"]
            if dc and dc != ("#all",):
                order = list(dc)
                self.settings.set("column_order", order)

            # Получаем ширины
            widths = {}
            for col in self.tree["columns"]:
                widths[col] = int(self.tree.column(col, "width"))
            self.settings.set("column_widths", widths)
        except Exception:
            pass

    def _auto_size_columns(self):
        """Автоматически подбирает ширину колонок под содержимое."""
        try:
            for col in self.tree["columns"]:
                self.tree.column(col, width=self.tree.column(col, "width"))
        except Exception:
            pass

    def _on_filter_changed(self, _choice=None):
        """Callback смены фильтра в выпадающих списках (статус/приоритет/тип/бренд).

        CTkComboBox с state='readonly' надёжнее через command, чем через
        bind('<<ComboboxSelected>>'), который не всегда срабатывает.
        """
        self.apply_filters()

    def _collect_filter_values(self, dict_type: str, db_column: str) -> list:
        """Собирает значения для фильтра: словарь + уникальные из заказов БД.

        Объединяет, чтобы в фильтре были и шаблонные значения, и те, что
        реально встречаются в заказах (могут не быть в словаре). Сортировка.
        """
        values = []
        try:
            # Из словаря
            values.extend(self.db.get_dict_values(dict_type))
            # Уникальные из заказов
            for d in self.db.get_all_devices(include_completed=True):
                v = (d.get(db_column) or "").strip()
                if v and v not in values:
                    values.append(v)
        except Exception as e:
            logger.exception(f"Ошибка сбора значений фильтра {dict_type}: {e}")
        return sorted(values)

    def _render_device_row(self, device: dict[str, Any]) -> tuple:
        """Формирует кортеж (values, tag) для вставки строки в таблицу устройств.

        Извлекает общий код из load_devices / apply_filters / search_devices.
        Включает колонку «Дней» (сколько дней в ремонте) и иконки приоритета.
        """
        # Имя устройства: brand+model или device_type+model или model
        if device.get("brand") and device.get("model"):
            device_name = f"{device['brand']} {device['model']}"
        elif device.get("device_type") and device.get("model"):
            device_name = f"{device['device_type']} {device['model']}"
        else:
            device_name = device.get("model", "")

        receipt_date = self.format_datetime_for_display(device.get("receipt_date", ""))
        completion_date = (
            self.format_datetime_for_display(device.get("completion_date", ""))
            if device.get("completion_date")
            else ""
        )

        # Колонка «Дней» — сколько дней заказ в ремонте
        receipt_date_raw = device.get("receipt_date", "")
        status_val = device.get("status", "")
        if status_val in ("Выдан клиенту", "Отказ от ремонта"):
            days_str = "—"
        else:
            days = get_days_since_receipt(receipt_date_raw)
            days_str = str(days) if days > 0 else "0"

        defect = device.get("defect", "")
        if defect and len(defect) > 35:
            defect = defect[:35] + "..."

        photos = device.get("photos", "")
        photo_count = len(photos.split(",")) if photos else 0
        photo_indicator = f"📸 {photo_count}" if photo_count > 0 else "—"

        # Иконка приоритета
        priority_val = device.get("priority", "Обычный")
        priority_icon = {
            "Срочный": "⚡ Срочный",
            "Высокий": "▲ Высокий",
            "Обычный": "▬ Обычный",
            "Низкий": "▼ Низкий",
        }.get(priority_val, priority_val)

        # Тег строки для цветовой индикации
        if status_val in ("Выдан клиенту", "Отказ от ремонта"):
            tag = "completed"
        else:
            days = get_days_since_receipt(receipt_date_raw)
            if days > 14:
                tag = "urgent"
            elif days > 7:
                tag = "warning"
            else:
                tag = "normal"

        values = (
            format_order_number_for_display(device.get("order_number", "")),
            receipt_date,
            days_str,
            completion_date,
            device_name,
            device.get("client_name", ""),
            format_phone(device.get("phone", "")),
            defect,
            status_val,
            priority_icon,
            device.get("engineer", ""),
            format_price(device.get("total_price", ""))
            if device.get("total_price")
            else "",
            photo_indicator,
        )
        return values, tag

    def _clear_tree_and_populate(self, devices, count_label_text=None):
        """Очищает таблицу и заполняет её списком устройств через _render_device_row."""
        for item in self.tree.get_children():
            self.tree.delete(item)

        for device in devices:
            values, tag = self._render_device_row(device)
            self.tree.insert("", "end", values=values, tags=(tag,))

        # Обновляем статус-бар количеством заказов
        count = count_label_text or f"Заказов: {len(devices)}"
        if hasattr(self, "status_label"):
            self.update_status_bar(count)

    def apply_filters(self):
        """Применение фильтров"""
        try:
            status = self.status_filter.get()
            priority = self.priority_filter.get()
            device_type = (
                self.device_type_filter.get()
                if hasattr(self, "device_type_filter")
                else "Все"
            )
            brand = self.brand_filter.get() if hasattr(self, "brand_filter") else "Все"
            hide_completed = self.hide_completed_var.get()
            devices = self.db.get_devices_by_filters(
                status, priority, not hide_completed, device_type, brand
            )
            self._clear_tree_and_populate(devices)
        except Exception as e:
            logger.exception(f"Ошибка применения фильтров: {e}")

    def load_devices(self):
        """Загрузка устройств"""
        try:
            hide_completed = self.hide_completed_var.get()
            devices = self.db.get_all_devices(include_completed=not hide_completed)
            self._clear_tree_and_populate(devices)
        except Exception as e:
            logger.exception(f"Ошибка загрузки устройств: {e}")

    def _quick_delete_selected(self):
        """Быстрое удаление выбранного заказа (Delete)."""
        selected = self.tree.selection()
        if not selected:
            return
        if self.settings.get("confirm_delete", True):
            if not messagebox.askyesno("Удаление", "Удалить выбранный заказ?"):
                return
        order_number_display = self.tree.item(selected[0])["values"][0]
        device_id = self.get_device_id_by_order_number(order_number_display)
        if device_id:
            try:
                # Удаляем через фасад Database вместо прямого SQL
                success = self.db.delete_device(device_id)
                if success:
                    self.load_devices()
                    self.dashboard.update_stats()
                    self.update_finance_display()
                    self.update_status_bar(f"Заказ #{order_number_display} удалён")
                else:
                    messagebox.showerror("Ошибка", "Не удалось удалить заказ")
            except Exception as e:
                logger.exception(f"Ошибка удаления: {e}")
                messagebox.showerror("Ошибка", f"Не удалось удалить заказ: {e}")

    def refresh_orders(self):
        """Ручное обновление списка заказов из БД (кнопка «🔄 Обновить»).

        Перезагружает данные с учётом текущих фильтров/поиска. Используется,
        чтобы увидеть изменения, внесённые через PWA (фото, новые заказы),
        без перезапуска программы.
        """
        try:
            # Если есть активный поиск — обновляем поиск, иначе фильтры
            search_text = (
                self.search_var.get().strip() if hasattr(self, "search_var") else ""
            )
            if search_text:
                self.search_devices()
            else:
                self.apply_filters()
            # Обновляем дашборд и финансы
            if hasattr(self, "dashboard"):
                self.dashboard.update_stats()
            if hasattr(self, "update_finance_display"):
                self.update_finance_display()
            self.update_status_bar("Список заказов обновлён")
        except Exception as e:
            logger.exception(f"Ошибка обновления: {e}")

    def show_overdue_orders(self):
        """Показ просроченных заказов (>14 дней в ремонте)."""
        try:
            all_devices = self.db.get_all_devices(include_completed=False)
            overdue = [
                d
                for d in all_devices
                if get_days_since_receipt(d.get("receipt_date", "")) > 14
            ]
            self._clear_tree_and_populate(
                overdue, count_label_text=f"Просроченных: {len(overdue)}"
            )
            self.update_status_bar(f"⏰ Просроченных заказов: {len(overdue)}")
        except Exception as e:
            logger.exception(f"Ошибка фильтра просроченных: {e}")

    def show_today_orders(self):
        """Показ заказов, принятых сегодня."""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            all_devices = self.db.get_all_devices(include_completed=True)
            today_orders = [
                d
                for d in all_devices
                if (d.get("receipt_date", "") or "")[:10] == today
            ]
            self._clear_tree_and_populate(
                today_orders, count_label_text=f"Сегодня: {len(today_orders)}"
            )
            self.update_status_bar(f"📅 Принято сегодня: {len(today_orders)}")
        except Exception as e:
            logger.exception(f"Ошибка фильтра «сегодня»: {e}")

    def show_week_orders(self):
        """Показ заказов за последнюю неделю."""
        try:
            week_ago = datetime.now() - timedelta(days=7)
            all_devices = self.db.get_all_devices(include_completed=True)
            week_orders = []
            for d in all_devices:
                rd = d.get("receipt_date", "")
                if rd:
                    try:
                        dt = datetime.strptime(rd[:10], "%Y-%m-%d")
                        if dt >= week_ago:
                            week_orders.append(d)
                    except ValueError, TypeError:
                        pass
            self._clear_tree_and_populate(
                week_orders, count_label_text=f"За неделю: {len(week_orders)}"
            )
            self.update_status_bar(f"📅 За неделю: {len(week_orders)}")
        except Exception as e:
            logger.exception(f"Ошибка фильтра «неделя»: {e}")

    def _start_auto_sync(self):
        """Запускает периодическое автообновление списка заказов.

        Интервал берётся из настроек pwa.sync_interval (секунд).
        Если 0 или auto_sync=False — автообновление выключено.
        Позволяет видеть изменения из PWA (фото, новые заказы) без ручного
        обновления.
        """
        self._auto_sync_after_id = None
        try:
            auto_sync = self.settings.get("pwa.auto_sync", True)
            interval = self.settings.get("pwa.sync_interval", 30)
        except Exception:
            auto_sync = False
            interval = 0

        if not auto_sync or not interval or interval <= 0:
            return

        def _tick():
            # Не обновляем, если открыто модальное окно (форма заказа и т.п.),
            # чтобы не сбить выбор пользователя.
            try:
                # Тихо перезагружаем, сохраняя текущие фильтры
                search_text = (
                    self.search_var.get().strip() if hasattr(self, "search_var") else ""
                )
                if search_text:
                    # При активном поиске автообновление не делаем (мешает)
                    pass
                else:
                    self.apply_filters()
            except Exception:
                pass
            # Планируем следующий тик
            self._auto_sync_after_id = self.root.after(interval * 1000, _tick)

        self._auto_sync_after_id = self.root.after(interval * 1000, _tick)

    def _stop_auto_sync(self):
        """Останавливает автообновление."""
        if getattr(self, "_auto_sync_after_id", None) is not None:
            with contextlib.suppress(Exception):
                self.root.after_cancel(self._auto_sync_after_id)
            self._auto_sync_after_id = None

    def search_devices(self):
        """Поиск устройств"""
        try:
            search_text = self.search_var.get().strip().lower()
            hide_completed = self.hide_completed_var.get()

            if not search_text:
                self.load_devices()
                return

            devices = self.db.search_devices(
                search_text, include_completed=not hide_completed
            )
            self._clear_tree_and_populate(
                devices, count_label_text=f"Найдено: {len(devices)}"
            )
        except Exception as e:
            logger.exception(f"Ошибка поиска: {e}")

    def sort_treeview(self, col):
        """Сортировка таблицы"""
        if self.sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = col
            self.sort_reverse = False

        items = [
            (self.tree.set(item, col), item) for item in self.tree.get_children("")
        ]

        if col == "Цена":
            items.sort(
                key=lambda x: (
                    float(x[0].replace("₽", "").replace(" ", "").replace(",", ""))
                    if x[0] != "0 ₽"
                    else 0
                ),
                reverse=self.sort_reverse,
            )
        else:
            items.sort(reverse=self.sort_reverse)

        for index, (_, item) in enumerate(items):
            self.tree.move(item, "", index)

        for heading in self.tree["columns"]:
            if heading == col:
                self.tree.heading(
                    heading, text=f"{heading} {'▼' if self.sort_reverse else '▲'}"
                )
            else:
                self.tree.heading(heading, text=heading)

    def get_device_id_by_order_number(self, order_number_display: str) -> int | None:
        """Получение ID устройства по номеру заказа"""
        try:
            db_order_number = format_order_number_for_db(order_number_display)
            device = self.db.get_device_by_order_number(db_order_number)
            if device:
                return device.get("id")
            return None
        except Exception as e:
            logger.exception(f"Ошибка получения ID устройства: {e}")
            return None

    def on_device_double_click(self, event):
        """Обработка двойного клика"""
        self.edit_device()

    def edit_device(self):
        """Редактирование устройства"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Предупреждение", "Выберите заказ")
            return

        order_number_display = self.tree.item(selected[0])["values"][0]
        device_id = self.get_device_id_by_order_number(order_number_display)

        if not device_id:
            messagebox.showerror(
                "Ошибка",
                f"Не удалось найти устройство с номером {order_number_display}",
            )
            return

        device = self.db.get_device(device_id)

        if device:
            self.open_edit_device_window(device)
        else:
            messagebox.showerror("Ошибка", "Не удалось загрузить данные")

    def open_add_device_window(self):
        """Открытие окна добавления заказа"""
        dialog = DeviceFormDialog(
            self.root,
            self.db,
            self.client_db,
            self.photo_manager,
            self.colors,
            is_new=True,
            settings=self.settings,
        )
        self.root.wait_window(dialog)

        if dialog.result:
            self.load_devices()
            self.dashboard.update_stats()
            self.update_finance_display()
            self.update_status_bar(
                f"Создан заказ: #{format_order_number_for_display(dialog.result.get('order_number', ''))}"
            )

    def open_edit_device_window(self, device_data: dict[str, Any]):
        """Открытие окна редактирования заказа"""
        dialog = DeviceFormDialog(
            self.root,
            self.db,
            self.client_db,
            self.photo_manager,
            self.colors,
            is_new=False,
            device_data=device_data,
            settings=self.settings,
        )
        self.root.wait_window(dialog)

        if dialog.result:
            self.load_devices()
            self.dashboard.update_stats()
            self.update_finance_display()
            self.update_status_bar("Заказ обновлен")

    def _load_act_template(self, act_type: str) -> dict:
        """Загружает шаблон акта из JSON (изменения из редактора актов).

        act_type: 'receipt' или 'completion'. Возвращает dict (пустой при ошибке).
        Это позволяет применять настройки редактора (заголовок, поля, цвет,
        условия, логотип) к актам, печатаемым из главного окна.
        """
        import json
        from pathlib import Path

        try:
            reports_dir = Path(__file__).parent.parent / "reports"
            template_dir = reports_dir / "templates"
            filename = (
                "receipt_act.json" if act_type == "receipt" else "completion_act.json"
            )
            path = template_dir / filename
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.exception(f"Не удалось загрузить шаблон акта: {e}")
        return {}

    def print_receipt_act(self):
        """Печать акта приема"""
        try:
            selected = self.tree.selection()
            if not selected:
                messagebox.showwarning("Предупреждение", "Выберите заказ")
                return

            order_number_display = self.tree.item(selected[0])["values"][0]
            device_id = self.get_device_id_by_order_number(order_number_display)
            device = self.db.get_device(device_id)

            if not device:
                messagebox.showerror(
                    "Ошибка",
                    f"Не удалось найти устройство с номером {order_number_display}",
                )
                return

            filename = self.report_gen.generate_receipt_act(device)
            if filename and os.path.exists(filename):
                with open(filename, encoding="utf-8") as f:
                    content = f.read()

                order_number = format_order_number_for_display(
                    device.get("order_number", "")
                )
                template = self._load_act_template("receipt")
                # Окно предпросмотра само генерирует PDF с применением шаблона
                # редактора (header_text, поля, цвет, логотип). Печать/экспорт —
                # через кнопки в окне предпросмотра.
                ActPreviewWindow(
                    self.root,
                    f"Акт приема {order_number}",
                    content,
                    self.colors,
                    "receipt",
                    device,
                    template,
                    settings=self.settings,
                )
            else:
                messagebox.showerror("Ошибка", "❌ Не удалось создать файл акта")

        except Exception as e:
            messagebox.showerror("Ошибка", f"❌ Ошибка создания документа: {e!s}")

    def print_completion_act(self):
        """Печать акта выполненных работ"""
        try:
            selected = self.tree.selection()
            if not selected:
                messagebox.showwarning("Предупреждение", "Выберите заказ")
                return

            order_number_display = self.tree.item(selected[0])["values"][0]
            device_id = self.get_device_id_by_order_number(order_number_display)
            device = self.db.get_device(device_id)

            if not device:
                messagebox.showerror(
                    "Ошибка",
                    f"Не удалось найти устройство с номером {order_number_display}",
                )
                return

            work_items_json = device.get("work_items", "")
            if work_items_json:
                work_manager = WorkItemsManager()
                work_manager.from_json(work_items_json)
                device["completed_work"] = work_manager.get_description_summary()

            filename = self.report_gen.generate_completion_act(device)
            if filename and os.path.exists(filename):
                with open(filename, encoding="utf-8") as f:
                    content = f.read()

                order_number = format_order_number_for_display(
                    device.get("order_number", "")
                )
                template = self._load_act_template("completion")
                ActPreviewWindow(
                    self.root,
                    f"Акт выполненных работ {order_number}",
                    content,
                    self.colors,
                    "completion",
                    device,
                    template,
                    settings=self.settings,
                )

                # Печать акта выполненных работ = выдача устройства клиенту.
                # Меняем статус на «Выдан клиенту» (с подтверждением).
                if device.get("status") != "Выдан клиенту":
                    if messagebox.askyesno(
                        "Выдача устройства",
                        f"Изменить статус заказа #{order_number} на «Выдан клиенту»?",
                    ) and self.db.update_device_status(device_id, "Выдан клиенту"):
                        self.load_devices()
                        self.dashboard.update_stats()
                        self.update_finance_display()
                        self.update_status_bar(f"Заказ #{order_number} выдан клиенту")
            else:
                messagebox.showerror("Ошибка", "❌ Не удалось создать файл акта")

        except Exception as e:
            messagebox.showerror("Ошибка", f"❌ Ошибка создания документа: {e!s}")

    def _ask_dual_print_mode(self):
        """Показывает кастомный диалог выбора режима печати двух актов.

        Возвращает: 'receipt2', 'completion2', 'both' или None (закрыто).
        """
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Два акта на листе A4")
        dialog.geometry("400x320")
        dialog.transient(self.root)
        dialog.grab_set()

        # Центрируем
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 400) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 320) // 2
        dialog.geometry(f"+{x}+{y}")

        result = {"choice": None}

        ctk.CTkLabel(
            dialog,
            text="📋 Выберите режим печати",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(pady=(20, 15))

        ctk.CTkLabel(
            dialog,
            text="Что напечатать на одном листе A4?",
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_secondary"],
        ).pack(pady=(0, 15))

        def _choose(value):
            result["choice"] = value
            dialog.destroy()

        ModernButton(
            dialog,
            self.colors,
            variant="primary",
            text="📄📄  2× Акт приёма",
            command=lambda: _choose("receipt2"),
            height=42,
            width=320,
        ).pack(pady=4)

        ModernButton(
            dialog,
            self.colors,
            variant="primary",
            text="🔧🔧  2× Акт выполненных работ",
            command=lambda: _choose("completion2"),
            height=42,
            width=320,
        ).pack(pady=4)

        ModernButton(
            dialog,
            self.colors,
            variant="secondary",
            text="📄🔧  Акт приёма + Акт работ",
            command=lambda: _choose("both"),
            height=42,
            width=320,
        ).pack(pady=4)

        ModernButton(
            dialog,
            self.colors,
            variant="secondary",
            text="✖ Отмена",
            command=dialog.destroy,
            height=36,
            width=320,
        ).pack(pady=(12, 4))

        self.root.wait_window(dialog)
        return result["choice"]

    def print_dual_acts(self):
        """Печать двух актов на одном листе A4 с выбором режима."""
        try:
            selected = self.tree.selection()
            if not selected:
                messagebox.showwarning("Предупреждение", "Выберите заказ")
                return

            order_number_display = self.tree.item(selected[0])["values"][0]
            device_id = self.get_device_id_by_order_number(order_number_display)
            device = self.db.get_device(device_id)

            if not device:
                messagebox.showerror(
                    "Ошибка",
                    f"Не удалось найти устройство с номером {order_number_display}",
                )
                return

            # work_items для акта выполненных работ
            work_items_json = device.get("work_items", "")
            if work_items_json:
                work_manager = WorkItemsManager()
                work_manager.from_json(work_items_json)
                device["completed_work"] = work_manager.get_description_summary()

            # Кастомный диалог выбора режима печати
            choice = self._ask_dual_print_mode()
            if choice is None:
                return  # пользователь закрыл окно

            # 'receipt2' → 2×receipt, 'completion2' → 2×completion, 'both' → receipt+completion
            if choice == "receipt2":
                act_type1, act_type2 = "receipt", "receipt"
                tpl_key = "receipt"
            elif choice == "completion2":
                act_type1, act_type2 = "completion", "completion"
                tpl_key = "completion"
            else:
                act_type1, act_type2 = "receipt", "completion"
                tpl_key = "receipt"

            from tkinter import filedialog

            from reports.report_renderer import ActPDFGenerator

            file_path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf")],
                initialfile=f"acts_{format_order_number_for_display(device.get('order_number', ''))}.pdf",
            )
            if not file_path:
                return

            tpl = self._load_act_template(tpl_key)
            gen = ActPDFGenerator(template_data=tpl)
            ok = gen.generate_dual_pdf(
                file_path, device, device, act_type1=act_type1, act_type2=act_type2
            )
            if ok:
                messagebox.showinfo(
                    "Успех", f"Два акта на листе A4 сохранены:\n{file_path}"
                )
                if sys.platform == "win32":
                    os.startfile(file_path)
            else:
                messagebox.showerror("Ошибка", "Не удалось создать PDF")
        except Exception as e:
            messagebox.showerror("Ошибка", f"❌ Ошибка: {e!s}")

    def show_client_history(self):
        """Показ истории клиента"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Предупреждение", "Выберите заказ")
            return

        item = self.tree.item(selected[0])
        values = item["values"]
        if len(values) < 6:
            return

        client_name = values[4]
        client_phone = values[5]

        if client_name and client_phone:
            order_number_display = values[0]
            db_order_number = format_order_number_for_db(order_number_display)
            device = self.db.get_device_by_order_number(db_order_number)
            client_status = device.get("client_status", "Новый") if device else "Новый"

            ClientHistoryWindow(
                self.root,
                self.db,
                self.client_db,
                client_name,
                client_phone,
                client_status,
                self.colors,
                settings=self.settings,
            )

    def format_datetime_for_display(self, date_str):
        """Форматирование даты и времени для отображения"""
        if not date_str:
            return ""
        try:
            if " " in date_str:
                dt = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
                return dt.strftime("%d.%m.%Y %H:%M")
            else:
                dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
                return dt.strftime("%d.%m.%Y")
        except ValueError, TypeError:
            return date_str[:10] if date_str else ""

    def show_activation(self):
        """Показывает окно активации лицензии из главного окна."""
        try:
            from gui.dialogs.activation_dialog import ActivationDialog
            from utils.license_manager import LicenseManager

            lic = LicenseManager()
            dialog = ActivationDialog(self.root, lic, self.colors)
            self.root.wait_window(dialog)
        except Exception as e:
            import traceback

            traceback.print_exc()
            messagebox.showerror("Ошибка", f"Не удалось открыть активацию: {e}")

    def open_settings(self):
        """Открытие окна настроек"""
        SettingsWindow(self.root, self.settings, self)

    def open_dictionaries_manager(self):
        """Открытие менеджера словарей"""
        DictionariesManagerWindow(
            self.root, self.db, self.colors, settings=self.settings
        )

    def open_report_editor(self):
        """Открытие редактора актов (сразу, с вкладками приёма/выполненных работ)."""
        try:
            from reports.report_editor import ReportEditor

            ReportEditor(self.root, self.colors, settings=self.settings)
        except ImportError as e:
            messagebox.showerror(
                "Ошибка",
                f"Не удалось загрузить редактор: {e}\n\nУстановите reportlab: pip install reportlab",
            )

    def update_status_bar(self, message: str):
        """Обновление статусной строки"""
        with contextlib.suppress(Exception):
            self.status_label.configure(text=f"✅ {message}")

    def on_closing(self):
        """Обработка закрытия приложения"""
        try:
            # Останавливаем авто-синхронизацию
            self._stop_auto_sync()
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
