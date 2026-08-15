#!/usr/bin/env python3

"""Domain Constants - Single Source of Truth for business dictionaries.

This module contains all business-related constants and dictionaries
used throughout the application. Following SSOT principle, these are
defined once and imported wherever needed.

Principles applied:
- SSOT (Single Source of Truth): All business constants in one place
- DRY (Don't Repeat Yourself): No duplication of constant values
- SRP (Single Responsibility): Only domain constants, no app settings
"""

from __future__ import annotations

from typing import Final

# =============================================================================
# ORDER STATUSES
# =============================================================================

STATUSES: Final[list[str]] = [
    "Диагностика",
    "Ожидание запчастей",
    "В ремонте",
    "Готов к выдаче",
    "Выдан клиенту",
    "Отказ от ремонта",
]

# Default status for new orders
DEFAULT_STATUS: Final[str] = STATUSES[0]

# Именованные "закрытые" статусы — раньше независимо переопределялись как
# сырые строковые литералы в 7 живых файлах (gui/main_window.py,
# gui/dialogs/client_history.py, gui/dialogs/device_form.py, pwa/server.py,
# database/sqlalchemy_database.py, database/client_db.py, database/db_manager.py),
# включая приватные дубли-константы в самом facade БД. См. AUDIT_REPORT_v21.md.
STATUS_READY: Final[str] = STATUSES[3]  # "Готов к выдаче"
STATUS_ISSUED: Final[str] = STATUSES[4]  # "Выдан клиенту"
STATUS_REFUSED: Final[str] = STATUSES[5]  # "Отказ от ремонта"
CLOSED_STATUSES: Final[tuple[str, ...]] = (STATUS_ISSUED, STATUS_REFUSED)


# =============================================================================
# PRIORITIES
# =============================================================================

PRIORITIES: Final[list[str]] = [
    "Низкий",
    "Обычный",
    "Высокий",
    "Срочный",
]

# Default priority for new orders
DEFAULT_PRIORITY: Final[str] = PRIORITIES[1]


# =============================================================================
# CLIENT STATUSES
# =============================================================================

CLIENT_STATUSES: Final[list[str]] = [
    "Новый",
    "Постоянный",
    "VIP",
    "Проблемный",
]


# =============================================================================
# WARRANTIES
# =============================================================================

WARRANTIES: Final[list[str]] = [
    "",
    "1 месяц",
    "3 месяца",
    "6 месяцев",
    "1 год",
    "2 года",
]


# =============================================================================
# DICTIONARY TYPES (Reference Data)
# =============================================================================

DICTIONARY_TYPES: Final[dict[str, dict]] = {
    "work": {
        "name": "Выполненные работы",
        "icon": "🔨",
        "default_values": [
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
            "Замена HDD на SSD",
        ],
    },
    "appearance": {
        "name": "Внешний вид",
        "icon": "👁️",
        "default_values": [
            "Отличное состояние",
            "Хорошее состояние",
            "Среднее состояние",
            "Частично разобран",
            "Следы эксплуатации",
            "Сколы/царапины",
            "Потертости",
            "Разбит экран",
            "Трещина на корпусе",
            "Отсутствуют детали",
        ],
    },
    "completeness": {
        "name": "Комплектация",
        "icon": "📦",
        "default_values": [
            "Полная комплектация",
            "Без ЗУ",
            "Без аккумулятора",
            "Только устройство",
            "С ЗУ, без кабеля",
            "С документами",
            "В заводской упаковке",
            "Без крышки",
            "Неполная комплектация",
        ],
    },
    "brands": {
        "name": "Бренды",
        "icon": "🏢",
        "default_values": [
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
            "Другое",
        ],
    },
    "device_types": {
        "name": "Типы устройств",
        "icon": "📱",
        "default_values": [
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
            "Другое",
        ],
    },
    "engineers": {
        "name": "Инженеры",
        "icon": "👨‍🔧",
        "default_values": [
            "Иноагент",
            "Петров П.П.",
            "Сидоров С.С.",
            "Козлов А.А.",
            "Михайлов М.М.",
        ],
    },
    "client_statuses": {
        "name": "Статусы клиента",
        "icon": "👤",
        "default_values": CLIENT_STATUSES,  # Reference to single source
    },
}


# =============================================================================
# PUBLIC API
# =============================================================================

__all__ = [
    "CLOSED_STATUSES",
    # Client constants
    "CLIENT_STATUSES",
    "DEFAULT_PRIORITY",
    "DEFAULT_STATUS",
    # Reference data
    "DICTIONARY_TYPES",
    "PRIORITIES",
    "STATUS_ISSUED",
    "STATUS_READY",
    "STATUS_REFUSED",
    # Order constants
    "STATUSES",
    # Warranty constants
    "WARRANTIES",
]
