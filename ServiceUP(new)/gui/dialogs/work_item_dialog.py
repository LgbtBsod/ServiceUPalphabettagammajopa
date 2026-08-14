#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Диалог для редактирования работы"""

import customtkinter as ctk
from tkinter import messagebox

from gui.widgets.premium import PremiumLabel, PremiumEntry
from utils.validators import validate_price


class WorkItemDialog(ctk.CTkToplevel):
    """Диалог для создания/редактирования работы"""
    
    def __init__(self, parent, colors, description="", price="", quantity=1, settings=None):
        super().__init__(parent)
        self.colors = colors
        self.settings = settings  # опционально, для сохранения геометрии
        self.result = None

        self.title("Редактирование работы" if description else "Новая работа")
        from utils.window_state import restore_window_geometry
        restore_window_geometry(self.settings, "work_item", self,
                                default_w=450, default_h=500, min_w=400, min_h=450)

        self.transient(parent)
        self.grab_set()

        # Сохраняем геометрию при закрытии
        self.protocol("WM_DELETE_WINDOW", self._close_with_geometry)

        self.create_widgets(description, price, quantity)

    def _close_with_geometry(self):
        """Сохраняет геометрию окна в config и закрывает его."""
        try:
            from utils.window_state import save_window_geometry
            save_window_geometry(self.settings, "work_item", self)
        except Exception:
            pass
        self.destroy()
    
    def create_widgets(self, description, price, quantity):
        """Создание виджетов диалога"""
        main_container = ctk.CTkFrame(self, fg_color=self.colors['bg_primary'])
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        title_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 20))
        
        icon_label = ctk.CTkLabel(
            title_frame,
            text="🔨",
            font=ctk.CTkFont(size=24),
            text_color=self.colors['accent']
        )
        icon_label.pack(side="left", padx=(0, 10))
        
        title_label = ctk.CTkLabel(
            title_frame,
            text="Редактирование работы" if description else "Новая работа",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.colors['accent']
        )
        title_label.pack(side="left")
        
        form_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        form_frame.pack(fill="both", expand=True)
        
        desc_label = PremiumLabel(
            form_frame,
            text="Описание работы:*",
            colors=self.colors,
            font=ctk.CTkFont(size=13, weight="bold")
        )
        desc_label.pack(anchor="w", pady=(5, 2))
        
        self.desc_entry = PremiumEntry(
            form_frame,
            colors=self.colors,
            placeholder_text="Введите описание работы"
        )
        self.desc_entry.insert(0, description)
        self.desc_entry.pack(fill="x", pady=(0, 10))
        
        price_label = PremiumLabel(
            form_frame,
            text="Цена (₽):*",
            colors=self.colors,
            font=ctk.CTkFont(size=13, weight="bold")
        )
        price_label.pack(anchor="w", pady=(5, 2))
        
        self.price_entry = PremiumEntry(
            form_frame,
            colors=self.colors,
            placeholder_text="Например: 5000"
        )
        self.price_entry.insert(0, price)
        self.price_entry.pack(fill="x", pady=(0, 10))
        
        quantity_label = PremiumLabel(
            form_frame,
            text="Количество:",
            colors=self.colors,
            font=ctk.CTkFont(size=13, weight="bold")
        )
        quantity_label.pack(anchor="w", pady=(5, 2))
        
        quantity_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        quantity_frame.pack(fill="x", pady=(0, 10))
        
        self.quantity_var = ctk.IntVar(value=quantity)
        
        quantity_spinbox = ctk.CTkEntry(
            quantity_frame,
            textvariable=self.quantity_var,
            width=80,
            fg_color=self.colors['bg_tertiary'],
            border_color=self.colors['border'],
            border_width=1,
            corner_radius=6,
            height=32
        )
        quantity_spinbox.pack(side="left")
        
        quantity_note = PremiumLabel(
            quantity_frame,
            text="шт.",
            colors=self.colors,
            font=ctk.CTkFont(size=12),
            text_color=self.colors['text_secondary']
        )
        quantity_note.pack(side="left", padx=(5, 0))
        
        note_label = PremiumLabel(
            form_frame,
            text="* - обязательные поля",
            colors=self.colors,
            font=ctk.CTkFont(size=11),
            text_color=self.colors['text_secondary']
        )
        note_label.pack(anchor="w", pady=(10, 5))
        
        buttons_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        buttons_frame.pack(fill="x", pady=(20, 0))
        
        save_btn = ctk.CTkButton(
            buttons_frame,
            text="💾 Сохранить",
            command=self.save,
            height=36,
            width=120,
            corner_radius=8,
            fg_color=self.colors['accent'],
            text_color="white",
            hover_color=self.colors['accent_hover'],
            font=ctk.CTkFont(size=13)
        )
        save_btn.pack(side="right", padx=5)
        
        cancel_btn = ctk.CTkButton(
            buttons_frame,
            text="✖ Отмена",
            command=self._close_with_geometry,
            height=36,
            width=120,
            corner_radius=8,
            fg_color=self.colors['bg_tertiary'],
            text_color=self.colors['text_primary'],
            hover_color=self.colors['hover'],
            border_width=1,
            border_color=self.colors['border'],
            font=ctk.CTkFont(size=13)
        )
        cancel_btn.pack(side="right", padx=5)
    
    def save(self):
        """Сохранение работы"""
        description = self.desc_entry.get().strip()
        price = self.price_entry.get().strip()

        if not description:
            messagebox.showerror("Ошибка", "Введите описание работы!")
            return

        if not price:
            messagebox.showerror("Ошибка", "Введите цену!")
            return

        if not validate_price(price):
            messagebox.showerror("Ошибка", "Неверный формат цены!")
            return

        # Безопасное чтение quantity (поле может быть пустым)
        try:
            quantity = self.quantity_var.get()
        except (ctk.TclError, ValueError, TypeError):
            quantity = 1

        if quantity < 1:
            messagebox.showerror("Ошибка", "Количество должно быть не менее 1!")
            return

        self.result = {
            'description': description,
            'price': price,
            'quantity': quantity
        }
        self._close_with_geometry()
