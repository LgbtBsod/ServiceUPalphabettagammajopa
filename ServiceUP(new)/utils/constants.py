#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Константы приложения"""

# Статусы заказов
STATUSES = [
    "Диагностика",
    "Ожидание запчастей", 
    "В ремонте",
    "Готов к выдаче",
    "Выдан клиенту",
    "Отказ от ремонта"
]

# Приоритеты
PRIORITIES = ["Низкий", "Обычный", "Высокий", "Срочный"]

# Статусы клиентов
CLIENT_STATUSES = ["Новый", "Постоянный", "Еблан"]

# Гарантии
WARRANTIES = ["", "1 месяц", "3 месяца", "6 месяцев", "1 год", "2 года"]

# Типы словарей
DICTIONARY_TYPES = {
    'work': {
        'name': 'Выполненные работы',
        'icon': '🔨',
        'default_values': [
            "Диагностика",
            "Установка ОС",
            "Замена аккумулятора",
            "Замена дисплея",
            "Профилактика",
            "Замена термопасты",
            "Ремонт материнской платы",
            "Замена клавиатуры",
            "Замена разъема зарядки",
            "Восстановление данных",
            "Замена матрицы",
            "Ремонт после залития",
            "Замена кулера",
            "Апгрейд ОЗУ",
            "Замена HDD на SSD"
        ]
    },
    'appearance': {
        'name': 'Внешний вид',
        'icon': '👁️',
        'default_values': [
            "Отличное состояние",
            "Хорошее состояние",
            "Среднее состояние",
            "Частично разобран",
            "Следы эксплуатации",
            "Сколы/царапины",
            "Потертости",
            "Разбит экран",
            "Трещина на корпусе",
            "Отсутствуют детали"
        ]
    },
    'completeness': {
        'name': 'Комплектация',
        'icon': '📦',
        'default_values': [
            "Полная комплектация",
            "Без ЗУ",
            "Без аккумулятора",
            "Только устройство",
            "С ЗУ, без кабеля",
            "С документами",
            "В заводской упаковке",
            "Без крышки",
            "Неполная комплектация"
        ]
    },
    'brands': {
        'name': 'Бренды',
        'icon': '🏢',
        'default_values': [
            "Apple",
            "Samsung",
            "Xiaomi",
            "HP",
            "Dell",
            "Lenovo",
            "Asus",
            "Acer",
            "LG",
            "Sony",
            "Другое"
        ]
    },
    'device_types': {
        'name': 'Типы устройств',
        'icon': '📱',
        'default_values': [
            "Ноутбук",
            "ПК",
            "Смартфон",
            "Планшет",
            "Монитор",
            "Принтер",
            "Телевизор",
            "Аудио",
            "Фотоаппарат",
            "Игровая консоль",
            "Другое"
        ]
    },
    'engineers': {
        'name': 'Инженеры',
        'icon': '👨‍🔧',
        'default_values': [
            "Иноагент",
            "Петров П.П.",
            "Сидоров С.С.",
            "Козлов А.А.",
            "Михайлов М.М."
        ]
    },
    'client_statuses': {
        'name': 'Статусы клиента',
        'icon': '👤',
        'default_values': [
            "Новый",
            "Постоянный",
            "VIP",
            "Еблан"
        ]
    }
}

# Настройки по умолчанию
DEFAULT_SETTINGS = {
    'theme': 'light',
    'accent_color': '#0078d4',
    'fullscreen': False,
    'confirm_delete': True,
    'confirm_exit': False,
    'auto_save_on_close': True,
    'default_status': 'Диагностика',
    'default_priority': 'Обычный',
    'remind_overdue': True,
    'overdue_days': 14,
    'notify_on_ready': True,
    'auto_backup': True,
    'backup_interval': 24,
    'backup_count': 10,
    'backup_path': '',  # пусто = BACKUP_DIR по умолчанию
    'compress_backups': True,
    'photo_quality': 85,
    'create_thumbnails': True,
    'window_width': 1280,
    'window_height': 720,
    'window_x': None,
    'window_y': None,
    'show_completed': True,
    'transparency': False,
    'transparency_alpha': 1.0,
    # Геометрия окон: {window_key: "WxH+X+Y"} — сохраняется/восстанавливается
    'window_geometry': {},
    # Настройки PWA (мобильная версия)
    'pwa': {
        'port': 5000,
        'auto_start': False,
        'auto_sync': True,
        'sync_interval': 30,
    },
}
