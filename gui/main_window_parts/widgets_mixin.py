#!/usr/bin/env python3
"""WidgetsMixin — построение виджетов главного окна (шапка, поиск, вкладки,
таблица заказов, контекстное меню, панель действий, статус-бар). См.
AUDIT_REPORT_v25.md, Task T (перенесено из main_window.py без изменения
поведения)."""

from __future__ import annotations

import contextlib

import customtkinter as ctk
from tkinter import ttk

from config import APP_VERSION
from gui.widgets import ModernButton, ModernCard, ModernCombobox, ModernLabel, ModernSwitch
from gui.widgets.dashboard import PremiumDashboard
from gui.widgets.modern import ModernEntry
from gui.widgets.skeleton import SKELETON_TAG, BusyIndicator
from domain.constants import PRIORITIES, STATUSES


class WidgetsMixin:
    """Требует от финального класса ServiceCenterApp: self.root,
    self.main_container, self.colors, self.settings, self.db,
    self.employees_api — все выставляются в ServiceCenterApp.__init__."""

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
            settings=self.settings,
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

        # Вкладка "Базис" — технические/административные настройки (БД,
        # полномочия, блокировки), отделённые от обычного диалога настроек
        # (см. AUDIT_REPORT_v25.md, Task U). Лёгкая — строим сразу, без
        # ленивой загрузки (в отличие от Финансов, здесь нет тяжёлых
        # запросов к БД).
        basis_tab = self.tabview.add("🔧 Базис")
        self.create_basis_tab(basis_tab)

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

    def _attach_tooltip(self, widget, text: str) -> None:
        """Прикрепляет tooltip к виджету, не прерывая инициализацию UI при ошибке."""
        try:
            from gui.widgets.tooltip import create_tooltip

            create_tooltip(widget, text)
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
        self._attach_tooltip(editor_btn, "Редактор актов")

        # Селектор текущего сотрудника ("ФИО — логин") — без авторизации,
        # просто отмечает, кто создаёт/меняет заказы (created_by/updated_by).
        self.employee_selector = ModernCombobox(
            right_container,
            self.colors,
            values=["Не выбран"],
            width=170,
            height=34,
            command=self._on_employee_selected,
        )
        self.employee_selector.pack(side="right", padx=(8, 0))
        self._attach_tooltip(self.employee_selector, "Текущий сотрудник")
        self.refresh_employee_selector()

        # Кнопка управления сотрудниками
        employees_btn = ModernButton(
            right_container,
            self.colors,
            variant="secondary",
            text="👥",
            command=self.open_employees_manager,
            width=40,
            height=34,
        )
        employees_btn.pack(side="right", padx=(8, 0))
        self._attach_tooltip(employees_btn, "Сотрудники")

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
        self._attach_tooltip(dict_btn, "Словари")

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
        self._attach_tooltip(settings_btn, "Настройки")

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
        self._attach_tooltip(license_btn, "Активация лицензии")

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
        # Плейсхолдер-строки на время фоновой загрузки (Task O) — см.
        # gui/widgets/skeleton.py::insert_skeleton_rows.
        self.tree.tag_configure(
            SKELETON_TAG, foreground=self.colors.get("text_tertiary", "#888888")
        )

        self.create_context_menu()

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

        # Busy-индикатор фоновой загрузки таблицы заказов (Task O) — сам
        # управляет своей видимостью через pack/pack_forget в start()/stop(),
        # скрыт по умолчанию, поэтому здесь НЕ packнут.
        self.busy_indicator = BusyIndicator(left_status, self.colors)

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
