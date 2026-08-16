#!/usr/bin/env python3
"""DeviceWidgetsMixin — построение виджетов диалога (вкладки "Устройство и
клиент"/"Работы и финансы"/"Фото"/"История") + связанные input-хендлеры.
См. AUDIT_REPORT_v25.md, Task T (перенесено из device_form.py без
изменения поведения).

Примечание: _create_main_tab_content() (альтернативная, независимо
продублированная реализация главной вкладки) была здесь и НЕ вызывалась
ниоткуда (create_widgets зовёт именно create_main_tab, не её) — удалена
как мёртвый код при переносе, не перенесена, см. AUDIT_REPORT_v25.md."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import customtkinter as ctk

from domain.constants import (
    CLOSED_STATUSES,
    PRIORITIES,
    STATUS_READY,
    STATUSES,
    WARRANTIES,
)
from gui.dialogs.client_history import ClientHistoryWindow
from gui.widgets.modern import ModernCard
from gui.widgets.work_table import WorkItemsTable
from utils.formatters import format_order_number_for_display, format_price

logger = logging.getLogger(__name__)


class DeviceWidgetsMixin:
    """Требует от финального класса DeviceFormDialog: self.colors, self.db,
    self.is_new, self.settings, self.employees_api, self.lock_api,
    self.report_gen, self.client_db, self.work_manager, self.current_photos
    — все выставляются в DeviceFormDialog.__init__."""

    def _format_phone_input(self, event=None):
        """Маска телефона: форматирует ввод как +7 (XXX) XXX-XX-XX."""
        import re

        try:
            text = self.phone_entry.get()
            digits = re.sub(r"\D", "", text)
            if digits.startswith("8") and len(digits) == 11:
                digits = "7" + digits[1:]
            elif len(digits) == 10:
                digits = "7" + digits
            if len(digits) == 0:
                return
            if len(digits) <= 1:
                formatted = "+7"
            elif len(digits) <= 4:
                formatted = f"+7 ({digits[1:]}"
            elif len(digits) <= 7:
                formatted = f"+7 ({digits[1:4]}) {digits[4:]}"
            elif len(digits) <= 9:
                formatted = f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
            else:
                formatted = (
                    f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
                )
            if formatted != text:
                cursor_pos = self.phone_entry.index("insert")
                self.phone_entry.delete(0, "end")
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
                existing_name = (device.get("client_name") or "").lower()
                if name in existing_name:
                    phone = device.get("phone", "")
                    status = device.get("client_status", "Новый")
                    if not self.phone_entry.get().strip() and phone:
                        self.phone_entry.delete(0, "end")
                        self.phone_entry.insert(0, phone)
                    if hasattr(self, "client_status_combo"):
                        self.client_status_combo.set(status)
                    break
        except Exception:
            pass

    def _on_device_type_changed(self, choice=None):
        """Связка тип устройства -> фильтрация брендов."""
        if not self.db or not hasattr(self, "brand_combo"):
            return
        try:
            device_type = self.device_type_combo.get()
            all_brands = self.db.get_dict_values("brands")
            type_brand_map = {
                "Смартфон": ["Apple", "Samsung", "Xiaomi", "Huawei", "Realme", "Honor"],
                "Планшет": ["Apple", "Samsung", "Lenovo", "Xiaomi"],
                "Ноутбук": ["Apple", "HP", "Dell", "Lenovo", "Asus", "Acer"],
                "ПК": ["HP", "Dell", "Lenovo", "Asus", "Acer", "MSI"],
                "Монитор": ["Samsung", "LG", "Asus", "Acer", "BenQ"],
            }
            relevant = type_brand_map.get(device_type, [])
            if relevant:
                other = [b for b in all_brands if b not in relevant]
                self.brand_combo.configure(values=relevant + other)
            else:
                self.brand_combo.configure(values=all_brands)
        except Exception:
            pass

    def create_widgets(self, device_data: dict[str, Any] | None):
        """Создание виджетов"""
        # Основной контейнер
        self.main_container = ctk.CTkFrame(self, fg_color=self.colors["bg_primary"])
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)

        # Заголовок
        title_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 15))

        icon_label = ctk.CTkLabel(
            title_frame,
            text="🔧" if self.is_new else "✏️",
            font=ctk.CTkFont(size=28),
            text_color=self.colors["accent"],
        )
        icon_label.pack(side="left", padx=(0, 10))

        # Заголовок с предпросмотром номера заказа
        if self.is_new:
            from utils.formatters import generate_order_number

            # Показываем следующий номер (без инкремента БД) — через facade,
            # а не через self.db.conn (которого нет у sqlalchemy_database.Database,
            # см. AUDIT_REPORT_v21.md)
            try:
                next_num = generate_order_number(self.db.peek_next_order_number())
            except Exception as e:
                logger.warning(f"Не удалось получить превью номера заказа: {e}")
                next_num = "???"
            title_text = f"Новый заказ  ·  №{next_num}"
        else:
            from utils.formatters import format_order_number_for_display as _fmt

            title_text = f"Редактирование заказа  ·  №{_fmt(device_data.get('order_number', '') if device_data else '')}"

        title_label = ctk.CTkLabel(
            title_frame,
            text=title_text,
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors["accent"],
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
                fg_color=self.colors["bg_tertiary"],
                text_color=self.colors["text_primary"],
                hover_color=self.colors["hover"],
                border_width=1,
                border_color=self.colors["border"],
                font=ctk.CTkFont(size=12),
            )
            receipt_btn.pack(side="right", padx=5)

            completion_btn = ctk.CTkButton(
                title_frame,
                text="🔧 Акт выполненных работ",
                command=self.show_completion_act_preview,
                height=35,
                width=180,
                corner_radius=6,
                fg_color=self.colors["bg_tertiary"],
                text_color=self.colors["text_primary"],
                hover_color=self.colors["hover"],
                border_width=1,
                border_color=self.colors["border"],
                font=ctk.CTkFont(size=12),
            )
            completion_btn.pack(side="right", padx=5)

        # --- Кнопки внизу (pack ПЕРВЫМ с side=bottom, до tabview) ---
        # Это гарантирует, что tabview(expand) не вытеснит кнопки за пределы.
        buttons_frame = ctk.CTkFrame(
            self.main_container, fg_color="transparent", height=50
        )
        buttons_frame.pack(fill="x", side="bottom", pady=(10, 5))
        buttons_frame.pack_propagate(False)

        # Создаем вкладки (pack последним — занимает остаток между top и bottom)
        self.tabview = ctk.CTkTabview(
            self.main_container, fg_color=self.colors["bg_primary"]
        )
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

        self.save_btn = ctk.CTkButton(
            buttons_frame,
            text="💾 Сохранить",
            command=self.save,
            height=38,
            width=140,
            corner_radius=8,
            fg_color=self.colors["accent"],
            text_color="white",
            hover_color=self.colors["accent_hover"],
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.save_btn.pack(side="right", padx=5)

        cancel_btn = ctk.CTkButton(
            buttons_frame,
            text="✖ Отмена",
            command=self.destroy,
            height=38,
            width=120,
            corner_radius=8,
            fg_color=self.colors["bg_tertiary"],
            text_color=self.colors["text_primary"],
            hover_color=self.colors["hover"],
            border_width=1,
            border_color=self.colors["border"],
            font=ctk.CTkFont(size=13),
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
            fg_color=self.colors["bg_tertiary"],
            text_color=self.colors["text_primary"],
            hover_color=self.colors["hover"],
            border_width=1,
            border_color=self.colors["border"],
            font=ctk.CTkFont(size=12),
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

        ctk.CTkLabel(
            dev_card,
            text="📱 Устройство",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(anchor="w", padx=12, pady=(8, 4))

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

        for i, (label_text, field_key) in enumerate(labels):
            ctk.CTkLabel(dev_frame, text=label_text, font=ctk.CTkFont(size=12)).grid(
                row=i, column=0, sticky="w", pady=3
            )

            if field_key in ("device_type", "brand", "appearance", "completeness"):
                dict_key = {
                    "device_type": "device_types",
                    "brand": "brands",
                    "appearance": "appearance",
                    "completeness": "completeness",
                }[field_key]
                values = self.db.get_dict_values(dict_key) if self.db else []
                combo = ctk.CTkComboBox(dev_frame, values=values, width=200, height=30)
                combo.set(device_data.get(field_key, "") if device_data else "")
                combo.grid(row=i, column=1, sticky="ew", padx=(8, 0), pady=3)
                setattr(self, f"{field_key}_combo", combo)
            elif field_key == "warranty":
                combo = ctk.CTkComboBox(
                    dev_frame, values=WARRANTIES, width=200, height=30
                )
                combo.set(device_data.get(field_key, "") if device_data else "")
                combo.grid(row=i, column=1, sticky="ew", padx=(8, 0), pady=3)
                setattr(self, f"{field_key}_combo", combo)
            else:
                entry = ctk.CTkEntry(
                    dev_frame,
                    width=200,
                    height=30,
                    fg_color=self.colors["bg_tertiary"],
                    border_color=self.colors["border"],
                )
                entry.insert(0, device_data.get(field_key, "") if device_data else "")
                entry.grid(row=i, column=1, sticky="ew", padx=(8, 0), pady=3)
                setattr(
                    self,
                    f"{field_key}_entry"
                    if field_key != "serial_number"
                    else "serial_entry",
                    entry,
                )

        # Неисправность
        ctk.CTkLabel(dev_frame, text="Неисправность:", font=ctk.CTkFont(size=12)).grid(
            row=len(labels), column=0, sticky="nw", pady=3
        )
        self.defect_text = ctk.CTkTextbox(
            dev_frame,
            height=60,
            width=200,
            fg_color=self.colors["bg_tertiary"],
            border_color=self.colors["border"],
            border_width=1,
            corner_radius=6,
        )
        self.defect_text.grid(
            row=len(labels), column=1, sticky="ew", padx=(8, 0), pady=3
        )
        if device_data:
            self.defect_text.insert("1.0", device_data.get("defect", ""))

        dev_frame.grid_columnconfigure(1, weight=1)

        # --- Правая колонка: клиент ---
        client_card = ModernCard(right_col, self.colors)
        client_card.pack(fill="both", expand=True)

        ctk.CTkLabel(
            client_card,
            text="👤 Клиент",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(anchor="w", padx=12, pady=(8, 4))

        client_frame = ctk.CTkFrame(client_card, fg_color="transparent")
        client_frame.pack(fill="x", padx=12, pady=(0, 8))

        # --- Подсветка обязательных полей ---
        required_color = self.colors.get("error", "#ff3b30")

        ctk.CTkLabel(
            client_frame,
            text="Имя клиента: *",
            font=ctk.CTkFont(size=12),
            text_color=required_color,
        ).grid(row=0, column=0, sticky="w", pady=3)
        self.client_name_entry = ctk.CTkEntry(
            client_frame,
            width=200,
            height=30,
            fg_color=self.colors["bg_tertiary"],
            border_color=self.colors["border"],
        )
        self.client_name_entry.insert(
            0, device_data.get("client_name", "") if device_data else ""
        )
        self.client_name_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=3)
        # Автозаполнение клиента
        self.client_name_entry.bind("<KeyRelease>", self._on_client_name_input)

        ctk.CTkLabel(
            client_frame,
            text="Телефон: *",
            font=ctk.CTkFont(size=12),
            text_color=required_color,
        ).grid(row=1, column=0, sticky="w", pady=3)
        self.phone_entry = ctk.CTkEntry(
            client_frame,
            width=200,
            height=30,
            fg_color=self.colors["bg_tertiary"],
            border_color=self.colors["border"],
        )
        phone_val = device_data.get("phone", "") if device_data else ""
        self.phone_entry.insert(0, phone_val)
        self.phone_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=3)
        # Маска телефона
        self.phone_entry.bind("<KeyRelease>", self._format_phone_input)

        ctk.CTkLabel(
            client_frame, text="Статус клиента:", font=ctk.CTkFont(size=12)
        ).grid(row=2, column=0, sticky="w", pady=3)
        client_statuses = (
            self.db.get_dict_values("client_statuses") if self.db else ["Новый"]
        )
        self.client_status_combo = ctk.CTkComboBox(
            client_frame, values=client_statuses, width=200, height=30
        )
        self.client_status_combo.set(
            device_data.get("client_status", "Новый") if device_data else "Новый"
        )
        self.client_status_combo.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=3)

        # Финансы
        ctk.CTkLabel(
            client_frame, text="Стоимость (₽):", font=ctk.CTkFont(size=12)
        ).grid(row=3, column=0, sticky="w", pady=3)
        self.total_price_entry = ctk.CTkEntry(
            client_frame,
            width=200,
            height=30,
            fg_color=self.colors["bg_tertiary"],
            border_color=self.colors["border"],
        )
        self.total_price_entry.insert(
            0, device_data.get("total_price", "") if device_data else ""
        )
        self.total_price_entry.grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=3)

        ctk.CTkLabel(
            client_frame, text="Предоплата (₽):", font=ctk.CTkFont(size=12)
        ).grid(row=4, column=0, sticky="w", pady=3)
        self.prepayment_entry = ctk.CTkEntry(
            client_frame,
            width=200,
            height=30,
            fg_color=self.colors["bg_tertiary"],
            border_color=self.colors["border"],
        )
        self.prepayment_entry.insert(
            0, device_data.get("prepayment", "") if device_data else ""
        )
        self.prepayment_entry.grid(row=4, column=1, sticky="ew", padx=(8, 0), pady=3)

        ctk.CTkLabel(
            client_frame, text="Статус заказа:", font=ctk.CTkFont(size=12)
        ).grid(row=5, column=0, sticky="w", pady=3)
        self.status_combo = ctk.CTkComboBox(
            client_frame, values=STATUSES, width=200, height=30
        )
        self.status_combo.set(
            device_data.get("status", "Диагностика") if device_data else "Диагностика"
        )
        self.status_combo.grid(row=5, column=1, sticky="ew", padx=(8, 0), pady=3)

        ctk.CTkLabel(client_frame, text="Приоритет:", font=ctk.CTkFont(size=12)).grid(
            row=6, column=0, sticky="w", pady=3
        )
        self.priority_combo = ctk.CTkComboBox(
            client_frame, values=PRIORITIES, width=200, height=30
        )
        self.priority_combo.set(
            device_data.get("priority", "Обычный") if device_data else "Обычный"
        )
        self.priority_combo.grid(row=6, column=1, sticky="ew", padx=(8, 0), pady=3)

        ctk.CTkLabel(client_frame, text="Инженер:", font=ctk.CTkFont(size=12)).grid(
            row=7, column=0, sticky="w", pady=3
        )
        engineers = self.db.get_dict_values("engineers") if self.db else []
        self.engineer_combo = ctk.CTkComboBox(
            client_frame, values=engineers, width=200, height=30
        )
        self.engineer_combo.set(device_data.get("engineer", "") if device_data else "")
        self.engineer_combo.grid(row=7, column=1, sticky="ew", padx=(8, 0), pady=3)

        # Заметки
        ctk.CTkLabel(client_frame, text="Заметки:", font=ctk.CTkFont(size=12)).grid(
            row=8, column=0, sticky="nw", pady=3
        )
        self.notes_text = ctk.CTkTextbox(
            client_frame,
            height=50,
            width=200,
            fg_color=self.colors["bg_tertiary"],
            border_color=self.colors["border"],
            border_width=1,
            corner_radius=6,
        )
        self.notes_text.grid(row=8, column=1, sticky="ew", padx=(8, 0), pady=3)
        if device_data:
            self.notes_text.insert("1.0", device_data.get("notes", ""))

        # Расход
        ctk.CTkLabel(client_frame, text="Расход (₽):", font=ctk.CTkFont(size=12)).grid(
            row=9, column=0, sticky="w", pady=3
        )
        self.expense_entry = ctk.CTkEntry(
            client_frame,
            width=200,
            height=30,
            fg_color=self.colors["bg_tertiary"],
            border_color=self.colors["border"],
        )
        self.expense_entry.insert(
            0, device_data.get("expense", "0") if device_data else "0"
        )
        self.expense_entry.grid(row=9, column=1, sticky="ew", padx=(8, 0), pady=3)

        client_frame.grid_columnconfigure(1, weight=1)

    def update_receipt_time(self):
        """Обновление даты и времени приема на текущие"""
        from tkinter import messagebox

        current_datetime = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        if hasattr(self, "receipt_datetime_label"):
            self.receipt_datetime_label.configure(text=current_datetime)
        messagebox.showinfo(
            "Успех", f"Дата и время приема обновлены на {current_datetime}"
        )

    def create_work_tab(self, parent, device_data):
        """Создание вкладки с работами"""
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10, pady=10)

        info_frame = ctk.CTkFrame(
            container, fg_color=self.colors["bg_secondary"], corner_radius=10
        )
        info_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            info_frame,
            text=f"Заказ №: {format_order_number_for_display(device_data.get('order_number', ''))}",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(anchor="w", padx=15, pady=10)

        work_frame = ctk.CTkFrame(
            container, fg_color=self.colors["bg_secondary"], corner_radius=10
        )
        work_frame.pack(fill="both", expand=True)

        ctk.CTkLabel(
            work_frame,
            text="🔨 ВЫПОЛНЕННЫЕ РАБОТЫ",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(anchor="w", padx=15, pady=(15, 10))

        self.work_table = WorkItemsTable(
            work_frame,
            self.colors,
            self.work_manager,
            on_total_changed=self.on_work_total_changed,
            db=self.db,
            settings=self.settings,
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
            fg_color=self.colors["accent"],
            text_color="white",
            hover_color=self.colors["accent_hover"],
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        add_btn.pack(side="left")

        self.photos_label = ctk.CTkLabel(
            btn_frame,
            text=f"📸 Фото: {len(self.current_photos)}",
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_secondary"],
        )
        self.photos_label.pack(side="left", padx=(15, 0))

        photos_frame = ctk.CTkFrame(
            container, fg_color=self.colors["bg_secondary"], corner_radius=10
        )
        photos_frame.pack(fill="both", expand=True)

        ctk.CTkLabel(
            photos_frame,
            text="СПИСОК ФОТОГРАФИЙ",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(anchor="w", padx=15, pady=(15, 10))

        scroll_frame = ctk.CTkScrollableFrame(
            photos_frame, fg_color="transparent", height=400
        )
        scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        self.thumbnails_container = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        self.thumbnails_container.pack(fill="x", padx=5, pady=5)

        self.update_photos_display()

    def create_history_tab(self, parent, device_data):
        """Создание вкладки с историей"""
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10, pady=10)

        stats = self.client_db.get_client_stats(
            device_data.get("client_name", ""), device_data.get("phone", "")
        )

        stats_frame = ctk.CTkFrame(
            container, fg_color=self.colors["bg_secondary"], corner_radius=10
        )
        stats_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            stats_frame,
            text="📊 СТАТИСТИКА КЛИЕНТА",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(anchor="w", padx=15, pady=(15, 10))

        stats_grid = ctk.CTkFrame(stats_frame, fg_color="transparent")
        stats_grid.pack(fill="x", padx=15, pady=(0, 15))

        ctk.CTkLabel(
            stats_grid,
            text=f"Всего ремонтов: {stats.get('total_orders', 0)}",
            font=ctk.CTkFont(size=12),
        ).grid(row=0, column=0, sticky="w", pady=5)
        ctk.CTkLabel(
            stats_grid,
            text=f"Завершено: {stats.get('completed_orders', 0)}",
            font=ctk.CTkFont(size=12),
        ).grid(row=0, column=1, sticky="w", pady=5, padx=(20, 0))
        ctk.CTkLabel(
            stats_grid,
            text=f"Общая сумма: {format_price(str(stats.get('total_spent', 0)))}",
            font=ctk.CTkFont(size=12),
        ).grid(row=1, column=0, sticky="w", pady=5)

        history_btn = ctk.CTkButton(
            container,
            text="📜 Открыть полную историю",
            command=lambda: ClientHistoryWindow(
                self,
                self.db,
                self.client_db,
                device_data.get("client_name", ""),
                device_data.get("phone", ""),
                device_data.get("client_status", "Новый"),
                self.colors,
                report_gen=self.report_gen,
                settings=self.settings,
                employees_api=self.employees_api,
                lock_api=self.lock_api,
            ),
            height=40,
            corner_radius=8,
            fg_color=self.colors["accent"],
            text_color="white",
            hover_color=self.colors["accent_hover"],
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        history_btn.pack(pady=20)

    def on_work_total_changed(self, total: float):
        """Обработка изменения общей суммы работ.

        Если добавлена хотя бы одна выполненная работа — автоматически меняем
        статус заказа на «Готов к выдаче» (если он ещё не выше по «лестнице»
        статусов: Готов/Выдан/Отказ не трогаем).
        """
        self.total_price_entry.delete(0, "end")
        self.total_price_entry.insert(0, str(int(total)))

        # Автосмена статуса при появлении выполненных работ
        try:
            if self.work_manager.items and hasattr(self, "status_combo"):
                current_status = self.status_combo.get().strip()
                # Не перезаписываем финальные статусы
                if current_status not in (STATUS_READY, *CLOSED_STATUSES):
                    self.status_combo.set(STATUS_READY)
        except Exception:
            pass
