#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Окно выбора шаблона выполненной работы.

Единый источник шаблонов работ — словарь 'work' в БД (additional_info = цена).
Окно позволяет:
- искать шаблон по названию;
- выбрать существующий из списка (двойной клик / кнопка «Выбрать»);
- добавить новый шаблон прямо здесь (название + цена) — он сохраняется в словарь.

Возвращает выбранный шаблон (description, price) через self.result.
"""

import customtkinter as ctk
from tkinter import ttk, messagebox
from typing import Optional, Dict, Any

from gui.widgets.modern import ModernCard, ModernButton, ModernLabel, ModernEntry


class WorkTemplatePicker(ctk.CTkToplevel):
    """Диалог выбора шаблона работы из словаря БД."""

    def __init__(self, parent, db, colors: dict):
        super().__init__(parent)
        self.parent = parent
        self.db = db
        self.colors = colors
        self.result: Optional[Dict[str, Any]] = None  # {'description', 'price'}
        self._all_items: list = []  # кеш элементов словаря

        self.title("Выбор шаблона работы")
        self.geometry("820x560")
        self.minsize(700, 480)

        self.transient(parent)
        self.grab_set()

        self.create_widgets()
        self.load_templates()

    def create_widgets(self):
        """Создание интерфейса: список слева, добавление справа."""
        main = ctk.CTkFrame(self, fg_color=self.colors['bg_primary'])
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # Заголовок (на всю ширину сверху)
        ctk.CTkLabel(main, text="🔨 Шаблоны выполненных работ",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=self.colors['accent']).pack(anchor="w", pady=(4, 8))

        # Двухпанельный контейнер: слева список, справа добавление
        content = ctk.CTkFrame(main, fg_color="transparent")
        content.pack(fill="both", expand=True)

        # ===== ЛЕВАЯ ПАНЕЛЬ: поиск + список =====
        left = ModernCard(content, self.colors)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))
        left_inner = ctk.CTkFrame(left, fg_color="transparent")
        left_inner.pack(fill="both", expand=True, padx=10, pady=10)

        # Поиск
        search_frame = ctk.CTkFrame(left_inner, fg_color="transparent")
        search_frame.pack(fill="x", pady=(0, 6))

        ModernLabel(search_frame, self.colors, text="🔍").pack(side="left", padx=(0, 6))
        self.search_entry = ModernEntry(search_frame, self.colors,
                                        placeholder_text="Поиск по названию работы...",
                                        height=32)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.search_entry.bind("<KeyRelease>", lambda e: self.apply_filter())

        ModernButton(search_frame, self.colors, variant="secondary",
                     text="🔄", command=self.load_templates,
                     width=38, height=32).pack(side="left")

        # Список шаблонов (Treeview)
        tree_container = ctk.CTkFrame(left_inner, fg_color="transparent")
        tree_container.pack(fill="both", expand=True)

        columns = ("name", "price")
        self.tree = ttk.Treeview(tree_container, columns=columns, show="headings", height=14)
        self.tree.heading("name", text="Наименование работы")
        self.tree.heading("price", text="Цена (₽)")
        self.tree.column("name", width=260, minwidth=160)
        self.tree.column("price", width=100, minwidth=70, anchor="e")

        from gui.widgets.auto_scroll import attach_auto_scrollbars
        attach_auto_scrollbars(tree_container, self.tree)
        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        self.tree.bind("<Double-Button-1>", lambda e: self.confirm_selection())

        style = ttk.Style()
        try:
            style.configure("Treeview", background=self.colors['bg_secondary'],
                            foreground=self.colors['text_primary'],
                            fieldbackground=self.colors['bg_secondary'],
                            rowheight=26, font=('Segoe UI', 11))
            style.configure("Treeview.Heading", background=self.colors['bg_tertiary'],
                            foreground=self.colors['text_primary'],
                            font=('Segoe UI', 11, 'bold'))
        except Exception:
            pass

        # Кнопки выбора (под списком слева)
        btn_frame = ctk.CTkFrame(left_inner, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(8, 0))
        ModernButton(btn_frame, self.colors, variant="primary", text="✅ Выбрать",
                     command=self.confirm_selection, height=32, width=110).pack(side="left")
        ModernButton(btn_frame, self.colors, variant="secondary", text="✖ Отмена",
                     command=self.destroy, height=32, width=90).pack(side="right")

        # ===== ПРАВАЯ ПАНЕЛЬ: добавление нового шаблона =====
        right = ModernCard(content, self.colors)
        right.pack(side="right", fill="y", padx=(6, 0))
        right_inner = ctk.CTkFrame(right, fg_color="transparent")
        right_inner.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(right_inner, text="➕ Новый шаблон",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=self.colors['accent']).pack(anchor="w", pady=(0, 10))

        ModernLabel(right_inner, self.colors, text="Название работы:").pack(anchor="w", pady=(4, 2))
        self.new_name_entry = ModernEntry(right_inner, self.colors)
        self.new_name_entry.pack(fill="x", pady=(0, 8))

        ModernLabel(right_inner, self.colors, text="Цена (₽):").pack(anchor="w", pady=(4, 2))
        self.new_price_entry = ModernEntry(right_inner, self.colors)
        self.new_price_entry.pack(fill="x", pady=(0, 12))

        ModernButton(right_inner, self.colors, variant="success",
                     text="💾 Добавить в словарь",
                     command=self.add_new_template, height=34).pack(fill="x")

    def load_templates(self):
        """Загружает шаблоны работ из словаря БД."""
        self._all_items = self.db.get_all_dict_items('work')
        self.apply_filter()

    def apply_filter(self):
        """Фильтрует список по поисковой строке."""
        needle = self.search_entry.get().strip().lower()
        for item in self.tree.get_children():
            self.tree.delete(item)

        for it in self._all_items:
            name = it.get('value', '')
            price = it.get('additional_info') or ''
            if needle and needle not in str(name).lower():
                continue
            # Цена хранится в additional_info как строка
            price_display = str(price).strip() if price else "—"
            self.tree.insert("", "end", values=(name, price_display))

    def confirm_selection(self):
        """Подтверждает выбор шаблона из списка."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Подсказка", "Выберите работу из списка")
            return
        values = self.tree.item(selected[0])['values']
        name = str(values[0])
        price = str(values[1]) if len(values) > 1 else ""
        if price in ("—", "None", ""):
            price = ""
        self.result = {'description': name, 'price': price}
        self.destroy()

    def add_new_template(self):
        """Добавляет новый шаблон в словарь БД и обновляет список."""
        name = self.new_name_entry.get().strip()
        price = self.new_price_entry.get().strip()
        if not name:
            messagebox.showerror("Ошибка", "Введите название работы")
            return
        # Очищаем цену от не-цифр (кроме запятой/точки)
        import re
        price_clean = re.sub(r'[^\d.,]', '', price).replace(',', '.')

        if self.db.add_dict_value('work', name, price_clean):
            self.new_name_entry.delete(0, 'end')
            self.new_price_entry.delete(0, 'end')
            self.load_templates()
            messagebox.showinfo("Успех", "Шаблон добавлен в словарь")
        else:
            messagebox.showerror("Ошибка", "Не удалось добавить (возможно, уже существует)")
