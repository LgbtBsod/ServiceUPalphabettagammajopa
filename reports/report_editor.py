#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Визуальный редактор актов с поддержкой PDF, логотипов и QR-кодов.

Структура окна:
- Сверху — панель инструментов (Сохранить / Экспорт PDF / Печать / Закрыть).
- Ниже — вкладки: «📄 Акт приёма» и «🔧 Акт выполненных работ».
- В каждой вкладке — двухпанельный layout: слева настройки шаблона
  (логотип, цвет, поля, условия/гарантия), справа — визуальный предпросмотр
  PDF A5.
"""

import os
import logging

logger = logging.getLogger(__name__)

import json
import customtkinter as ctk
from tkinter import messagebox, filedialog, colorchooser
from datetime import datetime
import tempfile

# Абсолютные импорты
from gui.widgets.modern import ModernCard, ModernButton, ModernEntry, ModernLabel, ModernCombobox


# Метки полей документа
FIELD_LABELS = {
    'order_number': 'Номер заказа',
    'receipt_date': 'Дата приема',
    'completion_date': 'Дата выдачи',
    'client_name': 'ФИО клиента',
    'phone': 'Телефон',
    'device_type': 'Тип устройства',
    'brand': 'Бренд',
    'model': 'Модель',
    'serial_number': 'Серийный номер',
    'defect': 'Неисправность',
    'completeness': 'Комплектность',
    'appearance': 'Внешний вид',
    'completed_work': 'Выполненные работы',
    'total_price': 'Общая стоимость',
    'prepayment': 'Предоплата',
    'warranty': 'Гарантия',
    'engineer': 'Инженер',
    'client_status': 'Статус клиента',
}

# Шаблоны по умолчанию
_DEFAULT_TEMPLATES = {
    'receipt': {
        "name": "Акт приема оборудования в ремонт",
        "header_text": "АКТ ПРИЕМА ОБОРУДОВАНИЯ В РЕМОНТ",
        "footer_text": "Сервисный центр",
        "logo_path": "", "qr_path": "", "show_qr": False,
        "primary_color": "#0078d4",
        "fields": ["order_number", "receipt_date", "client_name", "phone",
                   "device_type", "brand", "model", "serial_number",
                   "completeness", "appearance", "defect",
                   "total_price", "prepayment"],
        "conditions": "1. Срок выполнения ремонта составляет от 3 до 14 рабочих дней\n"
                      "2. В случае необходимости замены комплектующих, стоимость согласовывается\n"
                      "3. Сервисный центр несет ответственность за сохранность оборудования\n"
                      "4. При отказе от ремонта диагностика оплачивается",
    },
    'completion': {
        "name": "Акт выполненных работ",
        "header_text": "АКТ ВЫПОЛНЕННЫХ РАБОТ",
        "footer_text": "Сервисный центр",
        "logo_path": "", "qr_path": "", "show_qr": False,
        "primary_color": "#0078d4",
        "fields": ["order_number", "receipt_date", "completion_date", "client_name", "phone",
                   "device_type", "brand", "model", "serial_number",
                   "completed_work", "total_price", "prepayment", "warranty"],
        "warranty_text": "1. Гарантия на выполненные работы составляет 30 дней\n"
                         "2. Гарантия не распространяется на механические повреждения\n"
                         "3. Претензии принимаются при наличии акта",
    },
}


def _templates_dir() -> str:
    """Каталог шаблонов рядом с этим модулем."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    tdir = os.path.join(current_dir, "templates")
    os.makedirs(tdir, exist_ok=True)
    return tdir


def load_template_data(act_type: str) -> dict:
    """Загружает шаблон акта из JSON или создаёт дефолтный."""
    filename = 'receipt_act.json' if act_type == 'receipt' else 'completion_act.json'
    path = os.path.join(_templates_dir(), filename)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка чтения шаблона {path}: {e}")
    data = dict(_DEFAULT_TEMPLATES[act_type])
    save_template_data(act_type, data)
    return data


def save_template_data(act_type: str, data: dict) -> bool:
    """Сохраняет шаблон акта в JSON."""
    filename = 'receipt_act.json' if act_type == 'receipt' else 'completion_act.json'
    path = os.path.join(_templates_dir(), filename)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения шаблона {path}: {e}")
        return False


# ===========================================================================
# Панель одного акта (настройки слева + предпросмотр справа)
# ===========================================================================

class ActPanel:
    """Содержит состояние и виджеты настроек одного типа акта."""

    def __init__(self, master_tab, editor, act_type: str):
        self.editor = editor
        self.colors = editor.colors
        self.act_type = act_type
        self.template_data = load_template_data(act_type)
        self.logo_path = self.template_data.get("logo_path", "")
        self.qr_path = self.template_data.get("qr_path", "")
        self._preview_image = None
        self._preview_pdf = None

        # Левая часть: настройки (фиксированная ширина, прокручивается по вертикали)
        self.left_scroll = ctk.CTkScrollableFrame(
            master_tab, fg_color="transparent", width=420,
            label_anchor="w"
        )
        self.left_scroll.pack(side="left", fill="y", expand=False, padx=(0, 5))

        # Правая часть: предпросмотр
        self.right_frame = ModernCard(master_tab, self.colors)
        self.right_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))

        self._build_settings()
        self._build_preview()

    # ------------------------------------------------------------------
    # Сборка настроек (левая панель)
    # ------------------------------------------------------------------

    def _build_settings(self):
        parent = self.left_scroll

        # --- Логотип и QR ---
        logo_card = ModernCard(parent, self.colors)
        logo_card.pack(fill="x", pady=5)
        ctk.CTkLabel(logo_card, text="🏢 Логотип и QR-код",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=12, pady=(8, 4))

        logo_frame = ctk.CTkFrame(logo_card, fg_color="transparent")
        logo_frame.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkLabel(logo_frame, text="Логотип:").grid(row=0, column=0, sticky="w", pady=4)
        self.logo_label = ctk.CTkLabel(logo_frame, text=os.path.basename(self.logo_path) if self.logo_path else "Не выбран",
                                       width=160, anchor="w")
        self.logo_label.grid(row=0, column=1, sticky="w", padx=(8, 0), pady=4)
        ModernButton(logo_frame, self.colors, variant="secondary", text="Выбрать",
                     command=self.select_logo, width=80).grid(row=0, column=2, padx=(8, 0), pady=4)
        ModernButton(logo_frame, self.colors, variant="secondary", text="Очистить",
                     command=self.clear_logo, width=70).grid(row=0, column=3, padx=(4, 0), pady=4)

        ctk.CTkLabel(logo_frame, text="QR-код:").grid(row=1, column=0, sticky="w", pady=4)
        self.qr_label = ctk.CTkLabel(logo_frame, text=os.path.basename(self.qr_path) if self.qr_path else "Не выбран",
                                     width=160, anchor="w")
        self.qr_label.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=4)
        ModernButton(logo_frame, self.colors, variant="secondary", text="Выбрать",
                     command=self.select_qr, width=80).grid(row=1, column=2, padx=(8, 0), pady=4)
        ModernButton(logo_frame, self.colors, variant="secondary", text="Очистить",
                     command=self.clear_qr, width=70).grid(row=1, column=3, padx=(4, 0), pady=4)

        self.show_qr_var = ctk.BooleanVar(value=self.template_data.get("show_qr", False))
        ctk.CTkCheckBox(logo_frame, text="Показывать QR-код", variable=self.show_qr_var,
                        fg_color=self.colors['accent'],
                        command=self.update_preview).grid(row=2, column=0, columnspan=2, sticky="w", pady=4)

        # Размер логотипа (ползунок)
        ctk.CTkLabel(logo_frame, text="Размер логотипа:").grid(row=3, column=0, sticky="w", pady=4)
        logo_size_frame = ctk.CTkFrame(logo_frame, fg_color="transparent")
        logo_size_frame.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=4)
        self.logo_size_slider = ctk.CTkSlider(logo_size_frame, from_=30, to=100,
                                              number_of_steps=14,
                                              command=self._on_logo_size_changed)
        self.logo_size_slider.set(self.template_data.get("logo_size", 50))
        self.logo_size_slider.pack(side="left", fill="x", expand=True)
        self.logo_size_label = ctk.CTkLabel(logo_size_frame, text=f"{int(self.logo_size_slider.get())}pt",
                                            width=40, font=ctk.CTkFont(size=11))
        self.logo_size_label.pack(side="left", padx=(6, 0))

        # Позиция логотипа
        ctk.CTkLabel(logo_frame, text="Позиция логотипа:").grid(row=4, column=0, sticky="w", pady=4)
        self.logo_pos_combo = ctk.CTkComboBox(logo_frame,
                                              values=["По центру", "Слева", "Справа"],
                                              width=120, height=28,
                                              command=lambda _: self.update_preview())
        self.logo_pos_combo.set(self.template_data.get("logo_position", "По центру"))
        self.logo_pos_combo.grid(row=4, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=4)

        logo_frame.grid_columnconfigure(1, weight=1)

        # --- Основные настройки ---
        settings_card = ModernCard(parent, self.colors)
        settings_card.pack(fill="x", pady=5)
        ctk.CTkLabel(settings_card, text="📄 Основные настройки",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=12, pady=(8, 4))

        sf = ctk.CTkFrame(settings_card, fg_color="transparent")
        sf.pack(fill="x", padx=12, pady=(0, 8))

        # Debounce-таймер инициализируем заранее
        self._preview_timer = None

        row = 0
        ctk.CTkLabel(sf, text="Название:").grid(row=row, column=0, sticky="w", pady=3)
        self.name_entry = ctk.CTkEntry(sf)
        self.name_entry.insert(0, self.template_data.get("name", ""))
        self.name_entry.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        self.name_entry.bind("<KeyRelease>", self._schedule_preview_update)

        row += 1
        ctk.CTkLabel(sf, text="Заголовок:").grid(row=row, column=0, sticky="w", pady=3)
        self.header_entry = ctk.CTkEntry(sf)
        self.header_entry.insert(0, self.template_data.get("header_text", ""))
        self.header_entry.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        self.header_entry.bind("<KeyRelease>", self._schedule_preview_update)

        row += 1
        ctk.CTkLabel(sf, text="Адрес:").grid(row=row, column=0, sticky="w", pady=3)
        self.footer_entry = ctk.CTkEntry(sf)
        self.footer_entry.insert(0, self.template_data.get("footer_text", ""))
        self.footer_entry.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        self.footer_entry.bind("<KeyRelease>", self._schedule_preview_update)

        row += 1
        ctk.CTkLabel(sf, text="Телефон:").grid(row=row, column=0, sticky="w", pady=3)
        self.phone_entry = ctk.CTkEntry(sf)
        self.phone_entry.insert(0, self.template_data.get("company_phone", ""))
        self.phone_entry.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        self.phone_entry.bind("<KeyRelease>", self._schedule_preview_update)

        row += 1
        ctk.CTkLabel(sf, text="График:").grid(row=row, column=0, sticky="w", pady=3)
        self.schedule_entry = ctk.CTkEntry(sf)
        self.schedule_entry.insert(0, self.template_data.get("company_schedule", ""))
        self.schedule_entry.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        self.schedule_entry.bind("<KeyRelease>", self._schedule_preview_update)

        # --- Палитра быстрых цветов ---
        row += 1
        ctk.CTkLabel(sf, text="Цвет акцента:").grid(row=row, column=0, sticky="w", pady=(6, 3))
        color_frame = ctk.CTkFrame(sf, fg_color="transparent")
        color_frame.grid(row=row, column=1, sticky="w", padx=(8, 0), pady=(6, 3))

        current_color = self.template_data.get("primary_color", "#0078d4")
        self.color_preview = ctk.CTkFrame(color_frame, width=28, height=22, corner_radius=4,
                                          fg_color=current_color)
        self.color_preview.pack(side="left", padx=(0, 6))

        # Палитра пресетов
        palette = [
            ("#007aff", "iOS"), ("#34c759", "Зелёный"), ("#ff3b30", "Красный"),
            ("#ff9f0a", "Оранж."), ("#5856d6", "Фиолет."), ("#000000", "Чёрный"),
        ]
        self._color_buttons = []
        for hex_c, _label in palette:
            btn = ctk.CTkButton(color_frame, text="", width=24, height=22, corner_radius=4,
                                fg_color=hex_c, hover_color=hex_c, border_width=2,
                                border_color=("#ffffff" if hex_c != current_color else self.colors['accent']),
                                command=lambda c=hex_c: self._apply_quick_color(c))
            btn.pack(side="left", padx=2)
            self._color_buttons.append((btn, hex_c))

        # Кнопка кастомного цвета (colorchooser)
        ModernButton(color_frame, self.colors, variant="secondary", text="🎨",
                     command=self.choose_color, width=34, height=22).pack(side="left", padx=(4, 0))

        sf.grid_columnconfigure(1, weight=1)

        # --- Шрифт и поля страницы ---
        row += 1
        ctk.CTkLabel(sf, text="Шрифт:").grid(row=row, column=0, sticky="w", pady=(6, 3))
        self.font_combo = ctk.CTkComboBox(sf,
            values=["Trebuchet MS", "Arial", "Times New Roman", "Helvetica"],
            width=140, height=28,
            command=lambda _: self._schedule_preview_update())
        current_font = self.template_data.get("font_name", "Trebuchet MS")
        self.font_combo.set(current_font if current_font in ["Trebuchet MS", "Arial", "Times New Roman", "Helvetica"] else "Trebuchet MS")
        self.font_combo.grid(row=row, column=1, sticky="w", padx=(8, 0), pady=(6, 3))

        row += 1
        ctk.CTkLabel(sf, text="Поля (мм):").grid(row=row, column=0, sticky="w", pady=3)
        self.margins_combo = ctk.CTkComboBox(sf,
            values=["6", "8", "10", "12", "15"],
            width=60, height=28,
            command=lambda _: self._schedule_preview_update())
        self.margins_combo.set(str(self.template_data.get("page_margin_mm", 6)))
        self.margins_combo.grid(row=row, column=1, sticky="w", padx=(8, 0), pady=3)

        # --- Поля документа с Drag-and-Drop ---
        fields_card = ModernCard(parent, self.colors)
        fields_card.pack(fill="x", pady=5)
        ctk.CTkLabel(fields_card, text="📋 Поля документа (перетаскивайте для изменения порядка)",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=12, pady=(8, 4))

        ff = ctk.CTkFrame(fields_card, fg_color="transparent")
        ff.pack(fill="x", padx=12, pady=(0, 8))

        current_fields = self.template_data.get("fields", [])
        self.field_vars = {}
        self.field_widgets = {}  # key -> (frame, checkbox, label, gripper)
        
        # Контейнер для drag-and-drop элементов
        self.fields_container = ctk.CTkScrollableFrame(ff, fg_color="transparent", height=280)
        self.fields_container.pack(fill="both", expand=True)
        
        # Создаём элементы списка полей
        for idx, field_key in enumerate(current_fields):
            self._create_field_item(field_key, idx)
        
        # Кнопка добавления поля
        add_frame = ctk.CTkFrame(ff, fg_color="transparent")
        add_frame.pack(fill="x", pady=(8, 0))
        
        ctk.CTkLabel(add_frame, text="Добавить поле:", 
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 8))
        
        self.add_field_combo = ctk.CTkComboBox(
            add_frame,
            values=[FIELD_LABELS[k] for k in FIELD_LABELS.keys() if k not in current_fields],
            width=200, height=28
        )
        self.add_field_combo.pack(side="left", padx=(0, 8))
        
        ModernButton(add_frame, self.colors, variant="secondary", text="+ Добавить",
                     command=self._add_field, width=100).pack(side="left")
        
        # Инструкция
        hint_label = ctk.CTkLabel(
            ff, text="💡 Перетаскивайте поля за ⋮⋮ для изменения порядка",
            font=ctk.CTkFont(size=10), text_color=self.colors['text_secondary']
        )
        hint_label.pack(pady=(4, 0))

        # --- Дополнительный текст ---
        text_card = ModernCard(parent, self.colors)
        text_card.pack(fill="x", pady=5)
        if self.act_type == "receipt":
            ctk.CTkLabel(text_card, text="📜 Условия ремонта",
                         font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=12, pady=(8, 4))
            self.conditions_text = ctk.CTkTextbox(text_card, height=110, fg_color=self.colors['bg_tertiary'])
            self.conditions_text.pack(fill="x", padx=12, pady=(0, 8))
            self.conditions_text.insert("1.0", self.template_data.get("conditions", ""))
            self.conditions_text.bind("<KeyRelease>", self._schedule_preview_update)
        else:
            ctk.CTkLabel(text_card, text="📜 Гарантийные обязательства",
                         font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=12, pady=(8, 4))
            self.warranty_text = ctk.CTkTextbox(text_card, height=110, fg_color=self.colors['bg_tertiary'])
            self.warranty_text.pack(fill="x", padx=12, pady=(0, 8))
            self.warranty_text.insert("1.0", self.template_data.get("warranty_text", ""))
            self.warranty_text.bind("<KeyRelease>", self._schedule_preview_update)

        # --- Кнопки внизу настроек: Обновить + Сбросить ---
        actions_frame = ctk.CTkFrame(parent, fg_color="transparent")
        actions_frame.pack(fill="x", pady=(8, 0))
        ModernButton(actions_frame, self.colors, variant="secondary",
                     text="🔄 Обновить предпросмотр",
                     command=self.update_preview, height=30).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ModernButton(actions_frame, self.colors, variant="danger",
                     text="♻ Сбросить",
                     command=self.reset_to_defaults, height=30, width=100).pack(side="right", padx=(4, 0))

    # ------------------------------------------------------------------
    # Предпросмотр (правая панель)
    # ------------------------------------------------------------------

    def _build_preview(self):
        # Шапка правой панели: заголовок + кнопка обновления
        preview_header = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        preview_header.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(preview_header, text="👁️ Предпросмотр акта (PDF A5)",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")

        ModernButton(preview_header, self.colors, variant="secondary",
                     text="🔄 Обновить", command=self.update_preview,
                     width=130, height=30).pack(side="right")

        self.preview_container = ctk.CTkScrollableFrame(
            self.right_frame, fg_color=self.colors['bg_tertiary']
        )
        self.preview_container.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.preview_label = ctk.CTkLabel(
            self.preview_container, text="⏳ Нажмите «🔄 Обновить»",
            font=ctk.CTkFont(size=12), text_color=self.colors['text_secondary']
        )
        self.preview_label.pack(expand=True, pady=40)

    # ------------------------------------------------------------------
    # Drag-and-Drop логика для полей
    # ------------------------------------------------------------------

    def _create_field_item(self, field_key: str, index: int):
        """Создаёт элемент списка поля с поддержкой drag-and-drop."""
        frame = ctk.CTkFrame(self.fields_container, fg_color=self.colors['bg_secondary'], height=32)
        frame.pack(fill="x", pady=1, padx=2)
        frame.pack_propagate(False)
        
        # Gripper (ручка для перетаскивания)
        gripper = ctk.CTkLabel(
            frame, text="⋮⋮", font=ctk.CTkFont(size=14),
            text_color=self.colors['text_secondary'],
            cursor="hand2"
        )
        gripper.pack(side="left", padx=(4, 0))
        
        # Checkbox
        var = ctk.BooleanVar(value=True)
        self.field_vars[field_key] = var
        checkbox = ctk.CTkCheckBox(
            frame, text="", variable=var,
            fg_color=self.colors['accent'], width=20,
            command=lambda: self.after(10, self.update_preview)
        )
        checkbox.pack(side="left", padx=(4, 0))
        
        # Label с названием поля
        label = ctk.CTkLabel(
            frame, text=FIELD_LABELS.get(field_key, field_key),
            font=ctk.CTkFont(size=11), anchor="w"
        )
        label.pack(side="left", fill="x", expand=True, padx=(6, 0))
        
        # Кнопка удаления
        del_btn = ctk.CTkLabel(
            frame, text="✖", font=ctk.CTkFont(size=12),
            text_color=self.colors['error'], cursor="hand2"
        )
        del_btn.pack(side="right", padx=(0, 4))
        del_btn.bind("<Button-1>", lambda e, k=field_key: self._remove_field(k))
        
        # Сохраняем ссылки на виджеты
        self.field_widgets[field_key] = {
            'frame': frame,
            'checkbox': checkbox,
            'label': label,
            'gripper': gripper,
            'var': var
        }
        
        # Привязываем события drag-and-drop к gripper и frame
        self._bind_drag_events(frame, gripper, field_key)

    def _bind_drag_events(self, frame, gripper, field_key):
        """Привязывает события мыши для drag-and-drop."""
        # Храним данные о перетаскивании в атрибутах frame
        frame.drag_data = {'item': field_key, 'y': 0}
        
        gripper.bind("<ButtonPress-1>", lambda e: self._on_drag_start(e, frame, field_key))
        gripper.bind("<B1-Motion>", lambda e: self._on_drag_motion(e, frame))
        gripper.bind("<ButtonRelease-1>", lambda e: self._on_drag_drop(e, frame))
        
        # Также привязываем к самому frame для удобства
        frame.bind("<ButtonPress-1>", lambda e: self._on_drag_start(e, frame, field_key))
        frame.bind("<B1-Motion>", lambda e: self._on_drag_motion(e, frame))
        frame.bind("<ButtonRelease-1>", lambda e: self._on_drag_drop(e, frame))

    def _on_drag_start(self, event, frame, field_key):
        """Начало перетаскивания."""
        frame.drag_data['item'] = field_key
        frame.drag_data['y'] = event.y_root
        frame.configure(fg_color=self.colors['accent'])

    def _on_drag_motion(self, event, frame):
        """Перемещение во время перетаскивания."""
        delta = event.y_root - frame.drag_data['y']
        frame.drag_data['y'] = event.y_root
        
        # Находим текущий индекс элемента
        current_items = self._get_field_order()
        try:
            idx = current_items.index(frame.drag_data['item'])
        except ValueError:
            return
        
        # Определяем направление перемещения
        if delta > 20:  # Движение вниз
            if idx < len(current_items) - 1:
                self._swap_fields(idx, idx + 1)
                frame.drag_data['y'] = event.y_root
        elif delta < -20:  # Движение вверх
            if idx > 0:
                self._swap_fields(idx, idx - 1)
                frame.drag_data['y'] = event.y_root

    def _on_drag_drop(self, event, frame):
        """Завершение перетаскивания."""
        frame.configure(fg_color=self.colors['bg_secondary'])
        self.update_preview()

    def _get_field_order(self):
        """Возвращает текущий порядок полей из UI."""
        order = []
        for widget in self.fields_container.winfo_children():
            for key, widgets in self.field_widgets.items():
                if widgets['frame'] == widget:
                    order.append(key)
                    break
        return order

    def _swap_fields(self, idx1, idx2):
        """Меняет местами два поля в списке."""
        order = self._get_field_order()
        if idx1 < len(order) and idx2 < len(order):
            order[idx1], order[idx2] = order[idx2], order[idx1]
            self._rebuild_field_list(order)

    def _rebuild_field_list(self, new_order):
        """Перестраивает список полей в новом порядке."""
        # Сохраняем состояния checkbox
        states = {k: self.field_vars[k].get() for k in self.field_widgets}
        
        # Удаляем все виджеты
        for widget in self.fields_container.winfo_children():
            widget.destroy()
        self.field_widgets.clear()
        
        # Пересоздаём в новом порядке
        for idx, field_key in enumerate(new_order):
            self._create_field_item(field_key, idx)
            # Восстанавливаем состояние checkbox
            if field_key in self.field_vars:
                self.field_vars[field_key].set(states.get(field_key, True))
        
        # Обновляем template_data
        self.template_data['fields'] = new_order

    def _add_field(self):
        """Добавляет выбранное поле в список."""
        selected_label = self.add_field_combo.get()
        if not selected_label or selected_label == "—":
            return
        
        # Находим ключ поля по метке
        field_key = None
        for k, v in FIELD_LABELS.items():
            if v == selected_label:
                field_key = k
                break
        
        if field_key is None or field_key in self.field_widgets:
            return
        
        # Добавляем поле в конец списка
        current_order = self._get_field_order()
        current_order.append(field_key)
        self._rebuild_field_list(current_order)
        
        # Обновляем combobox
        self._update_add_field_combo()
        self.update_preview()

    def _remove_field(self, field_key):
        """Удаляет поле из списка."""
        if field_key not in self.field_widgets:
            return
        
        current_order = self._get_field_order()
        if field_key in current_order:
            current_order.remove(field_key)
            self._rebuild_field_list(current_order)
        
        # Обновляем combobox
        self._update_add_field_combo()
        self.update_preview()

    def _update_add_field_combo(self):
        """Обновляет список доступных для добавления полей."""
        current_fields = set(self._get_field_order())
        available = [FIELD_LABELS[k] for k in FIELD_LABELS.keys() if k not in current_fields]
        self.add_field_combo.configure(values=available)
        if available:
            self.add_field_combo.set(available[0] if available else "—")
        else:
            self.add_field_combo.set("—")

    # ------------------------------------------------------------------
    # Действия с логотипом/QR
    # ------------------------------------------------------------------

    def select_logo(self):
        path = filedialog.askopenfilename(
            title="Выберите логотип",
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.gif *.bmp *.webp")]
        )
        if path:
            self.logo_path = path
            self.logo_label.configure(text=os.path.basename(path))
            self.update_preview()

    def clear_logo(self):
        self.logo_path = ""
        self.logo_label.configure(text="Не выбран")
        self.update_preview()

    def select_qr(self):
        path = filedialog.askopenfilename(
            title="Выберите QR-код",
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.gif *.bmp *.webp")]
        )
        if path:
            self.qr_path = path
            self.qr_label.configure(text=os.path.basename(path))
            self.update_preview()

    def clear_qr(self):
        self.qr_path = ""
        self.qr_label.configure(text="Не выбран")
        self.update_preview()

    def choose_color(self):
        color = colorchooser.askcolor(
            title="Выберите основной цвет",
            initialcolor=self.template_data.get("primary_color", "#0078d4"))
        if color and color[1]:
            self.template_data["primary_color"] = color[1]
            self.color_preview.configure(fg_color=color[1])
            self.update_preview()

    # ------------------------------------------------------------------
    # Синхронизация UI -> template_data
    # ------------------------------------------------------------------

    def sync_template_from_ui(self):
        """Собирает self.template_data из полей редактора (без записи в файл)."""
        self.template_data["name"] = self.name_entry.get()
        self.template_data["header_text"] = self.header_entry.get()
        self.template_data["footer_text"] = self.footer_entry.get()
        self.template_data["company_phone"] = self.phone_entry.get()
        self.template_data["company_schedule"] = self.schedule_entry.get()
        self.template_data["show_qr"] = self.show_qr_var.get()
        self.template_data["logo_path"] = self.logo_path
        self.template_data["qr_path"] = self.qr_path
        # Размер и позиция логотипа
        if hasattr(self, 'logo_size_slider'):
            self.template_data["logo_size"] = int(self.logo_size_slider.get())
        if hasattr(self, 'logo_pos_combo'):
            self.template_data["logo_position"] = self.logo_pos_combo.get()
        # Шрифт и поля страницы
        if hasattr(self, 'font_combo'):
            self.template_data["font_name"] = self.font_combo.get()
        if hasattr(self, 'margins_combo'):
            try:
                self.template_data["page_margin_mm"] = int(self.margins_combo.get())
            except (ValueError, TypeError):
                self.template_data["page_margin_mm"] = 6
        # Поля документа с учётом порядка из Drag-and-Drop
        if hasattr(self, '_get_field_order') and hasattr(self, 'field_widgets') and self.field_widgets:
            # Используем порядок из UI + фильтр по checkbox
            ordered_fields = self._get_field_order()
            self.template_data["fields"] = [k for k in ordered_fields if k in self.field_vars and self.field_vars[k].get()]
        else:
            # Fallback для старого кода
            self.template_data["fields"] = [k for k, v in self.field_vars.items() if v.get()]
        if self.act_type == "receipt":
            self.template_data["conditions"] = self.conditions_text.get("1.0", "end-1c").strip()
        else:
            self.template_data["warranty_text"] = self.warranty_text.get("1.0", "end-1c").strip()

    def _apply_quick_color(self, hex_color: str):
        """Применяет выбранный цвет из палитры пресетов."""
        self.template_data["primary_color"] = hex_color
        self.color_preview.configure(fg_color=hex_color)
        # Обновляем выделение в палитре
        for btn, h in self._color_buttons:
            btn.configure(border_color=(self.colors['accent'] if h == hex_color else "#ffffff"))
        self.update_preview()

    def _on_logo_size_changed(self, value):
        """Обновляет метку размера логотипа и предпросмотр (с debounce)."""
        self.logo_size_label.configure(text=f"{int(value)}pt")
        self._schedule_preview_update()

    def reset_to_defaults(self):
        """Сбрасывает настройки текущего акта к стандартным."""
        from tkinter import messagebox
        if not messagebox.askyesno("Сброс", f"Сбросить настройки акта к стандартным?\n"
                                             f"Текущие изменения будут потеряны."):
            return
        # Загружаем дефолт
        defaults = dict(_DEFAULT_TEMPLATES[self.act_type])
        self.template_data = defaults
        self.logo_path = defaults.get("logo_path", "")
        self.qr_path = defaults.get("qr_path", "")
        # Сохраняем дефолт и перезагружаем UI
        save_template_data(self.act_type, self.template_data)
        # Перезагружаем все поля
        self._reload_ui()
        messagebox.showinfo("Готово", "Настройки сброшены к стандартным.")

    def _reload_ui(self):
        """Перезагружает все поля UI из self.template_data (после сброса)."""
        # Текстовые поля
        self.name_entry.delete(0, 'end')
        self.name_entry.insert(0, self.template_data.get("name", ""))
        self.header_entry.delete(0, 'end')
        self.header_entry.insert(0, self.template_data.get("header_text", ""))
        self.footer_entry.delete(0, 'end')
        self.footer_entry.insert(0, self.template_data.get("footer_text", ""))
        self.phone_entry.delete(0, 'end')
        self.phone_entry.insert(0, self.template_data.get("company_phone", ""))
        self.schedule_entry.delete(0, 'end')
        self.schedule_entry.insert(0, self.template_data.get("company_schedule", ""))
        # Цвет
        color = self.template_data.get("primary_color", "#0078d4")
        self.template_data["primary_color"] = color
        self.color_preview.configure(fg_color=color)
        for btn, h in self._color_buttons:
            btn.configure(border_color=(self.colors['accent'] if h == color else "#ffffff"))
        # Логотип
        self.logo_label.configure(text=os.path.basename(self.logo_path) if self.logo_path else "Не выбран")
        self.qr_label.configure(text=os.path.basename(self.qr_path) if self.qr_path else "Не выбран")
        self.show_qr_var.set(self.template_data.get("show_qr", False))
        self.logo_size_slider.set(self.template_data.get("logo_size", 50))
        self.logo_size_label.configure(text=f"{int(self.logo_size_slider.get())}pt")
        self.logo_pos_combo.set(self.template_data.get("logo_position", "По центру"))
        # Шрифт и поля страницы
        if hasattr(self, 'font_combo'):
            fn = self.template_data.get("font_name", "Trebuchet MS")
            self.font_combo.set(fn)
        if hasattr(self, 'margins_combo'):
            self.margins_combo.set(str(self.template_data.get("page_margin_mm", 6)))
        # Поля документа
        current_fields = self.template_data.get("fields", [])
        for field_key, var in self.field_vars.items():
            var.set(field_key in current_fields)
        # Условия/гарантия
        if self.act_type == "receipt":
            self.conditions_text.delete("1.0", "end")
            self.conditions_text.insert("1.0", self.template_data.get("conditions", ""))
        else:
            self.warranty_text.delete("1.0", "end")
            self.warranty_text.insert("1.0", self.template_data.get("warranty_text", ""))
        self.update_preview()

    def save_template(self) -> bool:
        """Сохраняет текущие настройки в JSON-файл шаблона."""
        self.sync_template_from_ui()
        return save_template_data(self.act_type, self.template_data)

    # ------------------------------------------------------------------
    # Предпросмотр
    # ------------------------------------------------------------------

    def _schedule_preview_update(self, _event=None):
        """Debounce-обновление предпросмотра (600мс после последнего нажатия).

        Предотвращает генерацию PDF на каждый символ при вводе текста.
        """
        try:
            if self._preview_timer is not None:
                self.editor.after_cancel(self._preview_timer)
        except Exception:
            pass
        self._preview_timer = self.editor.after(600, self.update_preview)

    def update_preview(self):
        """Рендерит реальный PDF A5 и показывает его как изображение."""
        self.sync_template_from_ui()
        try:
            from reports.report_renderer import ActPDFGenerator

            # Очищаем старое содержимое
            for w in self.preview_container.winfo_children():
                w.destroy()

            gen = ActPDFGenerator(template_data=self.template_data)
            device = self._build_demo_device()

            # Временный PDF
            self._cleanup_preview_pdf()
            fd, self._preview_pdf = tempfile.mkstemp(
                suffix=f"_{self.act_type}.pdf", prefix="editor_preview_")
            os.close(fd)

            if self.act_type == "completion":
                ok = gen.generate_completion_pdf(self._preview_pdf, device)
            else:
                ok = gen.generate_receipt_pdf(self._preview_pdf, device)

            if not ok or not os.path.exists(self._preview_pdf):
                self._show_preview_error("Не удалось сформировать PDF")
                return

            # Рендер PDF -> изображение
            try:
                import pypdfium2 as pdfium
                pdf = pdfium.PdfDocument(self._preview_pdf)
                if len(pdf) == 0:
                    raise RuntimeError("PDF без страниц")
                page = pdf[0]
                self.preview_container.update_idletasks()
                avail_w = max(self.preview_container.winfo_width() - 20, 280)
                avail_h = max(self.preview_container.winfo_height() - 20, 400)
                # A5: 148×210 мм = 419.5×595.3 pt. Подгоняем по ОБЕИМ измерениям,
                # чтобы вся страница была видна целиком как миниатюра.
                pt_w = 148 * 2.83465
                pt_h = 210 * 2.83465
                scale_w = avail_w / pt_w
                scale_h = avail_h / pt_h
                # Берём меньший масштаб — страница гарантированно помещается
                scale = max(0.8, min(scale_w, scale_h))
                pil_img = page.render(scale=scale).to_pil()

                ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img,
                                       size=(pil_img.size[0], pil_img.size[1]))
                self._preview_image = ctk_img
                self.preview_label = ctk.CTkLabel(self.preview_container, image=ctk_img, text="")
                self.preview_label.pack(expand=True, padx=4, pady=4)
            except Exception as render_err:
                logger.warning(f"Рендер PDF недоступен ({render_err})")
                self._render_text_fallback()
        except Exception as e:
            logger.error(f"Ошибка предпросмотра: {e}")
            self._show_preview_error(str(e))

    def _show_preview_error(self, msg: str):
        for w in self.preview_container.winfo_children():
            w.destroy()
        self.preview_label = ctk.CTkLabel(
            self.preview_container, text=f"❌ {msg}",
            font=ctk.CTkFont(size=12), text_color=self.colors['error']
        )
        self.preview_label.pack(expand=True, pady=40)

    def _render_text_fallback(self):
        """Текстовый предпросмотр (если pypdfium2 недоступен)."""
        header = self.template_data.get("header_text", "АКТ")
        footer = self.template_data.get("footer_text", "")
        fields = [k for k, v in self.field_vars.items() if v.get()]
        lines = ["╔" + "═" * 58 + "╗", f"║{header.center(58)}║",
                 "╠" + "═" * 58 + "╣", ""]
        for f in fields:
            lines.append(f"  {FIELD_LABELS.get(f, f)}: [значение]")
        lines += ["", "╠" + "═" * 58 + "╣", f"║{footer.center(58)}║", "╚" + "═" * 58 + "╝"]
        self.preview_label = ctk.CTkTextbox(
            self.preview_container, wrap="word",
            font=ctk.CTkFont(family="Courier", size=11),
            fg_color=self.colors['bg_tertiary'],
            text_color=self.colors['text_primary'], border_width=0, height=380
        )
        self.preview_label.pack(fill="both", expand=True, padx=4, pady=4)
        self.preview_label.insert("1.0", "\n".join(lines))
        self.preview_label.configure(state="disabled")

    def _build_demo_device(self) -> dict:
        """Демо-данные заказа для рендера предпросмотра в редакторе.

        Заполняет примеры значений, чтобы все блоки акта (включая спецблоки
        «Неисправность», «Стоимость») были видны в предпросмотре — как при
        печати реального заказа.
        """
        fields = self.template_data.get("fields", [])
        device = {f: "" for f in fields}
        today = datetime.now().strftime('%Y-%m-%d')
        # Демо-значения для наглядности предпросмотра
        demo_values = {
            "order_number": "00001",
            "receipt_date": today,
            "completion_date": today,
            "client_name": "Иванов Иван Иванович",
            "phone": "+7 (999) 123-45-67",
            "device_type": "Ноутбук",
            "brand": "Apple",
            "model": "MacBook Pro",
            "serial_number": "C02XK1234ABC",
            "completeness": "Полная комплектация",
            "appearance": "Отличное состояние",
            "defect": "Не включается, нет изображения на экране",
            "completed_work": "Замена дисплея, профилактика",
            "total_price": "8500",
            "prepayment": "2000",
            "warranty": "3 месяца",
            "engineer": "Иванов И.И.",
            "client_status": "Постоянный",
        }
        for f in fields:
            if f in demo_values:
                device[f] = demo_values[f]
        return device

    def _build_company_info(self) -> dict:
        return {
            'name': self.template_data.get("name", "Сервисный центр"),
            'address': self.template_data.get("footer_text", ""),
            'phone': self.template_data.get("company_phone", ""),
            'schedule': self.template_data.get("company_schedule", ""),
        }

    def _cleanup_preview_pdf(self):
        if self._preview_pdf and os.path.exists(self._preview_pdf):
            try:
                os.remove(self._preview_pdf)
            except OSError:
                pass
            self._preview_pdf = None

    def export_to_pdf(self):
        """Экспорт этого акта в PDF A5."""
        try:
            self.sync_template_from_ui()
            file_path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf")],
                initialfile=f"{self.template_data.get('name', 'act')}.pdf"
            )
            if not file_path:
                return
            from reports.report_renderer import ActPDFGenerator
            gen = ActPDFGenerator(self._build_company_info(), template_data=self.template_data)
            device = self._build_demo_device()
            if self.act_type == "completion":
                ok = gen.generate_completion_pdf(file_path, device)
            else:
                ok = gen.generate_receipt_pdf(file_path, device)
            if ok:
                messagebox.showinfo("Успех", f"PDF (A5) сохранён:\n{file_path}")
            else:
                messagebox.showerror("Ошибка", "Не удалось создать PDF")
        except ImportError:
            messagebox.showerror("Ошибка", "Установите reportlab: pip install reportlab")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось создать PDF: {e}")

    def print_pdf(self):
        """Печать этого акта на принтер."""
        try:
            import subprocess
            import sys as _sys
            self.sync_template_from_ui()
            from reports.report_renderer import ActPDFGenerator
            gen = ActPDFGenerator(self._build_company_info(), template_data=self.template_data)
            device = self._build_demo_device()
            suffix = self.act_type
            fd, tmp_pdf = tempfile.mkstemp(suffix=f"_{suffix}.pdf", prefix="act_print_")
            os.close(fd)
            if self.act_type == "completion":
                ok = gen.generate_completion_pdf(tmp_pdf, device)
            else:
                ok = gen.generate_receipt_pdf(tmp_pdf, device)
            if not ok or not os.path.exists(tmp_pdf):
                messagebox.showerror("Ошибка", "Не удалось сформировать PDF для печати")
                return
            printed = False
            try:
                if _sys.platform == "win32":
                    os.startfile(tmp_pdf, "print")
                    printed = True
                elif _sys.platform == "darwin":
                    subprocess.run(["lpr", tmp_pdf], check=False)
                    printed = True
                else:
                    subprocess.run(["lp", tmp_pdf], check=False)
                    printed = True
            except Exception as pe:
                logger.error(f"Прямая печать не удалась: {pe}")
                try:
                    if _sys.platform == "win32":
                        os.startfile(tmp_pdf)
                        printed = True
                except Exception:
                    pass
            if printed:
                messagebox.showinfo("Печать", "Документ отправлен на печать.")
            else:
                messagebox.showwarning("Печать", f"PDF создан, но отправка на печать не удалась.\nФайл: {tmp_pdf}")
        except ImportError:
            messagebox.showerror("Ошибка", "Установите reportlab: pip install reportlab")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось напечатать: {e}")


# ===========================================================================
# Главное окно редактора с вкладками
# ===========================================================================

class ReportEditor(ctk.CTkToplevel):
    """Визуальный редактор актов с вкладками «Акт приёма» / «Акт выполненных работ».

    Совместимость: принимает необязательный template_type (по умолчанию 'receipt'),
    открывает на соответствующей вкладке.
    """

    def __init__(self, parent, colors: dict, template_type: str = "receipt", settings=None):
        super().__init__(parent)
        self.parent = parent
        self.colors = colors
        self.settings = settings  # опционально, для сохранения геометрии
        self.initial_tab = template_type if template_type in ('receipt', 'completion') else 'receipt'
        self.panels = {}  # act_type -> ActPanel

        self.title("Редактор актов")
        # Восстанавливаем геометрию из config (или дефолт с центрированием)
        from utils.window_state import restore_window_geometry
        restore_window_geometry(self.settings, "report_editor", self,
                                default_w=1180, default_h=680, min_w=900, min_h=600)

        self.transient(parent)
        self.grab_set()

        # Сохраняем геометрию при закрытии
        self.protocol("WM_DELETE_WINDOW", self._close_with_geometry)

        self.create_widgets()
        # Первичный рендер предпросмотра активной вкладки
        self.after(400, lambda: self.active_panel().update_preview())

    def _fit_window(self, default_w: int, default_h: int, min_w: int, min_h: int):
        """Подбирает размер окна под текущий экран (для 1280x720 и меньше).

        Не превышает ~95% ширины/высоты экрана, центрирует окно.
        """
        try:
            import customtkinter as ctk
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
        except Exception:
            sw, sh = 1920, 1080
        w = min(default_w, int(sw * 0.96))
        h = min(default_h, int(sh * 0.92))
        # Гарантируем, что не меньше минимума и не больше экрана
        w = max(min_w, min(w, sw))
        h = max(min_h, min(h, sh))
        x = (sw - w) // 2
        y = max(0, (sh - h) // 2 - 20)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(min_w, min_h)

    def active_panel(self) -> ActPanel:
        """Возвращает панель текущей активной вкладки."""
        tab_name = self.tabview.get()
        for act_type, name in (('receipt', "📄 Акт приёма"), ('completion', "🔧 Акт выполненных работ")):
            if name == tab_name:
                return self.panels[act_type]
        return self.panels[self.initial_tab]

    def create_widgets(self):
        """Создание панели инструментов + вкладок."""
        # --- Панель инструментов ---
        toolbar = ctk.CTkFrame(self, fg_color=self.colors['bg_secondary'], height=50, corner_radius=0)
        toolbar.pack(fill="x", side="top")
        toolbar.pack_propagate(False)

        btn_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        btn_frame.pack(side="left", padx=10, pady=8)

        ModernButton(btn_frame, self.colors, variant="primary", text="💾 Сохранить",
                     command=self.save_current_template, width=110).pack(side="left", padx=2)
        ModernButton(btn_frame, self.colors, variant="success", text="📄 Экспорт PDF (A5)",
                     command=self.export_active_to_pdf, width=150).pack(side="left", padx=2)
        ModernButton(btn_frame, self.colors, variant="success", text="📋 2 на лист A4",
                     command=self.export_dual_from_editor, width=130).pack(side="left", padx=2)
        ModernButton(btn_frame, self.colors, variant="success", text="🖨️ Печать PDF",
                     command=self.print_active, width=120).pack(side="left", padx=2)

        # Экспорт/импорт/пресеты
        ModernButton(btn_frame, self.colors, variant="secondary", text="⬆ Экспорт",
                     command=self.export_settings, width=90).pack(side="left", padx=2)
        ModernButton(btn_frame, self.colors, variant="secondary", text="⬇ Импорт",
                     command=self.import_settings, width=90).pack(side="left", padx=2)

        # Пресеты
        preset_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        preset_frame.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(preset_frame, text="Пресет:", font=ctk.CTkFont(size=11),
                     text_color=self.colors['text_secondary']).pack(side="left", padx=(0, 4))
        self.preset_combo = ctk.CTkComboBox(
            preset_frame,
            values=["—", "📋 Официальный", "📝 Минималистичный", "🌙 Тёмный"],
            width=150, height=30,
            command=self.apply_preset)
        self.preset_combo.set("—")
        self.preset_combo.pack(side="left")

        ModernButton(btn_frame, self.colors, variant="secondary", text="✖ Закрыть",
                     command=self._close_with_geometry, width=100).pack(side="right", padx=2)

        # --- Вкладки ---
        self.tabview = ctk.CTkTabview(self, fg_color=self.colors['bg_primary'])
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        tab_receipt = self.tabview.add("📄 Акт приёма")
        tab_completion = self.tabview.add("🔧 Акт выполненных работ")

        # Создаём панели (каждая — двухпанельный layout: настройки | предпросмотр)
        self.panels['receipt'] = ActPanel(tab_receipt, self, 'receipt')
        self.panels['completion'] = ActPanel(tab_completion, self, 'completion')

        # Активируем запрошенную вкладку
        target_name = "📄 Акт приёма" if self.initial_tab == 'receipt' else "🔧 Акт выполненных работ"
        self.tabview.set(target_name)

        # Перерисовываем предпросмотр при переключении вкладки
        self.tabview.configure(command=self._on_tab_changed)

    def _on_tab_changed(self):
        """Обновляем предпросмотр при переключении вкладки."""
        try:
            panel = self.active_panel()
            if panel is not None:
                panel.update_preview()
        except Exception as e:
            logger.error(f"Ошибка обновления вкладки: {e}")

    # ------------------------------------------------------------------
    # Действия панели инструментов (применяются к активной вкладке)
    # ------------------------------------------------------------------

    def save_current_template(self):
        """Сохраняет шаблон активной вкладки."""
        panel = self.active_panel()
        if panel.save_template():
            messagebox.showinfo("Успех", "Шаблон сохранён!")

    def export_settings(self):
        """Экспорт настроек активного шаблона в .json файл."""
        try:
            panel = self.active_panel()
            panel.sync_template_from_ui()
            default_name = f"act_template_{panel.act_type}.json"
            file_path = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON", "*.json")],
                initialfile=default_name)
            if not file_path:
                return
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(panel.template_data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Успех", f"Настройки экспортированы:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось экспортировать: {e}")

    def import_settings(self):
        """Импорт настроек шаблона из .json файла."""
        try:
            file_path = filedialog.askopenfilename(
                title="Выберите файл настроек",
                filetypes=[("JSON", "*.json")])
            if not file_path:
                return
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            panel = self.active_panel()
            panel.template_data = data
            panel.logo_path = data.get("logo_path", "")
            panel.qr_path = data.get("qr_path", "")
            save_template_data(panel.act_type, data)
            panel._reload_ui()
            messagebox.showinfo("Успех", "Настройки импортированы и применены!")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось импортировать: {e}")

    def apply_preset(self, preset_name: str):
        """Применяет готовый пресет оформления."""
        if not preset_name or preset_name == "—":
            return
        panel = self.active_panel()

        # Базовые пресеты
        presets = {
            "📋 Официальный": {
                "primary_color": "#007aff",
                "font_name": "Trebuchet MS",
                "page_margin_mm": 10,
                "logo_size": 60,
                "logo_position": "По центру",
            },
            "📝 Минималистичный": {
                "primary_color": "#6e6e73",
                "font_name": "Helvetica",
                "page_margin_mm": 6,
                "logo_size": 40,
                "logo_position": "Слева",
            },
            "🌙 Тёмный": {
                "primary_color": "#5856d6",
                "font_name": "Arial",
                "page_margin_mm": 8,
                "logo_size": 50,
                "logo_position": "Справа",
            },
        }
        preset = presets.get(preset_name)
        if not preset:
            return

        panel.sync_template_from_ui()
        panel.template_data.update(preset)
        panel._reload_ui()
        messagebox.showinfo("Пресет", f"Применён пресет «{preset_name}»")

    def export_active_to_pdf(self):
        """Экспорт активной вкладки в PDF."""
        self.active_panel().export_to_pdf()

    def export_dual_from_editor(self):
        """Экспорт двух копий акта на одном листе A4 (демо-данные)."""
        panel = self.active_panel()
        panel.sync_template_from_ui()
        try:
            from tkinter import filedialog as _fd
            file_path = _fd.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf")],
                initialfile=f"{panel.act_type}_dual.pdf")
            if not file_path:
                return
            from reports.report_renderer import ActPDFGenerator
            gen = ActPDFGenerator(panel._build_company_info(), template_data=panel.template_data)
            device = panel._build_demo_device()
            ok = gen.generate_dual_pdf(file_path, device, device,
                                       act_type1=panel.act_type, act_type2=panel.act_type)
            if ok:
                messagebox.showinfo("Успех", f"Два акта на A4 сохранены:\n{file_path}")
            else:
                messagebox.showerror("Ошибка", "Не удалось создать PDF")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось: {e}")

    def print_active(self):
        """Печать активной вкладки."""
        self.active_panel().print_pdf()

    def _close_with_geometry(self):
        """Сохраняет геометрию окна в config и закрывает его."""
        try:
            from utils.window_state import save_window_geometry
            save_window_geometry(self.settings, "report_editor", self)
        except Exception:
            pass
        self.destroy()

    def destroy(self):
        """Очистка временных PDF и закрытие."""
        for panel in self.panels.values():
            panel._cleanup_preview_pdf()
        super().destroy()
