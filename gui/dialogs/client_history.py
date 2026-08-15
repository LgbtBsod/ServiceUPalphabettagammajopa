#!/usr/bin/env python3

"""Современное окно истории клиента"""

import contextlib
import csv
import json
import logging
import os
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from typing import Any

import customtkinter as ctk

from database import ClientDatabaseManager, Database
from gui.widgets.modern import (
    ModernButton,
    ModernCard,
    ModernCombobox,
    ModernEntry,
)
from managers import ReportGenerator
from utils.formatters import (
    format_date,
    format_order_number_for_db,
    format_order_number_for_display,
    format_phone,
    format_price,
)

logger = logging.getLogger(__name__)


class ClientHistoryWindow(ctk.CTkToplevel):
    """Современное окно истории ремонтов клиента"""

    def __init__(
        self,
        parent,
        db: Database,
        client_db: ClientDatabaseManager,
        client_name: str,
        client_phone: str,
        client_status: str,
        colors: dict,
        settings=None,
        report_gen: ReportGenerator | None = None,
    ):
        super().__init__(parent)
        self.db = db
        self.client_db = client_db
        # Единственный экземпляр из Kernel — см. AUDIT_REPORT_v21.md
        self.report_gen = report_gen or ReportGenerator()
        self.parent_app = parent
        self.client_name = client_name
        self.client_phone = client_phone
        self.client_status = client_status
        self.colors = colors
        self.settings = settings  # опционально, для сохранения геометрии
        self.all_history = []

        self.title(f"История клиента: {client_name}")
        from utils.window_state import restore_window_geometry

        restore_window_geometry(
            self.settings,
            "client_history",
            self,
            default_w=1200,
            default_h=700,
            min_w=950,
            min_h=560,
        )

        self.transient(parent)
        self.grab_set()

        # Сохраняем геометрию при закрытии
        self.protocol("WM_DELETE_WINDOW", self._close_with_geometry)

        self.create_widgets()
        self.load_data()

    def _close_with_geometry(self):
        """Сохраняет геометрию окна в config и закрывает его."""
        from utils.window_state import close_dialog_with_geometry

        close_dialog_with_geometry(self, self.settings, "client_history")

    def create_widgets(self):
        """Создание виджетов"""
        main_container = ctk.CTkFrame(self, fg_color=self.colors["bg_primary"])
        main_container.pack(fill="both", expand=True, padx=10, pady=10)

        # Заголовок с аватаром
        header_card = ModernCard(main_container, self.colors)
        header_card.pack(fill="x", pady=(0, 10))

        header_frame = ctk.CTkFrame(header_card, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=12)

        # Аватар клиента
        avatar_frame = ctk.CTkFrame(
            header_frame,
            width=60,
            height=60,
            corner_radius=30,
            fg_color=self.colors["accent"],
        )
        avatar_frame.pack(side="left", padx=(0, 15))
        avatar_frame.pack_propagate(False)

        avatar_label = ctk.CTkLabel(
            avatar_frame, text="👤", font=ctk.CTkFont(size=30), text_color="white"
        )
        avatar_label.pack(expand=True)

        # Информация о клиенте
        info_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True)

        name_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        name_frame.pack(anchor="w")

        ctk.CTkLabel(
            name_frame,
            text=self.client_name,
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors["text_primary"],
        ).pack(side="left")

        # Статус клиента
        status_colors = {"VIP": "#ffd700", "Постоянный": "#4caf50", "Новый": "#9e9e9e"}
        status_color = status_colors.get(self.client_status, "#9e9e9e")
        status_badge = ctk.CTkFrame(
            info_frame, fg_color=status_color, corner_radius=10, height=24
        )
        status_badge.pack(anchor="w", pady=(5, 0))
        status_badge.pack_propagate(False)
        ctk.CTkLabel(
            status_badge,
            text=self.client_status,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="white",
            padx=10,
            pady=2,
        ).pack()

        # Контактная информация
        contact_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        contact_frame.pack(anchor="w", pady=(8, 0))
        ctk.CTkLabel(contact_frame, text="📞", font=ctk.CTkFont(size=14)).pack(
            side="left", padx=(0, 5)
        )
        ctk.CTkLabel(
            contact_frame,
            text=format_phone(self.client_phone),
            font=ctk.CTkFont(size=13),
            text_color=self.colors["text_secondary"],
        ).pack(side="left")

        # Статистика
        stats_card = ModernCard(main_container, self.colors)
        stats_card.pack(fill="x", pady=(0, 10))

        stats_grid = ctk.CTkFrame(stats_card, fg_color="transparent")
        stats_grid.pack(fill="x", padx=15, pady=12)

        stats_items = [
            ("📊", "Всего ремонтов", "0", self.colors["accent"]),
            ("✅", "Завершено", "0", self.colors["success"]),
            ("💰", "Общая сумма", "0 ₽", self.colors["warning"]),
            ("⭐", "Любимое устройство", "—", self.colors["text_secondary"]),
        ]

        self.stats_labels = {}
        for i, (icon, label, value, color) in enumerate(stats_items):
            stat_frame = ctk.CTkFrame(stats_grid, fg_color="transparent")
            stat_frame.grid(row=0, column=i, padx=5, pady=5, sticky="nsew")

            ctk.CTkLabel(
                stat_frame, text=icon, font=ctk.CTkFont(size=24), text_color=color
            ).pack(anchor="w")
            ctk.CTkLabel(
                stat_frame,
                text=label,
                font=ctk.CTkFont(size=11),
                text_color=self.colors["text_secondary"],
            ).pack(anchor="w", pady=(2, 0))
            value_label = ctk.CTkLabel(
                stat_frame,
                text=value,
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=color,
            )
            value_label.pack(anchor="w", pady=(2, 0))
            self.stats_labels[label] = value_label

        for i in range(4):
            stats_grid.grid_columnconfigure(i, weight=1)

        # Панель поиска
        search_card = ModernCard(main_container, self.colors)
        search_card.pack(fill="x", pady=(0, 10))

        search_frame = ctk.CTkFrame(search_card, fg_color="transparent")
        search_frame.pack(fill="x", padx=15, pady=10)

        search_icon = ctk.CTkLabel(search_frame, text="🔍", font=ctk.CTkFont(size=14))
        search_icon.pack(side="left", padx=(0, 8))

        self.search_entry = ModernEntry(
            search_frame,
            self.colors,
            placeholder_text="Поиск по заказам, устройствам...",
            width=250,
            height=32,
        )
        self.search_entry.pack(side="left", padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", lambda e: self.filter_history())

        ctk.CTkLabel(search_frame, text="Статус:").pack(side="left", padx=(10, 5))
        self.status_filter = ModernCombobox(
            search_frame,
            self.colors,
            values=[
                "Все",
                "Диагностика",
                "Ожидание запчастей",
                "В ремонте",
                "Готов к выдаче",
                "Выдан клиенту",
                "Отказ от ремонта",
            ],
            width=140,
            height=32,
        )
        self.status_filter.set("Все")
        self.status_filter.pack(side="left", padx=(0, 10))
        self.status_filter.bind("<<ComboboxSelected>>", lambda e: self.filter_history())

        ctk.CTkLabel(search_frame, text="Год:").pack(side="left", padx=(10, 5))
        self.year_filter = ModernCombobox(
            search_frame, self.colors, values=["Все"], width=100, height=32
        )
        self.year_filter.set("Все")
        self.year_filter.pack(side="left")
        self.year_filter.bind("<<ComboboxSelected>>", lambda e: self.filter_history())

        reset_btn = ModernButton(
            search_frame,
            self.colors,
            variant="secondary",
            text="Сбросить",
            command=self.reset_filters,
            width=80,
            height=32,
        )
        reset_btn.pack(side="right", padx=(10, 0))

        export_btn = ModernButton(
            search_frame,
            self.colors,
            variant="primary",
            text="📊 Экспорт",
            command=self.export_history,
            width=100,
            height=32,
        )
        export_btn.pack(side="right", padx=(5, 0))

        # Таблица с историей
        table_card = ModernCard(main_container, self.colors)
        table_card.pack(fill="both", expand=True)

        table_header = ctk.CTkFrame(table_card, fg_color="transparent")
        table_header.pack(fill="x", padx=15, pady=(10, 5))

        ctk.CTkLabel(
            table_header,
            text="📋 История ремонтов",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(side="left")

        self.count_label = ctk.CTkLabel(
            table_header,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_secondary"],
        )
        self.count_label.pack(side="right")

        # Контейнер для таблицы
        tree_container = ctk.CTkFrame(table_card, fg_color="transparent")
        tree_container.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        # Sтиль для Treeview
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background=self.colors["bg_secondary"],
            foreground=self.colors["text_primary"],
            fieldbackground=self.colors["bg_secondary"],
            borderwidth=0,
            font=("Segoe UI", 11),
            rowheight=35,
        )
        style.configure(
            "Treeview.Heading",
            background=self.colors["bg_tertiary"],
            foreground=self.colors["text_primary"],
            borderwidth=0,
            font=("Segoe UI", 11, "bold"),
        )
        style.map("Treeview", background=[("selected", self.colors["accent"])])

        # Колонки таблицы
        columns = (
            "Дата",
            "Заказ №",
            "Устройство",
            "Неисправность",
            "Работы",
            "Статус",
            "Цена",
            "Фото",
        )

        self.tree = ttk.Treeview(
            tree_container, columns=columns, show="headings", height=15
        )

        column_widths = [120, 80, 200, 200, 220, 120, 100, 70]
        for col, width in zip(columns, column_widths, strict=False):
            self.tree.heading(
                col, text=col, command=lambda c=col: self.sort_by_column(c)
            )
            self.tree.column(col, width=width, minwidth=50)

        # Скроллы
        # Авто-скрываемые скроллбары
        from gui.widgets.auto_scroll import attach_auto_scrollbars

        attach_auto_scrollbars(tree_container, self.tree)

        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        # Привязываем события
        self.tree.bind("<Double-Button-1>", self.edit_order_from_history)
        self.tree.bind("<Button-3>", self.show_context_menu_history)

        # Создаем контекстное меню
        self.history_context_menu = ctk.CTkToplevel(self)
        self.history_context_menu.withdraw()
        self.history_context_menu.overrideredirect(True)

        menu_frame = ModernCard(self.history_context_menu, self.colors, corner_radius=6)
        menu_frame.pack(fill="both", expand=True)

        # Кнопки в контекстном меню
        edit_btn = ctk.CTkButton(
            menu_frame,
            text="✏️ Редактировать заказ",
            command=self.edit_order_from_history,
            fg_color="transparent",
            text_color=self.colors["text_primary"],
            hover_color=self.colors["bg_hover"],
            anchor="w",
            height=28,
            corner_radius=0,
            font=ctk.CTkFont(size=12),
        )
        edit_btn.pack(fill="x", padx=4, pady=2)

        print_btn = ctk.CTkButton(
            menu_frame,
            text="🖨️ Печать акта",
            command=self.print_act_from_history,
            fg_color="transparent",
            text_color=self.colors["text_primary"],
            hover_color=self.colors["bg_hover"],
            anchor="w",
            height=28,
            corner_radius=0,
            font=ctk.CTkFont(size=12),
        )
        print_btn.pack(fill="x", padx=4, pady=2)

        # Кнопка закрытия — фиксированная внизу, всегда видна
        close_bar = ctk.CTkFrame(main_container, fg_color="transparent", height=45)
        close_bar.pack(side="bottom", fill="x", pady=(10, 5))
        close_bar.pack_propagate(False)
        ModernButton(
            close_bar,
            self.colors,
            variant="secondary",
            text="✖ Закрыть",
            command=self._close_with_geometry,
            height=35,
            width=120,
        ).pack(side="right")

    def load_data(self):
        """Загрузка данных"""
        logger.info(
            f"Загрузка истории для клиента: {self.client_name}, тел: {self.client_phone}"
        )
        self.all_history = self.client_db.get_client_history(
            self.client_name, self.client_phone
        )
        logger.info(f"Найдено записей: {len(self.all_history)}")

        # Обновляем статистику
        self.update_statistics()

        # Обновляем фильтр годов
        self.update_year_filter()

        # Загружаем таблицу
        self.filter_history()

    def update_statistics(self):
        """Обновление статистики"""
        total = len(self.all_history)
        completed = sum(
            1 for r in self.all_history if r.get("status") == "Выдан клиенту"
        )
        total_sum = 0
        favorite_device = {}

        for record in self.all_history:
            # Сумма только завершенных
            if record.get("status") == "Выдан клиенту":
                price_str = record.get("total_price", "0")
                try:
                    price_val = (
                        float(price_str.replace(",", ".").replace(" ", ""))
                        if price_str
                        else 0
                    )
                    total_sum += price_val
                except (ValueError, TypeError):
                    pass

            # Любимое устройство
            device = f"{record.get('brand', '')} {record.get('model', '')}".strip()
            if device:
                favorite_device[device] = favorite_device.get(device, 0) + 1

        favorite = (
            max(favorite_device.items(), key=lambda x: x[1])[0]
            if favorite_device
            else "—"
        )

        self.stats_labels["Всего ремонтов"].configure(text=str(total))
        self.stats_labels["Завершено"].configure(text=str(completed))
        self.stats_labels["Общая сумма"].configure(text=format_price(str(total_sum)))
        self.stats_labels["Любимое устройство"].configure(
            text=favorite[:25] + ("..." if len(favorite) > 25 else "")
        )

    def update_year_filter(self):
        """Обновление фильтра по годам"""
        years = []
        for r in self.all_history:
            receipt_date = r.get("receipt_date", "")
            if receipt_date:
                try:
                    year = receipt_date[:4]
                    if year and year.isdigit():
                        years.append(year)
                except (ValueError, TypeError, IndexError):
                    pass

        years = sorted(set(years), reverse=True)
        self.year_filter.configure(values=["Все", *years])

    def filter_history(self):
        """Фильтрация истории"""
        search_text = self.search_entry.get().strip().lower()
        status = self.status_filter.get()
        year = self.year_filter.get()

        filtered = []
        for record in self.all_history:
            # Фильтр по статусу
            if status != "Все" and record.get("status") != status:
                continue

            # Фильтр по году
            if year != "Все":
                receipt_date = record.get("receipt_date", "")
                record_year = ""
                if receipt_date:
                    with contextlib.suppress(ValueError, TypeError, IndexError):
                        record_year = receipt_date[:4]
                if record_year != year:
                    continue

            # Поиск
            if search_text:
                search_fields = [
                    record.get("order_number", ""),
                    record.get("brand", ""),
                    record.get("model", ""),
                    record.get("client_name", ""),
                    record.get("defect", ""),
                ]
                if not any(search_text in str(f).lower() for f in search_fields):
                    continue

            filtered.append(record)

        self.load_history(filtered)
        self.count_label.configure(
            text=f"Показано: {len(filtered)} из {len(self.all_history)}"
        )

    def reset_filters(self):
        """Сброс фильтров"""
        self.search_entry.delete(0, "end")
        self.status_filter.set("Все")
        self.year_filter.set("Все")
        self.filter_history()

    def load_history(self, history: list[dict[str, Any]]):
        """Загрузка истории в таблицу"""
        # Очищаем таблицу
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not history:
            self.tree.insert(
                "", "end", values=("Нет данных", "", "", "", "", "", "", "")
            )
            return

        for record in history:
            # Форматируем дату
            receipt_date = record.get("receipt_date", "")
            if receipt_date:
                try:
                    if " " in receipt_date:
                        dt = datetime.strptime(receipt_date[:19], "%Y-%m-%d %H:%M:%S")
                    else:
                        dt = datetime.strptime(receipt_date[:10], "%Y-%m-%d")
                    receipt_date = dt.strftime("%d.%m.%Y %H:%M")
                except (ValueError, TypeError):
                    receipt_date = receipt_date[:10] if receipt_date else "—"
            else:
                receipt_date = "—"

            order_number = format_order_number_for_display(
                record.get("order_number", "")
            )
            device_name = f"{record.get('brand', '')} {record.get('model', '')}".strip()
            if not device_name:
                device_name = record.get("device_type", "—")

            defect = record.get("defect", "—")
            if len(defect) > 30:
                defect = defect[:27] + "..."

            # Форматируем работы
            work_items_json = record.get("work_items", "")
            work_summary = "—"
            if work_items_json:
                try:
                    work_data = json.loads(work_items_json)
                    work_descriptions = []
                    for item in work_data:
                        if item.get("quantity", 1) > 1:
                            work_descriptions.append(
                                f"{item.get('description', '')[:20]} x{item.get('quantity', 1)}"
                            )
                        else:
                            work_descriptions.append(item.get("description", "")[:20])
                    work_summary = "; ".join(work_descriptions[:2])
                    if len(work_descriptions) > 2:
                        work_summary += "..."
                except (json.JSONDecodeError, KeyError, TypeError):
                    work_summary = "—"

            status_val = record.get("status", "—")
            price = (
                format_price(record.get("total_price", ""))
                if record.get("total_price")
                else "0 ₽"
            )

            photos = record.get("photos", "")
            photo_count = len(photos.split(",")) if photos else 0
            photo_indicator = f"📸 {photo_count}" if photo_count > 0 else "—"

            # Определяем цвет строки по статусу
            tags = ()
            if status_val == "Выдан клиенту":
                tags = ("completed",)
            elif status_val == "Отказ от ремонта":
                tags = ("declined",)

            values = (
                receipt_date,
                order_number,
                device_name,
                defect,
                work_summary,
                status_val,
                price,
                photo_indicator,
            )
            self.tree.insert("", "end", values=values, tags=tags)

        # Настройка цветов для тегов
        self.tree.tag_configure(
            "completed", background=self.colors.get("success_light", "#e6f4ea")
        )
        self.tree.tag_configure(
            "declined", background=self.colors.get("error_light", "#fce8e8")
        )

    def _safe_price_sort_key(self, value_str):
        """Безопасный парсинг цены для сортировки."""
        try:
            cleaned = (
                value_str.replace("₽", "")
                .replace("\u00a0", "")
                .replace(" ", "")
                .replace(",", ".")
            )
            return float(cleaned) if cleaned else 0.0
        except (ValueError, TypeError):
            return 0.0

    def sort_by_column(self, col):
        """Сортировка по колонке"""
        items = [
            (self.tree.set(item, col), item) for item in self.tree.get_children("")
        ]

        # Пропускаем если нет данных
        if not items or items[0][0] == "Нет данных":
            return

        # Определяем тип сортировки
        if col == "Цена":
            items.sort(key=lambda x: self._safe_price_sort_key(x[0]))
        elif col == "Заказ №":
            # Treeview мог привести числоподобное значение к int
            def _order_key(val):
                try:
                    return int(val)
                except (ValueError, TypeError):
                    return 0

            items.sort(key=lambda x: _order_key(x[0]))
        else:
            items.sort(key=lambda x: str(x[0]).lower())

        for index, (_, item) in enumerate(items):
            self.tree.move(item, "", index)

    def edit_order_from_history(self, event=None):
        """Открытие окна редактирования заказа из истории"""
        selected = self.tree.selection()
        if not selected:
            return

        item = self.tree.item(selected[0])
        values = item["values"]

        # Проверяем, что это не строка "Нет данных"
        if values[0] == "Нет данных":
            return

        # Ищем полную запись.
        # ВАЖНО: ttk.Treeview конвертирует числоподобные строки в int, поэтому
        # order_number из values может оказаться int (42 вместо '42'). Приводим к str.
        order_number = str(values[1]).strip()
        record = None
        for r in self.all_history:
            if (
                str(format_order_number_for_display(r.get("order_number", "")))
                == order_number
            ):
                record = r
                break

        if not record:
            messagebox.showerror("Ошибка", "Не удалось найти заказ")
            return

        # Получаем полные данные заказа из БД
        db_order_number = format_order_number_for_db(order_number)
        device = self.db.get_device_by_order_number(db_order_number)

        if device:
            # Открываем окно редактирования
            from gui.dialogs.device_form import DeviceFormDialog

            _parent_settings = getattr(self.parent_app, "settings", None)
            dialog = DeviceFormDialog(
                self.parent_app,
                self.db,
                self.client_db,
                self.parent_app.photo_manager
                if hasattr(self.parent_app, "photo_manager")
                else None,
                self.colors,
                is_new=False,
                device_data=device,
                settings=_parent_settings,
            )
            self.parent_app.wait_window(dialog)

            if dialog.result:
                # Обновляем данные в окне истории
                self.load_data()
                # Обновляем основную таблицу если есть метод
                if hasattr(self.parent_app, "load_devices"):
                    self.parent_app.load_devices()
                if hasattr(self.parent_app, "update_finance_display"):
                    self.parent_app.update_finance_display()
        else:
            messagebox.showerror("Ошибка", "Не удалось найти заказ в базе данных")

    def get_work_summary_full(self, work_items_json: str) -> str:
        """Получение полного описания работ"""
        if not work_items_json:
            return "—"
        try:
            work_data = json.loads(work_items_json)
            work_descriptions = []
            for item in work_data:
                qty = item.get("quantity", 1)
                price = item.get("price", "0")
                desc = item.get("description", "")
                if qty > 1:
                    work_descriptions.append(f"{desc} x{qty} ({price}₽)")
                else:
                    work_descriptions.append(f"{desc} ({price}₽)")
            return "\n".join(work_descriptions) if work_descriptions else "—"
        except (json.JSONDecodeError, KeyError, TypeError):
            return "—"

    def show_context_menu_history(self, event):
        """Показ контекстного меню для истории"""
        item = self.tree.identify_row(event.y)
        if item:
            # Проверяем, что это не пустая строка
            values = self.tree.item(item)["values"]
            if values and values[0] != "Нет данных":
                self.tree.selection_set(item)
                self.history_context_menu.geometry(f"+{event.x_root}+{event.y_root}")
                self.history_context_menu.deiconify()
                self.history_context_menu.lift()

    def print_act_from_history(self):
        """Печать акта из истории"""
        selected = self.tree.selection()
        if not selected:
            return

        item = self.tree.item(selected[0])
        values = item["values"]

        if values[0] == "Нет данных":
            return

        # Приводим к строке: Treeview мог сделать числоподобное значение int.
        order_number = str(values[1]).strip()

        # Ищем устройство в БД
        db_order_number = format_order_number_for_db(order_number)
        device = self.db.get_device_by_order_number(db_order_number)

        if device:
            from gui.dialogs.act_preview import ActPreviewWindow

            report_gen = self.report_gen
            filename = report_gen.generate_receipt_act(device)
            if filename and os.path.exists(filename):
                with open(filename, encoding="utf-8") as f:
                    content = f.read()
                ActPreviewWindow(
                    self,
                    f"Акт приема {order_number}",
                    content,
                    self.colors,
                    "receipt",
                    device,
                    settings=self.settings,
                )
        else:
            messagebox.showerror("Ошибка", "Не удалось найти акт для этого заказа")

    def export_history(self):
        """Экспорт истории в CSV"""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=f"history_{self.client_name}.csv",
        )

        if file_path:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "Дата",
                        "Заказ №",
                        "Устройство",
                        "Неисправность",
                        "Работы",
                        "Статус",
                        "Цена",
                    ]
                )

                for record in self.all_history:
                    receipt_date = format_date(record.get("receipt_date", ""))
                    order_number = format_order_number_for_display(
                        record.get("order_number", "")
                    )
                    device_name = (
                        f"{record.get('brand', '')} {record.get('model', '')}".strip()
                    )
                    defect = record.get("defect", "")
                    work_summary = self.get_work_summary_full(
                        record.get("work_items", "")
                    )
                    status = record.get("status", "")
                    price = format_price(record.get("total_price", ""))

                    writer.writerow(
                        [
                            receipt_date,
                            order_number,
                            device_name,
                            defect,
                            work_summary,
                            status,
                            price,
                        ]
                    )

            messagebox.showinfo("Успех", f"История экспортирована:\n{file_path}")
