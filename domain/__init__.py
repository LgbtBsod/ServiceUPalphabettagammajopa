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

__all__ = [
    'Device',
    'Client',
    'WorkItem',
    'Photo',
    'RepairHistory',
    'FinanceRecord',
    'OrderAggregate',
]
