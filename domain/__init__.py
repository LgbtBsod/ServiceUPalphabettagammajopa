"""Domain module - бизнес-модели и агрегаты.

Содержит чистые бизнес-сущности без зависимостей от инфраструктуры.
"""

from .aggregates import OrderAggregate
from .constants import (
    CLIENT_STATUSES,
    DEFAULT_PRIORITY,
    DEFAULT_STATUS,
    DICTIONARY_TYPES,
    PRIORITIES,
    STATUSES,
    WARRANTIES,
)
from .entities import (
    Client,
    Device,
    FinanceRecord,
    Photo,
    RepairHistory,
    WorkItem,
)

__all__ = [
    "CLIENT_STATUSES",
    "DEFAULT_PRIORITY",
    "DEFAULT_STATUS",
    "DICTIONARY_TYPES",
    "PRIORITIES",
    # Domain constants
    "STATUSES",
    "WARRANTIES",
    "Client",
    # Entities and aggregates
    "Device",
    "FinanceRecord",
    "OrderAggregate",
    "Photo",
    "RepairHistory",
    "WorkItem",
]
