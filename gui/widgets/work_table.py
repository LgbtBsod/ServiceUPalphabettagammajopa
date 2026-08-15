#!/usr/bin/env python3

"""Мини-таблица для управления выполненными работами"""

import logging
from tkinter import messagebox, ttk

import customtkinter as ctk

from database import WorkItem
from gui.widgets.premium import PremiumLabel

logger = logging.getLogger(__name__)


class WorkItemsTable:
    """Мини-таблица для управления несколькими выполненными работами"""

    def __init__(
        self,
        parent,
        colors,
        work_manager,
        on_total_changed=None,
        db=None,
        settings=None,
    ):
        self.parent = parent
        self.colors = colors
        self.work_manager = work_manager
        self.on_total_changed = on_total_changed
        self.db = db  # для доступа к словарю шаблонов работ
        self.settings = settings  # для сохранения геометрии окон
        self.tree = None
        self.create_widgets()

    def create_widgets(self):
        """Создание виджетов"""
        table_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        table_frame.pack(fill="both", expand=True, padx=10, pady=5)

        header_frame = ctk.CTkFrame(table_frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 5))

        title_label = PremiumLabel(
            header_frame,
            text="Выполненные работы:",
            colors=self.colors,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        title_label.pack(side="left")

        total_label = PremiumLabel(
            header_frame,
            text="",
            colors=self.colors,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        total_label.pack(side="right")
        self.total_label = total_label

        tree_container = ctk.CTkFrame(
            table_frame, fg_color=self.colors["bg_tertiary"], corner_radius=6
        )
        tree_container.pack(fill="both", expand=True)

        columns = ("№", "Описание работы", "Цена", "Кол-во", "Сумма")

        self.tree = ttk.Treeview(
            tree_container, columns=columns, show="headings", height=5
        )

        column_widths = [40, 300, 100, 70, 100]
        for col, width in zip(columns, column_widths, strict=False):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=width, minwidth=40)

        # Авто-скрываемый скроллбар (скрывается, когда работ немного)
        from gui.widgets.auto_scroll import attach_auto_scrollbars

        attach_auto_scrollbars(tree_container, self.tree)

        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        self.tree.bind("<Double-Button-1>", self.on_item_double_click)
        self.tree.bind("<Delete>", self.delete_selected)

        buttons_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        buttons_frame.pack(fill="x", padx=10, pady=5)

        # Кнопка выбора работы из словаря (открывает окно с поиском + списком)
        add_template_btn = ctk.CTkButton(
            buttons_frame,
            text="➕ Из шаблона",
            command=self.add_from_template,
            height=30,
            width=130,
            corner_radius=6,
            fg_color=self.colors["bg_tertiary"],
            text_color=self.colors["text_primary"],
            hover_color=self.colors["hover"],
            border_width=1,
            border_color=self.colors["border"],
            font=ctk.CTkFont(size=12),
        )
        add_template_btn.pack(side="left", padx=2)

        add_custom_btn = ctk.CTkButton(
            buttons_frame,
            text="➕ Своя работа",
            command=self.add_work_item,
            height=30,
            width=120,
            corner_radius=6,
            fg_color=self.colors["bg_tertiary"],
            text_color=self.colors["text_primary"],
            hover_color=self.colors["hover"],
            border_width=1,
            border_color=self.colors["border"],
            font=ctk.CTkFont(size=12),
        )
        add_custom_btn.pack(side="left", padx=2)

        edit_btn = ctk.CTkButton(
            buttons_frame,
            text="✏️ Редактировать",
            command=self.edit_selected,
            height=30,
            width=120,
            corner_radius=6,
            fg_color=self.colors["bg_tertiary"],
            text_color=self.colors["text_primary"],
            hover_color=self.colors["hover"],
            border_width=1,
            border_color=self.colors["border"],
            font=ctk.CTkFont(size=12),
        )
        edit_btn.pack(side="left", padx=2)

        delete_btn = ctk.CTkButton(
            buttons_frame,
            text="🗑️ Удалить",
            command=self.delete_selected,
            height=30,
            width=100,
            corner_radius=6,
            fg_color="#d13438",
            text_color="white",
            hover_color="#b32d30",
            font=ctk.CTkFont(size=12),
        )
        delete_btn.pack(side="left", padx=2)

        self.refresh_table()

    def get_work_templates(self):
        """Получение шаблонов работ из словаря БД (единый источник).

        Возвращает список словарей {'description', 'price'}.
        Раньше был захардкоженный список — теперь берём из БД, чтобы
        шаблоны работ и словарь всегда были синхронизированы.
        """
        if not self.db:
            return []
        try:
            items = self.db.get_all_dict_items("work")
            return [
                {
                    "description": it.get("value", ""),
                    "price": (it.get("additional_info") or "").strip(),
                }
                for it in items
            ]
        except Exception as e:
            logger.error(f"Ошибка загрузки шаблонов работ: {e}", exc_info=True)
            return []

    def add_from_template(self):
        """Добавление работы из шаблона через окно выбора.

        Открывает WorkTemplatePicker с поиском, списком словаря и
        возможностью добавить новый шаблон. После выбора — добавляет работу.
        """
        if not self.db:
            from tkinter import messagebox

            messagebox.showwarning("Недоступно", "База данных недоступна для шаблонов")
            return
        from gui.dialogs.work_template_picker import WorkTemplatePicker

        picker = WorkTemplatePicker(self.parent, self.db, self.colors)
        self.parent.wait_window(picker)

        if picker.result:
            tpl = picker.result
            work_item = WorkItem(
                description=tpl.get("description", ""),
                price=tpl.get("price", ""),
                quantity=1,
            )
            self.work_manager.add_item(work_item)
            self.refresh_table()

    def refresh_table(self):
        """Обновление таблицы"""
        for item in self.tree.get_children():
            self.tree.delete(item)

        for i, work_item in enumerate(self.work_manager.items):
            total = work_item.total_price()
            values = (
                i + 1,
                work_item.description,
                work_item.price,
                work_item.quantity,
                f"{total:,.0f} ₽",
            )
            self.tree.insert("", "end", values=values)

        total = self.work_manager.get_total_price()
        self.total_label.configure(text=f"Всего: {total:,.0f} ₽")

        if self.on_total_changed:
            self.on_total_changed(total)

    def add_work_item(self):
        """Добавление новой работы"""
        from gui.dialogs.work_item_dialog import WorkItemDialog

        dialog = WorkItemDialog(self.parent, self.colors, settings=self.settings)
        self.parent.wait_window(dialog)

        if dialog.result:
            work_item = WorkItem(
                description=dialog.result.get("description", ""),
                price=dialog.result.get("price", ""),
                quantity=dialog.result.get("quantity", 1),
            )
            self.work_manager.add_item(work_item)
            self.refresh_table()

    def edit_selected(self, event=None):
        """Редактирование выбранной работы"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning(
                "Предупреждение", "Выберите работу для редактирования"
            )
            return

        index = int(self.tree.item(selected[0])["values"][0]) - 1
        work_item = self.work_manager.items[index]

        from gui.dialogs.work_item_dialog import WorkItemDialog

        dialog = WorkItemDialog(
            self.parent,
            self.colors,
            description=work_item.description,
            price=work_item.price,
            quantity=work_item.quantity,
            settings=self.settings,
        )
        self.parent.wait_window(dialog)

        if dialog.result:
            work_item.description = dialog.result.get("description", "")
            work_item.price = dialog.result.get("price", "")
            work_item.quantity = dialog.result.get("quantity", 1)
            self.refresh_table()

    def delete_selected(self, event=None):
        """Удаление выбранной работы"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Предупреждение", "Выберите работу для удаления")
            return

        if messagebox.askyesno("Подтверждение", "Удалить выбранную работу?"):
            index = int(self.tree.item(selected[0])["values"][0]) - 1
            self.work_manager.remove_item(index)
            self.refresh_table()

    def on_item_double_click(self, event):
        """Обработка двойного клика"""
        self.edit_selected()
