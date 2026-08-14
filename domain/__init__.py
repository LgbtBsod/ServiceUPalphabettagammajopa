"""
Domain module - бизнес-модели и агрегаты.

Содержит чистые бизнес-сущности без зависимостей от инфраструктуры.
"""

from .entities import (
    Device,
    Client,
    WorkItem,
    Photo,
    RepairHistory,
    FinanceRecord,
)

from .aggregates import OrderAggregate

from .constants import (
    STATUSES,
    DEFAULT_STATUS,
    PRIORITIES,
    DEFAULT_PRIORITY,
    CLIENT_STATUSES,
    WARRANTIES,
    DICTIONARY_TYPES,
)

__all__ = [
    # Entities and aggregates
    'Device',
    'Client',
    'WorkItem',
    'Photo',
    'RepairHistory',
    'FinanceRecord',
    'OrderAggregate',
    # Domain constants
    'STATUSES',
    'DEFAULT_STATUS',
    'PRIORITIES',
    'DEFAULT_PRIORITY',
    'CLIENT_STATUSES',
    'WARRANTIES',
    'DICTIONARY_TYPES',
]
