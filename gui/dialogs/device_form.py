#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Диалог создания/редактирования устройства"""

import os
import logging
import customtkinter as ctk
from tkinter import messagebox, filedialog
from datetime import datetime
from typing import Optional, Dict, Any, List

from config import PHOTOS_DIR
from database import Database, ClientDatabaseManager, WorkItemsManager, WorkItem
from managers import PhotoManager, ReportGenerator
from utils.formatters import (
    format_order_number_for_display, format_order_number_for_db,
    generate_order_number, format_price, normalize_phone
)
from utils.validators import validate_phone, validate_price
from utils.constants import STATUSES, PRIORITIES, CLIENT_STATUSES, WARRANTIES
from utils.window_effects import apply_dialog_translucency

logger = logging.getLogger(__name__)

from gui.widgets.premium import PremiumCard, PremiumLabel, PremiumEntry, PremiumCombobox
from gui.widgets.modern import ModernCard
from gui.widgets.thumbnail import ThumbnailWidget
from gui.widgets.work_table import WorkItemsTable
from gui.dialogs.client_history import ClientHistoryWindow
from gui.dialogs.act_preview import ActPreviewWindow
from gui.dialogs.photo_viewer import PhotoViewerWindow


class DeviceFormDialog(ctk.CTkToplevel):
    """Диалог создания/редактирования устройства"""
    
    def __init__(self, parent, db: Database, client_db: ClientDatabaseManager,
                 photo_manager: PhotoManager, colors: Dict[str, str],
                 is_new: bool = True, device_data: Optional[Dict[str, Any]] = None,
                 settings=None):
        super().__init__(parent)
        self.db = db
        self.client_db = client_db
        self.photo_manager = photo_manager
        self.colors = colors
        self.settings = settings  # для сохранения геометрии окна (опционально)
        self.is_new = is_new
        self.device_data = device_data
        self.result = None
        self.current_photos: List[str] = []
        self.thumbnail_widgets: List[ctk.CTkFrame] = []
        self.work_manager = WorkItemsManager()
        
        # Загружаем существующие фото и работы
        if not is_new and device_data:
            photos = device_data.get('photos', '')
            self.current_photos = [p for p in photos.split(',') if p] if photos else []
            work_items_json = device_data.get('work_items', '')
            if work_items_json:
                self.work_manager.from_json(work_items_json)
        
        title = "➕ Новый заказ" if is_new else f"✏️ Редактирование заказа #{format_order_number_for_display(device_data.get('order_number', '')) if device_data else ''}"
        self.title(title)
        # Восстанавливаем геометрию из config-файла (или дефолт с центрированием)
        from utils.window_state import restore_window_geometry
        restore_window_geometry(self.settings, "device_form", self,
                                default_w=1100, default_h=700, min_w=950, min_h=560)

        self.transient(parent)
        self.grab_set()

        # Сохраняем геометрию при закрытии окна пользователем
        self.protocol("WM_DELETE_WINDOW", self._close_with_geometry)

        # macOS-стиль: лёгкая прозрачность и скругление углов диалога
        try:
            apply_dialog_translucency(self, theme=self.colors.get('bg_primary', '#fff'))
        except Exception:
            pass

        self.create_widgets(device_data)

    def _close_with_geometry(self):
        """Сохраняет геометрию окна в config и закрывает его."""
        try:
            from utils.window_state import save_window_geometry
            save_window_geometry(self.settings, "device_form", self)
        except Exception:
            pass
        self.destroy()

    def _format_phone_input(self, event=None):
        """Маска телефона: форматирует ввод как +7 (XXX) XXX-XX-XX."""
        import re
        try:
            text = self.phone_entry.get()
            digits = re.sub(r'\D', '', text)
            if digits.startswith('8') and len(digits) == 11:
                digits = '7' + digits[1:]
            elif len(digits) == 10:
                digits = '7' + digits
            if len(digits) == 0:
                return
            if len(digits) <= 1:
                formatted = '+7'
            elif len(digits) <= 4:
                formatted = f'+7 ({digits[1:]}'
            elif len(digits) <= 7:
                formatted = f'+7 ({digits[1:4]}) {digits[4:]}'
            elif len(digits) <= 9:
                formatted = f'+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}'
            else:
                formatted = f'+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}'
            if formatted != text:
                cursor_pos = self.phone_entry.index("insert")
                self.phone_entry.delete(0, 'end')
                self.phone_entry.insert(0, formatted)
                self.phone_entry.icursor(min(cursor_pos + 1, len(formatted)))
        except Exception:
            pass

    def _on_client_name_input(self, event=None):
        """Автозаполнение: при вводе имени клиента ищет существующих в БД."""
        if not self.db:
            return
        try:
            name = self.client_name_entry.get().strip().lower()
            if len(name) < 2:
                return
            for device in self.db.get_all_devices(include_completed=True):
                existing_name = (device.get('client_name') or '').lower()
                if name in existing_name:
                    phone = device.get('phone', '')
                    status = device.get('client_status', 'Новый')
                    if not self.phone_entry.get().strip() and phone:
                        self.phone_entry.delete(0, 'end')
                        self.phone_entry.insert(0, phone)
                    if hasattr(self, 'client_status_combo'):
                        self.client_status_combo.set(status)
                    break
        except Exception:
            pass

    def _on_device_type_changed(self, choice=None):
        """Связка тип устройства -> фильтрация брендов."""
        if not self.db or not hasattr(self, 'brand_combo'):
            return
        try:
            device_type = self.device_type_combo.get()
            all_brands = self.db.get_dict_values('brands')
            type_brand_map = {
                'Смартфон': ['Apple', 'Samsung', 'Xiaomi', 'Huawei', 'Realme', 'Honor'],
                'Планшет': ['Apple', 'Samsung', 'Lenovo', 'Xiaomi'],
                'Ноутбук': ['Apple', 'HP', 'Dell', 'Lenovo', 'Asus', 'Acer'],
                'ПК': ['HP', 'Dell', 'Lenovo', 'Asus', 'Acer', 'MSI'],
                'Монитор': ['Samsung', 'LG', 'Asus', 'Acer', 'BenQ'],
            }
            relevant = type_brand_map.get(device_type, [])
            if relevant:
                other = [b for b in all_brands if b not in relevant]
                self.brand_combo.configure(values=relevant + other)
            else:
                self.brand_combo.configure(values=all_brands)
        except Exception:
            pass

    def create_widgets(self, device_data: Optional[Dict[str, Any]]):
        """Создание виджетов"""
        # Основной контейнер
        self.main_container = ctk.CTkFrame(self, fg_color=self.colors['bg_primary'])
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Заголовок
        title_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 15))
        
        icon_label = ctk.CTkLabel(
            title_frame,
            text="🔧" if self.is_new else "✏️",
            font=ctk.CTkFont(size=28),
            text_color=self.colors['accent']
        )
        icon_label.pack(side="left", padx=(0, 10))
        
        # Заголовок с предпросмотром номера заказа
        if self.is_new:
            from utils.formatters import generate_order_number
            # Показываем следующий номер (без инкремента БД)
            try:
                cursor = self.db.conn.cursor()
                cursor.execute('SELECT value FROM counters WHERE name = ?', ('order_counter',))
                row = cursor.fetchone()
                next_num = generate_order_number(row['value'] if row else 1)
            except Exception:
                next_num = "???"
            title_text = f"Новый заказ  ·  №{next_num}"
        else:
            from utils.formatters import format_order_number_for_display
            title_text = f"Редактирование заказа  ·  №{format_order_number_for_display(device_data.get('order_number', '') if device_data else '')}"

        title_label = ctk.CTkLabel(
            title_frame,
            text=title_text,
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors['accent']
        )
        title_label.pack(side="left")
        
        # Кнопки актов (только для редактирования)
        if not self.is_new:
            receipt_btn = ctk.CTkButton(
                title_frame,
                text="📄 Акт приема",
                command=self.show_receipt_act_preview,
                height=35,
                width=140,
                corner_radius=6,
                fg_color=self.colors['bg_tertiary'],
                text_color=self.colors['text_primary'],
                hover_color=self.colors['hover'],
                border_width=1,
                border_color=self.colors['border'],
                font=ctk.CTkFont(size=12)
            )
            receipt_btn.pack(side="right", padx=5)
            
            completion_btn = ctk.CTkButton(
                title_frame,
                text="🔧 Акт выполненных работ",
                command=self.show_completion_act_preview,
                height=35,
                width=180,
                corner_radius=6,
                fg_color=self.colors['bg_tertiary'],
                text_color=self.colors['text_primary'],
                hover_color=self.colors['hover'],
                border_width=1,
                border_color=self.colors['border'],
                font=ctk.CTkFont(size=12)
            )
            completion_btn.pack(side="right", padx=5)

        # --- Кнопки внизу (pack ПЕРВЫМ с side=bottom, до tabview) ---
        # Это гарантирует, что tabview(expand) не вытеснит кнопки за пределы.
        buttons_frame = ctk.CTkFrame(self.main_container, fg_color="transparent", height=50)
        buttons_frame.pack(fill="x", side="bottom", pady=(10, 5))
        buttons_frame.pack_propagate(False)

        # Создаем вкладки (pack последним — занимает остаток между top и bottom)
        self.tabview = ctk.CTkTabview(self.main_container, fg_color=self.colors['bg_primary'])
        self.tabview.pack(fill="both", expand=True, pady=(0, 10))

        # Вкладка "Устройство и клиент"
        tab_main = self.tabview.add("📱 Устройство и клиент")
        self.create_main_tab(tab_main, device_data)

        # Вкладка "Работы и финансы" (только для редактирования)
        if not self.is_new:
            tab_work = self.tabview.add("🔨 Работы и финансы")
            self.create_work_tab(tab_work, device_data)

        # Вкладка "Фото"
        tab_photos = self.tabview.add("📸 Фотографии")
        self.create_photos_tab(tab_photos)

        # Вкладка "История" (только для редактирования)
        if not self.is_new and device_data:
            tab_history = self.tabview.add("📋 История клиента")
            self.create_history_tab(tab_history, device_data)
        
        save_btn = ctk.CTkButton(
            buttons_frame,
            text="💾 Сохранить",
            command=self.save,
            height=38,
            width=140,
            corner_radius=8,
            fg_color=self.colors['accent'],
            text_color="white",
            hover_color=self.colors['accent_hover'],
            font=ctk.CTkFont(size=13, weight="bold")
        )
        save_btn.pack(side="right", padx=5)

        cancel_btn = ctk.CTkButton(
            buttons_frame,
            text="✖ Отмена",
            command=self.destroy,
            height=38,
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

        # Кнопка «Акт приёма» (слева) — для нового и существующего заказа
        receipt_act_btn = ctk.CTkButton(
            buttons_frame,
            text="📄 Акт приёма",
            command=self.print_receipt_from_form,
            height=38,
            width=130,
            corner_radius=8,
            fg_color=self.colors['bg_tertiary'],
            text_color=self.colors['text_primary'],
            hover_color=self.colors['hover'],
            border_width=1,
            border_color=self.colors['border'],
            font=ctk.CTkFont(size=12)
        )
        receipt_act_btn.pack(side="left", padx=5)

    def create_main_tab(self, parent, device_data):
        """Создание основной вкладки"""
        columns = ctk.CTkFrame(parent, fg_color="transparent")
        columns.pack(fill="both", expand=True, padx=10, pady=5)

        # Левая колонка — устройство
        left_col = ctk.CTkFrame(columns, fg_color="transparent")
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 5))

        # Правая колонка — клиент
        right_col = ctk.CTkFrame(columns, fg_color="transparent")
        right_col.pack(side="right", fill="both", expand=True, padx=(5, 0))

        # --- Левая колонка: устройство ---
        dev_card = ModernCard(left_col, self.colors)
        dev_card.pack(fill="both", expand=True)

        ctk.CTkLabel(dev_card, text="📱 Устройство",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=self.colors['accent']).pack(anchor="w", padx=12, pady=(8, 4))

        dev_frame = ctk.CTkFrame(dev_card, fg_color="transparent")
        dev_frame.pack(fill="x", padx=12, pady=(0, 8))

        labels = [
            ("Тип устройства:", "device_type"),
            ("Бренд:", "brand"),
            ("Модель:", "model"),
            ("Серийный номер:", "serial_number"),
            ("Внешний вид:", "appearance"),
            ("Комплектность:", "completeness"),
            ("Гарантия:", "warranty"),
        ]
        from utils.constants import DICTIONARY_TYPES
        from tkinter import ttk

        for i, (label_text, field_key) in enumerate(labels):
            ctk.CTkLabel(dev_frame, text=label_text,
                         font=ctk.CTkFont(size=12)).grid(row=i, column=0, sticky="w", pady=3)

            if field_key in ('device_type', 'brand', 'appearance', 'completeness'):
                dict_key = {'device_type': 'device_types', 'brand': 'brands',
                            'appearance': 'appearance', 'completeness': 'completeness'}[field_key]
                values = self.db.get_dict_values(dict_key) if self.db else []
                combo = ctk.CTkComboBox(dev_frame, values=values, width=200, height=30)
                combo.set(device_data.get(field_key, '') if device_data else '')
                combo.grid(row=i, column=1, sticky="ew", padx=(8, 0), pady=3)
                setattr(self, f"{field_key}_combo", combo)
            elif field_key == 'warranty':
                from utils.constants import WARRANTIES
                combo = ctk.CTkComboBox(dev_frame, values=WARRANTIES, width=200, height=30)
                combo.set(device_data.get(field_key, '') if device_data else '')
                combo.grid(row=i, column=1, sticky="ew", padx=(8, 0), pady=3)
                setattr(self, f"{field_key}_combo", combo)
            else:
                entry = ctk.CTkEntry(dev_frame, width=200, height=30,
                                     fg_color=self.colors['bg_tertiary'],
                                     border_color=self.colors['border'])
                entry.insert(0, device_data.get(field_key, '') if device_data else '')
                entry.grid(row=i, column=1, sticky="ew", padx=(8, 0), pady=3)
                setattr(self, f"{field_key}_entry" if field_key != 'serial_number' else "serial_entry", entry)

        # Неисправность
        ctk.CTkLabel(dev_frame, text="Неисправность:",
                     font=ctk.CTkFont(size=12)).grid(row=len(labels), column=0, sticky="nw", pady=3)
        self.defect_text = ctk.CTkTextbox(dev_frame, height=60, width=200,
                                           fg_color=self.colors['bg_tertiary'],
                                           border_color=self.colors['border'],
                                           border_width=1, corner_radius=6)
        self.defect_text.grid(row=len(labels), column=1, sticky="ew", padx=(8, 0), pady=3)
        if device_data:
            self.defect_text.insert("1.0", device_data.get('defect', ''))

        dev_frame.grid_columnconfigure(1, weight=1)

        # --- Правая колонка: клиент ---
        client_card = ModernCard(right_col, self.colors)
        client_card.pack(fill="both", expand=True)

        ctk.CTkLabel(client_card, text="👤 Клиент",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=self.colors['accent']).pack(anchor="w", padx=12, pady=(8, 4))

        client_frame = ctk.CTkFrame(client_card, fg_color="transparent")
        client_frame.pack(fill="x", padx=12, pady=(0, 8))

        # --- Подсветка обязательных полей ---
        required_color = self.colors.get('error', '#ff3b30')

        ctk.CTkLabel(client_frame, text="Имя клиента: *",
                     font=ctk.CTkFont(size=12), text_color=required_color).grid(row=0, column=0, sticky="w", pady=3)
        self.client_name_entry = ctk.CTkEntry(client_frame, width=200, height=30,
                                               fg_color=self.colors['bg_tertiary'],
                                               border_color=self.colors['border'])
        self.client_name_entry.insert(0, device_data.get('client_name', '') if device_data else '')
        self.client_name_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=3)
        # Автозаполнение клиента
        self.client_name_entry.bind("<KeyRelease>", self._on_client_name_input)

        ctk.CTkLabel(client_frame, text="Телефон: *",
                     font=ctk.CTkFont(size=12), text_color=required_color).grid(row=1, column=0, sticky="w", pady=3)
        self.phone_entry = ctk.CTkEntry(client_frame, width=200, height=30,
                                        fg_color=self.colors['bg_tertiary'],
                                        border_color=self.colors['border'])
        phone_val = device_data.get('phone', '') if device_data else ''
        self.phone_entry.insert(0, phone_val)
        self.phone_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=3)
        # Маска телефона
        self.phone_entry.bind("<KeyRelease>", self._format_phone_input)

        ctk.CTkLabel(client_frame, text="Статус клиента:",
                     font=ctk.CTkFont(size=12)).grid(row=2, column=0, sticky="w", pady=3)
        client_statuses = self.db.get_dict_values('client_statuses') if self.db else ['Новый']
        self.client_status_combo = ctk.CTkComboBox(client_frame, values=client_statuses, width=200, height=30)
        self.client_status_combo.set(device_data.get('client_status', 'Новый') if device_data else 'Новый')
        self.client_status_combo.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=3)

        # Финансы
        ctk.CTkLabel(client_frame, text="Стоимость (₽):",
                     font=ctk.CTkFont(size=12)).grid(row=3, column=0, sticky="w", pady=3)
        self.total_price_entry = ctk.CTkEntry(client_frame, width=200, height=30,
                                              fg_color=self.colors['bg_tertiary'],
                                              border_color=self.colors['border'])
        self.total_price_entry.insert(0, device_data.get('total_price', '') if device_data else '')
        self.total_price_entry.grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=3)

        ctk.CTkLabel(client_frame, text="Предоплата (₽):",
                     font=ctk.CTkFont(size=12)).grid(row=4, column=0, sticky="w", pady=3)
        self.prepayment_entry = ctk.CTkEntry(client_frame, width=200, height=30,
                                             fg_color=self.colors['bg_tertiary'],
                                             border_color=self.colors['border'])
        self.prepayment_entry.insert(0, device_data.get('prepayment', '') if device_data else '')
        self.prepayment_entry.grid(row=4, column=1, sticky="ew", padx=(8, 0), pady=3)

        ctk.CTkLabel(client_frame, text="Статус заказа:",
                     font=ctk.CTkFont(size=12)).grid(row=5, column=0, sticky="w", pady=3)
        from utils.constants import STATUSES
        self.status_combo = ctk.CTkComboBox(client_frame, values=STATUSES, width=200, height=30)
        self.status_combo.set(device_data.get('status', 'Диагностика') if device_data else 'Диагностика')
        self.status_combo.grid(row=5, column=1, sticky="ew", padx=(8, 0), pady=3)

        ctk.CTkLabel(client_frame, text="Приоритет:",
                     font=ctk.CTkFont(size=12)).grid(row=6, column=0, sticky="w", pady=3)
        from utils.constants import PRIORITIES
        self.priority_combo = ctk.CTkComboBox(client_frame, values=PRIORITIES, width=200, height=30)
        self.priority_combo.set(device_data.get('priority', 'Обычный') if device_data else 'Обычный')
        self.priority_combo.grid(row=6, column=1, sticky="ew", padx=(8, 0), pady=3)

        ctk.CTkLabel(client_frame, text="Инженер:",
                     font=ctk.CTkFont(size=12)).grid(row=7, column=0, sticky="w", pady=3)
        engineers = self.db.get_dict_values('engineers') if self.db else []
        self.engineer_combo = ctk.CTkComboBox(client_frame, values=engineers, width=200, height=30)
        self.engineer_combo.set(device_data.get('engineer', '') if device_data else '')
        self.engineer_combo.grid(row=7, column=1, sticky="ew", padx=(8, 0), pady=3)

        # Заметки
        ctk.CTkLabel(client_frame, text="Заметки:",
                     font=ctk.CTkFont(size=12)).grid(row=8, column=0, sticky="nw", pady=3)
        self.notes_text = ctk.CTkTextbox(client_frame, height=50, width=200,
                                         fg_color=self.colors['bg_tertiary'],
                                         border_color=self.colors['border'],
                                         border_width=1, corner_radius=6)
        self.notes_text.grid(row=8, column=1, sticky="ew", padx=(8, 0), pady=3)
        if device_data:
            self.notes_text.insert("1.0", device_data.get('notes', ''))

        # Расход
        ctk.CTkLabel(client_frame, text="Расход (₽):",
                     font=ctk.CTkFont(size=12)).grid(row=9, column=0, sticky="w", pady=3)
        self.expense_entry = ctk.CTkEntry(client_frame, width=200, height=30,
                                          fg_color=self.colors['bg_tertiary'],
                                          border_color=self.colors['border'])
        self.expense_entry.insert(0, device_data.get('expense', '0') if device_data else '0')
        self.expense_entry.grid(row=9, column=1, sticky="ew", padx=(8, 0), pady=3)

        client_frame.grid_columnconfigure(1, weight=1)

    def print_receipt_from_form(self):
        """Печать акта приёма прямо из формы (новый или существующий заказ).

        Для нового заказа: сначала сохраняет, потом печатает.
        """
        from tkinter import messagebox as _mb
        if self.is_new:
            # Сначала сохраняем заказ
            if not self._do_save(silent=True):
                _mb.showwarning("Внимание", "Сначала сохраните заказ (заполните обязательные поля)")
                return

        # Теперь заказ сохранён — печатаем акт
        device = self.db.get_device(self.device_data.get('id'))
        if not device:
            _mb.showerror("Ошибка", "Заказ не найден")
            return
        self.show_receipt_act_preview()

    def _do_save(self, silent: bool = False) -> bool:
        """Тихое сохранение без закрытия окна. Возвращает True при успехе."""
        try:
            from utils.formatters import normalize_phone
            from datetime import datetime as _dt

            client_name = self.client_name_entry.get().strip()
            phone_raw = self.phone_entry.get().strip()
            if not client_name or not phone_raw:
                if not silent:
                    _mb = __import__('tkinter.messagebox', fromlist=['showerror'])
                    _mb.showerror("Ошибка", "Заполните имя и телефон!")
                return False

            phone = normalize_phone(phone_raw)
            order_counter = self.db.get_next_order_number()
            from utils.formatters import generate_order_number
            order_number = generate_order_number(order_counter)

            # Собираем work_items
            work_items_json = self.work_manager.to_json() if self.work_manager.items else ''

            try:
                wm_total = int(self.work_manager.get_total_price()) if self.work_manager.items else 0
            except Exception:
                wm_total = 0
            total_price = str(wm_total) if wm_total > 0 else self.total_price_entry.get().strip()

            now = _dt.now().strftime('%Y-%m-%d %H:%M:%S')
            device_data = {
                'order_number': order_number,
                'receipt_date': now,
                'device_type': self.device_type_combo.get().strip() if hasattr(self, 'device_type_combo') else '',
                'brand': self.brand_combo.get().strip() if hasattr(self, 'brand_combo') else '',
                'model': self.model_entry.get().strip() if hasattr(self, 'model_entry') else '',
                'serial_number': self.serial_entry.get().strip() if hasattr(self, 'serial_entry') else '',
                'defect': self.defect_text.get("1.0", "end-1c").strip() if hasattr(self, 'defect_text') else '',
                'appearance': self.appearance_combo.get().strip() if hasattr(self, 'appearance_combo') else '',
                'completeness': self.completeness_combo.get().strip() if hasattr(self, 'completeness_combo') else '',
                'work_items_json': work_items_json,
                'client_name': client_name,
                'client_status': self.client_status_combo.get().strip() if hasattr(self, 'client_status_combo') else 'Новый',
                'phone': phone,
                'total_price': total_price,
                'prepayment': self.prepayment_entry.get().strip() if hasattr(self, 'prepayment_entry') else '',
                'status': self.status_combo.get().strip() if hasattr(self, 'status_combo') else 'Диагностика',
                'priority': self.priority_combo.get().strip() if hasattr(self, 'priority_combo') else 'Обычный',
                'engineer': self.engineer_combo.get().strip() if hasattr(self, 'engineer_combo') else '',
                'warranty': self.warranty_combo.get().strip() if hasattr(self, 'warranty_combo') else '',
                'notes': self.notes_text.get("1.0", "end-1c").strip() if hasattr(self, 'notes_text') else '',
                'photos': ','.join(self.current_photos) if self.current_photos else '',
                'expense': self.expense_entry.get().strip() if hasattr(self, 'expense_entry') else '0',
            }

            device_id = self.db.add_device(device_data)
            if device_id:
                self.client_db.add_repair_to_client_history(client_name, phone, device_data)
                self.is_new = False
                self.device_data = device_data
                self.device_data['id'] = device_id
                self.result = device_data
                if not silent:
                    from tkinter import messagebox
                    messagebox.showinfo("Успех", f"Заказ №{order_number} создан!")
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка сохранения: {e}", exc_info=True)
            return False

    def _create_main_tab_content(self, parent, device_data):
        """Создание основной вкладки (контент)."""
        columns = ctk.CTkFrame(parent, fg_color="transparent")
        columns.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Левая колонка - Устройство
        left = ctk.CTkFrame(columns, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(0, 5))
        
        device_frame = ctk.CTkFrame(left, fg_color=self.colors['bg_secondary'], corner_radius=10)
        device_frame.pack(fill="both", expand=True)
        
        ctk.CTkLabel(
            device_frame,
            text="📱 УСТРОЙСТВО",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors['accent']
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Информация о дате и времени приема
        info_frame = ctk.CTkFrame(device_frame, fg_color="transparent")
        info_frame.pack(fill="x", padx=15, pady=(0, 10))
        
        ctk.CTkLabel(
            info_frame,
            text="📅 Дата приема:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.colors['text_secondary']
        ).pack(side="left")
        
        # Форматируем дату для отображения
        current_datetime = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        if not self.is_new and device_data and device_data.get('receipt_date'):
            receipt_date = device_data.get('receipt_date')
            try:
                if ' ' in receipt_date:
                    dt = datetime.strptime(receipt_date[:19], "%Y-%m-%d %H:%M:%S")
                else:
                    dt = datetime.strptime(receipt_date[:10], "%Y-%m-%d")
                current_datetime = dt.strftime("%d.%m.%Y %H:%M:%S")
            except Exception as e:
                logger.warning(f"Ошибка парсинга даты приема {receipt_date}: {e}")
        
        self.receipt_datetime_label = ctk.CTkLabel(
            info_frame,
            text=current_datetime,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.colors['success']
        )
        self.receipt_datetime_label.pack(side="left", padx=(10, 0))
        
        # Кнопка обновления времени (только для редактирования)
        if not self.is_new:
            update_time_btn = ctk.CTkButton(
                info_frame,
                text="🔄 Обновить время",
                command=self.update_receipt_time,
                height=25,
                width=120,
                corner_radius=6,
                fg_color=self.colors['bg_tertiary'],
                text_color=self.colors['text_primary'],
                hover_color=self.colors['hover'],
                border_width=1,
                border_color=self.colors['border'],
                font=ctk.CTkFont(size=10)
            )
            update_time_btn.pack(side="right")
        
        # Линия-разделитель
        separator = ctk.CTkFrame(device_frame, height=1, fg_color=self.colors['border'])
        separator.pack(fill="x", padx=15, pady=(0, 10))
        
        # Поля устройства
        fields_frame = ctk.CTkFrame(device_frame, fg_color="transparent")
        fields_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        # Тип
        ctk.CTkLabel(fields_frame, text="Тип*:", font=ctk.CTkFont(size=12)).grid(row=0, column=0, sticky="w", pady=5)
        self.device_type_combo = ctk.CTkComboBox(
            fields_frame, values=self.db.get_dict_values('device_types'), width=200,
            fg_color=self.colors['bg_tertiary'], border_color=self.colors['border']
        )
        if device_data and device_data.get('device_type'):
            self.device_type_combo.set(device_data['device_type'])
        elif self.db.get_dict_values('device_types'):
            self.device_type_combo.set(self.db.get_dict_values('device_types')[0])
        self.device_type_combo.grid(row=0, column=1, sticky="ew", pady=5, padx=(10, 0))
        self.device_type_combo.bind("<<ComboboxSelected>>", self._on_device_type_changed)
        
        # Бренд
        ctk.CTkLabel(fields_frame, text="Бренд:", font=ctk.CTkFont(size=12)).grid(row=1, column=0, sticky="w", pady=5)
        self.brand_combo = ctk.CTkComboBox(
            fields_frame, values=self.db.get_dict_values('brands'), width=200,
            fg_color=self.colors['bg_tertiary'], border_color=self.colors['border']
        )
        if device_data and device_data.get('brand'):
            self.brand_combo.set(device_data['brand'])
        self.brand_combo.grid(row=1, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        # Модель
        ctk.CTkLabel(fields_frame, text="Модель*:", font=ctk.CTkFont(size=12)).grid(row=2, column=0, sticky="w", pady=5)
        self.model_entry = ctk.CTkEntry(
            fields_frame, width=200, placeholder_text="Введите модель",
            fg_color=self.colors['bg_tertiary'], border_color=self.colors['border']
        )
        if device_data and device_data.get('model'):
            self.model_entry.insert(0, device_data['model'])
        self.model_entry.grid(row=2, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        # S/N
        ctk.CTkLabel(fields_frame, text="S/N:", font=ctk.CTkFont(size=12)).grid(row=3, column=0, sticky="w", pady=5)
        self.serial_entry = ctk.CTkEntry(
            fields_frame, width=200, placeholder_text="Введите серийный номер",
            fg_color=self.colors['bg_tertiary'], border_color=self.colors['border']
        )
        if device_data and device_data.get('serial_number'):
            self.serial_entry.insert(0, device_data['serial_number'])
        self.serial_entry.grid(row=3, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        # Неисправность
        ctk.CTkLabel(fields_frame, text="Неисправность*:", font=ctk.CTkFont(size=12)).grid(row=4, column=0, sticky="nw", pady=5)
        self.defect_text = ctk.CTkTextbox(
            fields_frame, height=80, width=200,
            fg_color=self.colors['bg_tertiary'], border_color=self.colors['border']
        )
        if device_data and device_data.get('defect'):
            self.defect_text.insert("1.0", device_data['defect'])
        self.defect_text.grid(row=4, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        # Внешний вид
        ctk.CTkLabel(fields_frame, text="Внешний вид:", font=ctk.CTkFont(size=12)).grid(row=5, column=0, sticky="w", pady=5)
        self.appearance_combo = ctk.CTkComboBox(
            fields_frame, values=self.db.get_dict_values('appearance'), width=200,
            fg_color=self.colors['bg_tertiary'], border_color=self.colors['border']
        )
        if device_data and device_data.get('appearance'):
            self.appearance_combo.set(device_data['appearance'])
        elif self.db.get_dict_values('appearance'):
            self.appearance_combo.set(self.db.get_dict_values('appearance')[0])
        self.appearance_combo.grid(row=5, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        # Комплектация
        ctk.CTkLabel(fields_frame, text="Комплектация:", font=ctk.CTkFont(size=12)).grid(row=6, column=0, sticky="w", pady=5)
        self.completeness_combo = ctk.CTkComboBox(
            fields_frame, values=self.db.get_dict_values('completeness'), width=200,
            fg_color=self.colors['bg_tertiary'], border_color=self.colors['border']
        )
        if device_data and device_data.get('completeness'):
            self.completeness_combo.set(device_data['completeness'])
        elif self.db.get_dict_values('completeness'):
            self.completeness_combo.set(self.db.get_dict_values('completeness')[0])
        self.completeness_combo.grid(row=6, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        # Статус
        ctk.CTkLabel(fields_frame, text="Статус:", font=ctk.CTkFont(size=12)).grid(row=7, column=0, sticky="w", pady=5)
        self.status_combo = ctk.CTkComboBox(
            fields_frame, values=STATUSES, width=200,
            fg_color=self.colors['bg_tertiary'], border_color=self.colors['border']
        )
        if device_data and device_data.get('status'):
            self.status_combo.set(device_data['status'])
        else:
            self.status_combo.set("Диагностика")
        self.status_combo.grid(row=7, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        fields_frame.grid_columnconfigure(1, weight=1)
        
        # Правая колонка - Клиент
        right = ctk.CTkFrame(columns, fg_color="transparent")
        right.pack(side="right", fill="both", expand=True, padx=(5, 0))
        
        client_frame = ctk.CTkFrame(right, fg_color=self.colors['bg_secondary'], corner_radius=10)
        client_frame.pack(fill="both", expand=True)
        
        ctk.CTkLabel(
            client_frame,
            text="👤 КЛИЕНТ",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors['accent']
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        client_fields = ctk.CTkFrame(client_frame, fg_color="transparent")
        client_fields.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        # ФИО
        ctk.CTkLabel(client_fields, text="ФИО*:", font=ctk.CTkFont(size=12)).grid(row=0, column=0, sticky="w", pady=5)
        self.client_name_entry = ctk.CTkEntry(
            client_fields, width=200, placeholder_text="Введите ФИО клиента",
            fg_color=self.colors['bg_tertiary'], border_color=self.colors['border']
        )
        if device_data and device_data.get('client_name'):
            self.client_name_entry.insert(0, device_data['client_name'])
        self.client_name_entry.grid(row=0, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        # Статус клиента
        ctk.CTkLabel(client_fields, text="Статус клиента:", font=ctk.CTkFont(size=12)).grid(row=1, column=0, sticky="w", pady=5)
        self.client_status_combo = ctk.CTkComboBox(
            client_fields, values=CLIENT_STATUSES, width=200,
            fg_color=self.colors['bg_tertiary'], border_color=self.colors['border']
        )
        if device_data and device_data.get('client_status'):
            self.client_status_combo.set(device_data['client_status'])
        else:
            self.client_status_combo.set("Новый")
        self.client_status_combo.grid(row=1, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        # Телефон
        ctk.CTkLabel(client_fields, text="Телефон*:", font=ctk.CTkFont(size=12)).grid(row=2, column=0, sticky="w", pady=5)
        self.phone_entry = ctk.CTkEntry(
            client_fields, width=200, placeholder_text="+7 (XXX) XXX-XX-XX",
            fg_color=self.colors['bg_tertiary'], border_color=self.colors['border']
        )
        if device_data and device_data.get('phone'):
            self.phone_entry.insert(0, device_data['phone'])
        self.phone_entry.grid(row=2, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        # Инженер
        ctk.CTkLabel(client_fields, text="Инженер:", font=ctk.CTkFont(size=12)).grid(row=3, column=0, sticky="w", pady=5)
        self.engineer_combo = ctk.CTkComboBox(
            client_fields, values=self.db.get_dict_values('engineers'), width=200,
            fg_color=self.colors['bg_tertiary'], border_color=self.colors['border']
        )
        if device_data and device_data.get('engineer'):
            self.engineer_combo.set(device_data['engineer'])
        elif self.db.get_dict_values('engineers'):
            self.engineer_combo.set(self.db.get_dict_values('engineers')[0])
        self.engineer_combo.grid(row=3, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        # Общая цена
        ctk.CTkLabel(client_fields, text="Общая цена:", font=ctk.CTkFont(size=12)).grid(row=4, column=0, sticky="w", pady=5)
        self.total_price_entry = ctk.CTkEntry(
            client_fields, width=200, placeholder_text="0",
            fg_color=self.colors['bg_tertiary'], border_color=self.colors['border']
        )
        if device_data and device_data.get('total_price'):
            self.total_price_entry.insert(0, device_data['total_price'])
        self.total_price_entry.grid(row=4, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        # Предоплата
        ctk.CTkLabel(client_fields, text="Предоплата:", font=ctk.CTkFont(size=12)).grid(row=5, column=0, sticky="w", pady=5)
        self.prepayment_entry = ctk.CTkEntry(
            client_fields, width=200, placeholder_text="0",
            fg_color=self.colors['bg_tertiary'], border_color=self.colors['border']
        )
        if device_data and device_data.get('prepayment'):
            self.prepayment_entry.insert(0, device_data['prepayment'])
        self.prepayment_entry.grid(row=5, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        # Затраты
        ctk.CTkLabel(client_fields, text="Затраты (₽):", font=ctk.CTkFont(size=12)).grid(row=6, column=0, sticky="w", pady=5)
        self.expense_entry = ctk.CTkEntry(
            client_fields, width=200, placeholder_text="0",
            fg_color=self.colors['bg_tertiary'], border_color=self.colors['border']
        )
        if device_data and device_data.get('expense'):
            self.expense_entry.insert(0, device_data['expense'])
        self.expense_entry.grid(row=6, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        # Приоритет
        ctk.CTkLabel(client_fields, text="Приоритет:", font=ctk.CTkFont(size=12)).grid(row=7, column=0, sticky="w", pady=5)
        self.priority_combo = ctk.CTkComboBox(
            client_fields, values=PRIORITIES, width=200,
            fg_color=self.colors['bg_tertiary'], border_color=self.colors['border']
        )
        if device_data and device_data.get('priority'):
            self.priority_combo.set(device_data['priority'])
        else:
            self.priority_combo.set("Обычный")
        self.priority_combo.grid(row=7, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        # Гарантия
        ctk.CTkLabel(client_fields, text="Гарантия:", font=ctk.CTkFont(size=12)).grid(row=8, column=0, sticky="w", pady=5)
        self.warranty_combo = ctk.CTkComboBox(
            client_fields, values=WARRANTIES, width=200,
            fg_color=self.colors['bg_tertiary'], border_color=self.colors['border']
        )
        if device_data and device_data.get('warranty'):
            self.warranty_combo.set(device_data['warranty'])
        self.warranty_combo.grid(row=8, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        # Заметки
        ctk.CTkLabel(client_fields, text="Заметки:", font=ctk.CTkFont(size=12)).grid(row=9, column=0, sticky="nw", pady=5)
        self.notes_text = ctk.CTkTextbox(
            client_fields, height=120, width=200,
            fg_color=self.colors['bg_tertiary'], border_color=self.colors['border']
        )
        if device_data and device_data.get('notes'):
            self.notes_text.insert("1.0", device_data['notes'])
        self.notes_text.grid(row=9, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        client_fields.grid_columnconfigure(1, weight=1)
    
    def update_receipt_time(self):
        """Обновление даты и времени приема на текущие"""
        current_datetime = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        if hasattr(self, 'receipt_datetime_label'):
            self.receipt_datetime_label.configure(text=current_datetime)
        messagebox.showinfo("Успех", f"Дата и время приема обновлены на {current_datetime}")
    
    def create_work_tab(self, parent, device_data):
        """Создание вкладки с работами"""
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10, pady=10)
        
        info_frame = ctk.CTkFrame(container, fg_color=self.colors['bg_secondary'], corner_radius=10)
        info_frame.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(
            info_frame,
            text=f"Заказ №: {format_order_number_for_display(device_data.get('order_number', ''))}",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors['accent']
        ).pack(anchor="w", padx=15, pady=10)
        
        work_frame = ctk.CTkFrame(container, fg_color=self.colors['bg_secondary'], corner_radius=10)
        work_frame.pack(fill="both", expand=True)
        
        ctk.CTkLabel(
            work_frame,
            text="🔨 ВЫПОЛНЕННЫЕ РАБОТЫ",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors['accent']
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        self.work_table = WorkItemsTable(
            work_frame,
            self.colors,
            self.work_manager,
            on_total_changed=self.on_work_total_changed,
            db=self.db,
            settings=self.settings
        )
    
    def create_photos_tab(self, parent):
        """Создание вкладки с фото"""
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10, pady=10)
        
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(0, 10))
        
        add_btn = ctk.CTkButton(
            btn_frame,
            text="➕ Добавить фотографию",
            command=self.add_photos,
            height=40,
            width=180,
            corner_radius=8,
            fg_color=self.colors['accent'],
            text_color="white",
            hover_color=self.colors['accent_hover'],
            font=ctk.CTkFont(size=13, weight="bold")
        )
        add_btn.pack(side="left")
        
        self.photos_label = ctk.CTkLabel(
            btn_frame,
            text=f"📸 Фото: {len(self.current_photos)}",
            font=ctk.CTkFont(size=12),
            text_color=self.colors['text_secondary']
        )
        self.photos_label.pack(side="left", padx=(15, 0))
        
        photos_frame = ctk.CTkFrame(container, fg_color=self.colors['bg_secondary'], corner_radius=10)
        photos_frame.pack(fill="both", expand=True)
        
        ctk.CTkLabel(
            photos_frame,
            text="СПИСОК ФОТОГРАФИЙ",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors['accent']
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        scroll_frame = ctk.CTkScrollableFrame(photos_frame, fg_color="transparent", height=400)
        scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        self.thumbnails_container = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        self.thumbnails_container.pack(fill="x", padx=5, pady=5)
        
        self.update_photos_display()
    
    def create_history_tab(self, parent, device_data):
        """Создание вкладки с историей"""
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10, pady=10)
        
        stats = self.client_db.get_client_stats(
            device_data.get('client_name', ''), 
            device_data.get('phone', '')
        )
        
        stats_frame = ctk.CTkFrame(container, fg_color=self.colors['bg_secondary'], corner_radius=10)
        stats_frame.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(
            stats_frame,
            text="📊 СТАТИСТИКА КЛИЕНТА",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors['accent']
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        stats_grid = ctk.CTkFrame(stats_frame, fg_color="transparent")
        stats_grid.pack(fill="x", padx=15, pady=(0, 15))
        
        ctk.CTkLabel(stats_grid, text=f"Всего ремонтов: {stats.get('total_orders', 0)}", font=ctk.CTkFont(size=12)).grid(row=0, column=0, sticky="w", pady=5)
        ctk.CTkLabel(stats_grid, text=f"Завершено: {stats.get('completed_orders', 0)}", font=ctk.CTkFont(size=12)).grid(row=0, column=1, sticky="w", pady=5, padx=(20, 0))
        ctk.CTkLabel(stats_grid, text=f"Общая сумма: {format_price(str(stats.get('total_spent', 0)))}", font=ctk.CTkFont(size=12)).grid(row=1, column=0, sticky="w", pady=5)
        
        history_btn = ctk.CTkButton(
            container,
            text="📜 Открыть полную историю",
            command=lambda: ClientHistoryWindow(
                self, self.db, self.client_db,
                device_data.get('client_name', ''), 
                device_data.get('phone', ''),
                device_data.get('client_status', 'Новый'),
                self.colors
            ),
            height=40,
            corner_radius=8,
            fg_color=self.colors['accent'],
            text_color="white",
            hover_color=self.colors['accent_hover'],
            font=ctk.CTkFont(size=13, weight="bold")
        )
        history_btn.pack(pady=20)
    
    def on_work_total_changed(self, total: float):
        """Обработка изменения общей суммы работ.

        Если добавлена хотя бы одна выполненная работа — автоматически меняем
        статус заказа на «Готов к выдаче» (если он ещё не выше по «лестнице»
        статусов: Готов/Выдан/Отказ не трогаем).
        """
        self.total_price_entry.delete(0, 'end')
        self.total_price_entry.insert(0, str(int(total)))

        # Автосмена статуса при появлении выполненных работ
        try:
            if self.work_manager.items and hasattr(self, 'status_combo'):
                current_status = self.status_combo.get().strip()
                # Не перезаписываем финальные статусы
                if current_status not in ('Готов к выдаче', 'Выдан клиенту', 'Отказ от ремонта'):
                    self.status_combo.set('Готов к выдаче')
        except Exception:
            pass
    
    def add_photos(self):
        """Добавление фотографий"""
        files = filedialog.askopenfilenames(
            title="Выберите фотографии",
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.gif *.bmp")]
        )
        
        if files:
            client_name = self.client_name_entry.get().strip()
            client_phone = self.phone_entry.get().strip()
            
            if not client_name or not client_phone:
                messagebox.showerror("Ошибка", "Сначала заполните ФИО и телефон клиента")
                return
            
            order_number = "new"
            if not self.is_new and self.device_data:
                order_number = self.device_data.get('order_number', '')
            
            saved_count = 0
            for file in files:
                photo_path = self.photo_manager.save_photo(file, client_name, client_phone, order_number, "device")
                if photo_path:
                    self.current_photos.append(photo_path)
                    saved_count += 1
            
            if saved_count > 0:
                messagebox.showinfo("Успех", f"✅ Добавлено {saved_count} фото")
                self.update_photos_display()
    
    def delete_photo(self, photo_path: str):
        """Удаление фотографии"""
        if messagebox.askyesno("Подтверждение", "Удалить фото?"):
            if photo_path in self.current_photos:
                self.current_photos.remove(photo_path)
                if os.path.exists(photo_path):
                    try:
                        os.remove(photo_path)
                    except Exception as e:
                        logger.error(f"Ошибка удаления фото {photo_path}: {e}")
                self.update_photos_display()
    
    def view_photo(self, photo_path: str):
        """Просмотр фотографии — открывает все фото заказа с навигацией."""
        if os.path.exists(photo_path):
            # Передаём ВСЕ фото заказа, чтобы работала навигация ◀ ▶
            all_photos = list(self.current_photos)
            try:
                start_idx = all_photos.index(photo_path)
            except ValueError:
                start_idx = 0
            viewer = PhotoViewerWindow(self, self.photo_manager, all_photos,
                                       self.colors, title="Просмотр фото", settings=self.settings)
            viewer.current_index = start_idx
            viewer.load_current_photo()
    
    def update_photos_display(self):
        """Обновление отображения фотографий"""
        for widget in self.thumbnail_widgets:
            widget.destroy()
        self.thumbnail_widgets.clear()
        
        if self.current_photos:
            for photo_path in self.current_photos:
                if os.path.exists(photo_path):
                    thumb_widget = ThumbnailWidget(
                        self.thumbnails_container,
                        self.photo_manager,
                        photo_path,
                        self.colors,
                        on_delete=self.delete_photo,
                        on_click=self.view_photo
                    )
                    thumb_widget.pack(side="left", padx=5, pady=5)
                    self.thumbnail_widgets.append(thumb_widget)
            
            self.photos_label.configure(text=f"📸 Фото: {len(self.current_photos)}")
        else:
            self.photos_label.configure(text="📸 Фото: 0")
    
    def print_dual_from_form(self):
        """Печать двух актов на одном листе A4 из формы заказа."""
        import customtkinter as _ctk
        from tkinter import messagebox as _mb

        device = self.db.get_device(self.device_data.get('id'))
        if not device:
            _mb.showerror("Ошибка", "Заказ не найден")
            return

        # work_items для акта выполненных работ
        work_items_json = device.get('work_items', '')
        if work_items_json:
            wm = WorkItemsManager()
            wm.from_json(work_items_json)
            device['completed_work'] = wm.get_description_summary()

        # Кастомный диалог выбора режима
        dlg = _ctk.CTkToplevel(self)
        dlg.title("Два акта на листе A4")
        dlg.geometry("380x300")
        dlg.transient(self)
        dlg.grab_set()
        dlg.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 380) // 2
        y = self.winfo_y() + (self.winfo_height() - 300) // 2
        dlg.geometry(f"+{x}+{y}")

        result = {'choice': None}

        _ctk.CTkLabel(dlg, text="📋 Выберите режим печати",
                      font=_ctk.CTkFont(size=15, weight="bold"),
                      text_color=self.colors['accent']).pack(pady=(16, 10))

        def _choose(val):
            result['choice'] = val
            dlg.destroy()

        for text, val, variant in [
            ("📄📄  2× Акт приёма", 'receipt2', "primary"),
            ("🔧🔧  2× Акт выполненных работ", 'completion2', "primary"),
            ("📄🔧  Акт приёма + Акт работ", 'both', "secondary"),
        ]:
            _ctk.CTkButton(dlg, text=text, command=lambda v=val: _choose(v),
                          height=40, width=300, corner_radius=8,
                          fg_color=self.colors['accent'] if variant == "primary" else self.colors['bg_tertiary'],
                          text_color="white" if variant == "primary" else self.colors['text_primary'],
                          hover_color=self.colors.get('accent_hover', self.colors['hover']),
                          font=_ctk.CTkFont(size=12)).pack(pady=4)

        _ctk.CTkButton(dlg, text="✖ Отмена", command=dlg.destroy,
                      height=34, width=300, corner_radius=8,
                      fg_color=self.colors['bg_tertiary'],
                      text_color=self.colors['text_primary']).pack(pady=(8, 4))

        self.wait_window(dlg)
        choice = result['choice']
        if not choice:
            return

        if choice == 'receipt2':
            act_type1, act_type2, tpl_key = "receipt", "receipt", 'receipt'
        elif choice == 'completion2':
            act_type1, act_type2, tpl_key = "completion", "completion", 'completion'
        else:
            act_type1, act_type2, tpl_key = "receipt", "completion", 'receipt'

        from tkinter import filedialog as _fd
        from reports.report_renderer import ActPDFGenerator

        file_path = _fd.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")],
            initialfile=f"acts_{device.get('order_number', 'order')}.pdf")
        if not file_path:
            return

        tpl = self._load_act_template(tpl_key)
        gen = ActPDFGenerator(template_data=tpl)
        ok = gen.generate_dual_pdf(file_path, device, device,
                                   act_type1=act_type1, act_type2=act_type2)
        if ok:
            _mb.showinfo("Успех", f"Два акта на A4 сохранены:\n{file_path}")
            import os as _os, sys as _sys
            if _sys.platform == 'win32':
                _os.startfile(file_path)
        else:
            _mb.showerror("Ошибка", "Не удалось создать PDF")

    def _load_act_template(self, act_type: str) -> dict:
        """Загружает шаблон акта из JSON (настройки редактора актов).

        act_type: 'receipt' или 'completion'. Возвращает dict (пустой при ошибке).
        Позволяет применять настройки редактора (заголовок, поля, цвет,
        условия, логотип) к актам, печатаемым из формы заказа.
        """
        import json
        import os as _os
        try:
            # device_form.py в gui/dialogs/, корень проекта = 3x dirname
            project_root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
            template_dir = _os.path.join(project_root, 'reports', 'templates')
            filename = 'receipt_act.json' if act_type == 'receipt' else 'completion_act.json'
            path = _os.path.join(template_dir, filename)
            if _os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Не удалось загрузить шаблон акта: {e}", exc_info=True)
        return {}

    def show_receipt_act_preview(self):
        """Показать предпросмотр акта приема"""
        report_gen = ReportGenerator()
        device = self.db.get_device(self.device_data.get('id'))
        if device:
            filename = report_gen.generate_receipt_act(device)
            if filename and os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    content = f.read()
                template = self._load_act_template('receipt')
                ActPreviewWindow(self, "Акт приема", content, self.colors, "receipt", device, template, settings=self.settings)

    def show_completion_act_preview(self):
        """Показать предпросмотр акта выполненных работ"""
        report_gen = ReportGenerator()
        device = self.db.get_device(self.device_data.get('id'))
        if device:
            work_items_json = device.get('work_items', '')
            if work_items_json:
                work_manager = WorkItemsManager()
                work_manager.from_json(work_items_json)
                device['completed_work'] = work_manager.get_description_summary()

            filename = report_gen.generate_completion_act(device)
            if filename and os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    content = f.read()
                template = self._load_act_template('completion')
                ActPreviewWindow(self, "Акт выполненных работ", content, self.colors, "completion", device, template, settings=self.settings)
    
    def save(self):
        """Сохранение данных"""
        try:
            # Сбор данных
            device_type = self.device_type_combo.get().strip()
            brand = self.brand_combo.get().strip()
            model = self.model_entry.get().strip()
            serial_number = self.serial_entry.get().strip()
            defect = self.defect_text.get("1.0", "end-1c").strip()
            appearance = self.appearance_combo.get().strip()
            completeness = self.completeness_combo.get().strip()
            client_name = self.client_name_entry.get().strip()
            client_status = self.client_status_combo.get().strip()
            phone_raw = self.phone_entry.get().strip()
            # БЕРЁМ total_price из work_manager (актуальная сумма работ), а не только
            # из entry — entry мог быть пустым или не обновляться после правок работ.
            # Это исправляет «не отображается общая сумма» в истории клиента.
            try:
                wm_total = int(self.work_manager.get_total_price())
            except Exception:
                wm_total = 0
            total_price_from_entry = self.total_price_entry.get().strip()
            # Приоритет — фактическая сумма работ; иначе значение из поля (если вводили вручную)
            if wm_total > 0:
                total_price = str(wm_total)
                # Синхронизируем поле с актуальной суммой
                self.total_price_entry.delete(0, 'end')
                self.total_price_entry.insert(0, str(wm_total))
            else:
                total_price = total_price_from_entry
            prepayment = self.prepayment_entry.get().strip()
            expense = self.expense_entry.get().strip() if hasattr(self, 'expense_entry') else "0"
            priority = self.priority_combo.get().strip()
            engineer = self.engineer_combo.get().strip()
            warranty = self.warranty_combo.get().strip()
            notes = self.notes_text.get("1.0", "end-1c").strip()
            status = self.status_combo.get().strip()

            photos_str = ','.join(self.current_photos) if self.current_photos else ''
            work_items_json = self.work_manager.to_json() if hasattr(self, 'work_manager') else ''

            # Получаем дату приема
            if hasattr(self, 'receipt_datetime_label'):
                receipt_date_str = self.receipt_datetime_label.cget("text")
                try:
                    dt = datetime.strptime(receipt_date_str, "%d.%m.%Y %H:%M:%S")
                    receipt_date = dt.strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    receipt_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                receipt_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Валидация
            if not device_type:
                messagebox.showerror("Ошибка", "Выберите тип устройства!")
                return
            if not model:
                messagebox.showerror("Ошибка", "Заполните модель устройства!")
                return
            if not defect:
                messagebox.showerror("Ошибка", "Опишите неисправность!")
                return
            if not client_name:
                messagebox.showerror("Ошибка", "Заполните ФИО клиента!")
                return
            if not phone_raw:
                messagebox.showerror("Ошибка", "Заполните номер телефона!")
                return

            if not validate_phone(phone_raw):
                messagebox.showerror("Ошибка", "Неверный формат телефона!\nПример: +7 (123) 456-78-90")
                return

            if total_price and not validate_price(total_price):
                messagebox.showerror("Ошибка", "Неверный формат цены!")
                return

            if prepayment and not validate_price(prepayment):
                messagebox.showerror("Ошибка", "Неверный формат предоплаты!")
                return

            if expense and not validate_price(expense):
                messagebox.showerror("Ошибка", "Неверный формат затрат!")
                return

            # Нормализуем телефон к единому каноничному виду.
            # Раньше телефон сохранялся «как ввёл пользователь» (с любыми
            # разделителями), из-за чего поиск по телефону ничего не находил.
            phone = normalize_phone(phone_raw)

            if self.is_new:
                # Создание нового заказа
                order_counter = self.db.get_next_order_number()
                order_number = generate_order_number(order_counter)

                device_data = {
                    'order_number': order_number,
                    'receipt_date': receipt_date,
                    'device_type': device_type,
                    'brand': brand,
                    'model': model,
                    'serial_number': serial_number,
                    'defect': defect,
                    'appearance': appearance,
                    'completeness': completeness,
                    'work_items_json': work_items_json,
                    'client_name': client_name,
                    'client_status': client_status,
                    'phone': phone,
                    'total_price': total_price,
                    'prepayment': prepayment,
                    'priority': priority,
                    'engineer': engineer,
                    'warranty': warranty,
                    'notes': notes,
                    'status': status,
                    'photos': photos_str,
                    'expense': expense
                }

                device_id = self.db.add_device(device_data)

                if device_id:
                    # Сохраняем в историю клиента
                    self.client_db.add_repair_to_client_history(client_name, phone, device_data)

                    self.result = device_data
                    self._close_with_geometry()
                    messagebox.showinfo("Успех", f"✅ Заказ #{format_order_number_for_display(order_number)} создан!")
                else:
                    messagebox.showerror("Ошибка", "❌ Не удалось создать заказ")
            else:
                # Обновление существующего заказа
                existing_order_number = self.device_data.get('order_number', '')
                completion_date = ""
                if status == 'Выдан клиенту':
                    completion_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                device_data = {
                    # КРИТИЧНО: order_number должен присутствовать в данных,
                    # иначе db.update_device() записывает в finances с пустым
                    # номером и нарушает UNIQUE(order_number).
                    'order_number': existing_order_number,
                    'device_type': device_type,
                    'brand': brand,
                    'model': model,
                    'serial_number': serial_number,
                    'defect': defect,
                    'appearance': appearance,
                    'completeness': completeness,
                    'work_items_json': work_items_json,
                    'client_name': client_name,
                    'client_status': client_status,
                    'phone': phone,
                    'total_price': total_price,
                    'prepayment': prepayment,
                    'priority': priority,
                    'engineer': engineer,
                    'warranty': warranty,
                    'notes': notes,
                    'status': status,
                    'photos': photos_str,
                    'completion_date': completion_date,
                    'expense': expense
                }

                if self.db.update_device(self.device_data.get('id'), device_data):
                    # Обновляем в истории клиента
                    self.client_db.update_repair_in_history(
                        client_name, phone, existing_order_number, device_data)

                    self.result = device_data
                    self._close_with_geometry()
                    messagebox.showinfo("Успех", "✅ Заказ обновлен!")
                else:
                    messagebox.showerror("Ошибка", "❌ Не удалось обновить заказ")

        except Exception as e:
            messagebox.showerror("Ошибка", f"❌ Ошибка сохранения: {str(e)}")
            import traceback
            traceback.print_exc()
