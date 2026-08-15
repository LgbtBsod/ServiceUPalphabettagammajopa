#!/usr/bin/env python3

"""Окно управления словарями"""

from tkinter import messagebox, ttk

import customtkinter as ctk

from gui.widgets.premium import PremiumCard
from utils.constants import DICTIONARY_TYPES


class DictionariesManagerWindow(ctk.CTkToplevel):
    """Окно управления словарями"""

    def __init__(self, parent, db, colors: dict[str, str], settings=None):
        super().__init__(parent)
        self.parent = parent
        self.db = db
        self.colors = colors
        self.settings = settings  # опционально, для сохранения геометрии окна
        self.current_dict_type = None
        self.current_item_id = None
        self.trees: dict[str, ttk.Treeview] = {}
        self.entries: dict[str, dict] = {}

        self.title("Управление словарями")
        from utils.window_state import restore_window_geometry

        restore_window_geometry(
            self.settings,
            "dictionaries",
            self,
            default_w=1000,
            default_h=650,
            min_w=900,
            min_h=550,
        )

        self.transient(parent)
        self.grab_set()

        # Сохраняем геометрию при закрытии
        self.protocol("WM_DELETE_WINDOW", self._close_with_geometry)

        self.create_widgets()

    def _close_with_geometry(self):
        """Сохраняет геометрию окна в config и закрывает его."""
        try:
            from utils.window_state import save_window_geometry

            save_window_geometry(self.settings, "dictionaries", self)
        except Exception:
            pass
        self.destroy()

    def create_widgets(self):
        """Создание виджетов"""
        main_container = ctk.CTkFrame(self, fg_color=self.colors["bg_primary"])
        main_container.pack(fill="both", expand=True, padx=10, pady=10)

        # Заголовок
        title_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 10))

        icon_label = ctk.CTkLabel(
            title_frame,
            text="📚",
            font=ctk.CTkFont(size=28),
            text_color=self.colors["accent"],
        )
        icon_label.pack(side="left", padx=(0, 10))

        title_label = ctk.CTkLabel(
            title_frame,
            text="Управление словарями",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors["accent"],
        )
        title_label.pack(side="left")

        # Создаем вкладки для каждого типа словаря
        self.tabview = ctk.CTkTabview(
            main_container, fg_color=self.colors["bg_primary"]
        )
        self.tabview.pack(fill="both", expand=True, pady=(0, 10))

        # Добавляем вкладки для каждого словаря
        for dict_type, config in DICTIONARY_TYPES.items():
            tab = self.tabview.add(f"{config['icon']} {config['name']}")
            self.create_dict_tab(tab, dict_type, config)

        # Кнопка закрытия
        close_btn = ctk.CTkButton(
            main_container,
            text="✖ Закрыть",
            command=self.destroy,
            height=36,
            width=120,
            corner_radius=8,
            fg_color=self.colors["bg_tertiary"],
            text_color=self.colors["text_primary"],
            hover_color=self.colors["hover"],
            border_width=1,
            border_color=self.colors["border"],
            font=ctk.CTkFont(size=13),
        )
        close_btn.pack(side="right", pady=(0, 5))

    def create_dict_tab(self, parent, dict_type: str, config: dict):
        """Создание вкладки для конкретного словаря"""
        # Контейнер с двумя колонками
        columns = ctk.CTkFrame(parent, fg_color="transparent")
        columns.pack(fill="both", expand=True, padx=10, pady=10)

        # Левая колонка - список значений
        left = ctk.CTkFrame(columns, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(0, 5))

        left_card = PremiumCard(left, self.colors)
        left_card.pack(fill="both", expand=True)

        ctk.CTkLabel(
            left_card,
            text=f"{config['icon']} Список значений",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(anchor="w", padx=12, pady=(12, 8))

        # Таблица для списка
        tree_frame = ctk.CTkFrame(left_card, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # Создаем Treeview с авто-скрываемой прокруткой
        tree = ttk.Treeview(
            tree_frame, columns=("id", "value", "info"), show="headings", height=15
        )

        tree.heading("id", text="ID")
        tree.heading("value", text="Значение")
        tree.heading("info", text="Доп. информация")

        tree.column("id", width=50, minwidth=40)
        tree.column("value", width=250, minwidth=150)
        tree.column("info", width=200, minwidth=100)

        # Авто-скрываемые скроллбары (скрываются, когда контент помещается)
        from gui.widgets.auto_scroll import attach_auto_scrollbars

        attach_auto_scrollbars(tree_frame, tree)

        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # Привязываем событие выбора
        tree.bind(
            "<<TreeviewSelect>>", lambda e, dt=dict_type: self.on_item_select(dt, tree)
        )

        self.trees[dict_type] = tree

        # Правая колонка - редактирование
        right = ctk.CTkFrame(columns, fg_color="transparent")
        right.pack(side="right", fill="both", expand=True, padx=(5, 0))

        right_card = PremiumCard(right, self.colors)
        right_card.pack(fill="both", expand=True)

        ctk.CTkLabel(
            right_card,
            text="✏️ Редактирование",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(anchor="w", padx=12, pady=(12, 8))

        # Форма редактирования
        form = ctk.CTkFrame(right_card, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # Поле для значения
        ctk.CTkLabel(
            form, text="Значение*:", font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", pady=(0, 3))
        value_entry = ctk.CTkEntry(
            form,
            placeholder_text="Введите значение",
            fg_color=self.colors["bg_tertiary"],
            border_color=self.colors["border"],
            height=35,
        )
        value_entry.pack(fill="x", pady=(0, 10))

        # Поле для дополнительной информации
        ctk.CTkLabel(
            form, text="Доп. информация:", font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", pady=(0, 3))
        info_entry = ctk.CTkEntry(
            form,
            placeholder_text="Например: цена для работы",
            fg_color=self.colors["bg_tertiary"],
            border_color=self.colors["border"],
            height=35,
        )
        info_entry.pack(fill="x", pady=(0, 15))

        # Кнопки действий — grid с автоматическим переносом
        btn_frame = ctk.CTkFrame(form, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(5, 0))

        # Используем grid для возможности переноса на новую строку
        _dict_btns = [
            (
                "💾 Сохранить",
                lambda dt=dict_type, ve=value_entry, ie=info_entry: self.save_item(
                    dt, ve, ie
                ),
                self.colors["accent"],
                "white",
                self.colors.get("accent_hover"),
                0,
                0,
            ),
            (
                "➕ Добавить",
                lambda dt=dict_type, ve=value_entry, ie=info_entry: self.add_new_item(
                    dt, ve, ie
                ),
                self.colors["bg_tertiary"],
                self.colors["text_primary"],
                self.colors.get("hover"),
                0,
                1,
            ),
            (
                "🗑️ Удалить",
                lambda dt=dict_type: self.delete_item(dt),
                "#d13438",
                "white",
                "#b32d30",
                1,
                0,
            ),
            (
                "✖ Очистить",
                lambda ve=value_entry, ie=info_entry: self.clear_form(ve, ie),
                self.colors["bg_tertiary"],
                self.colors["text_primary"],
                self.colors.get("hover"),
                1,
                1,
            ),
        ]
        for text, cmd, fg, tc, hover, brow, bcol in _dict_btns:
            ctk.CTkButton(
                btn_frame,
                text=text,
                command=cmd,
                height=33,
                width=130,
                corner_radius=6,
                fg_color=fg,
                text_color=tc,
                hover_color=hover,
                border_width=1 if fg == self.colors["bg_tertiary"] else 0,
                border_color=self.colors["border"],
                font=ctk.CTkFont(size=12),
            ).grid(row=brow, column=bcol, padx=3, pady=3, sticky="ew")
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        # Подсказка
        note_label = ctk.CTkLabel(
            form,
            text="* - обязательные поля",
            font=ctk.CTkFont(size=11),
            text_color=self.colors["text_secondary"],
        )
        note_label.pack(anchor="w", pady=(15, 0))

        # Сохраняем ссылки на поля ввода для этого словаря
        self.entries[dict_type] = {
            "value": value_entry,
            "info": info_entry,
            "tree": tree,
        }

        # Загружаем данные
        self.load_dict_data(dict_type)

    def load_dict_data(self, dict_type: str):
        """Загрузка данных словаря в таблицу"""
        tree = self.trees.get(dict_type)
        if not tree:
            return

        # Очищаем таблицу
        for item in tree.get_children():
            tree.delete(item)

        # Получаем данные из БД
        items = self.db.get_all_dict_items(dict_type)

        # Заполняем таблицу
        for item in items:
            tree.insert(
                "",
                "end",
                iid=str(item["id"]),
                values=(item["id"], item["value"], item.get("additional_info", "")),
            )

    def on_item_select(self, dict_type: str, tree: ttk.Treeview):
        """Обработка выбора элемента в таблице"""
        selected = tree.selection()
        if not selected:
            return

        entry = self.entries.get(dict_type)
        if not entry:
            return

        try:
            item_id = int(selected[0])
        except ValueError, TypeError:
            return
        item = tree.item(selected[0])
        values = item["values"]

        self.current_dict_type = dict_type
        self.current_item_id = item_id

        # Заполняем поля формы
        entry["value"].delete(0, "end")
        entry["value"].insert(0, values[1])

        entry["info"].delete(0, "end")
        if len(values) > 2 and values[2]:
            entry["info"].insert(0, values[2])

    def save_item(
        self, dict_type: str, value_entry: ctk.CTkEntry, info_entry: ctk.CTkEntry
    ):
        """Сохранение изменений элемента"""
        value = value_entry.get().strip()
        info = info_entry.get().strip()

        if not value:
            messagebox.showerror("Ошибка", "Введите значение!")
            return

        if self.current_item_id and self.current_dict_type == dict_type:
            if self.db.update_dict_value(self.current_item_id, value, info):
                messagebox.showinfo("Успех", "✅ Значение обновлено")
                self.load_dict_data(dict_type)
                self.clear_form(value_entry, info_entry)
                self.current_item_id = None
            else:
                messagebox.showerror("Ошибка", "❌ Не удалось обновить значение")
        else:
            messagebox.showwarning(
                "Предупреждение", "Сначала выберите элемент для редактирования"
            )

    def add_new_item(
        self, dict_type: str, value_entry: ctk.CTkEntry, info_entry: ctk.CTkEntry
    ):
        """Добавление нового элемента"""
        value = value_entry.get().strip()
        info = info_entry.get().strip()

        if not value:
            messagebox.showerror("Ошибка", "Введите значение!")
            return

        if self.db.add_dict_value(dict_type, value, info):
            messagebox.showinfo("Успех", "✅ Значение добавлено")
            self.load_dict_data(dict_type)
            self.clear_form(value_entry, info_entry)
        else:
            messagebox.showerror("Ошибка", "❌ Такое значение уже существует")

    def delete_item(self, dict_type: str):
        """Удаление элемента"""
        if not self.current_item_id or self.current_dict_type != dict_type:
            messagebox.showwarning("Предупреждение", "Выберите элемент для удаления")
            return

        if messagebox.askyesno(
            "Подтверждение", "Вы уверены, что хотите удалить этот элемент?"
        ):
            if self.db.delete_dict_value(self.current_item_id):
                messagebox.showinfo("Успех", "✅ Элемент удален")
                self.load_dict_data(dict_type)
                # Очищаем форму
                entry = self.entries.get(dict_type)
                if entry:
                    self.clear_form(entry["value"], entry["info"])
                self.current_item_id = None
            else:
                messagebox.showerror("Ошибка", "❌ Не удалось удалить элемент")

    def clear_form(self, value_entry: ctk.CTkEntry, info_entry: ctk.CTkEntry):
        """Очистка формы"""
        value_entry.delete(0, "end")
        info_entry.delete(0, "end")
