"""Domain module - бизнес-константы.

SSOT для статусов/приоритетов/справочников (domain.constants) — реально
используется всем живым приложением (gui/, database/, pwa/). Раньше этот
__init__.py также импортировал entities.py/aggregates.py — независимую,
никогда не используемую живым кодом иерархию Client/Device/WorkItem/
OrderAggregate (дублирующую database.sqlalchemy_models.Client/Device),
и вместе с ней domain/services/, domain/events/, domain/state_machines/ —
недостижимый мёртвый стек (~2500 строк, включая 3 несовместимых графа
переходов статуса заказа), см. AUDIT_REPORT_v21.md. Удалены.
"""

from .constants import (
    CLIENT_STATUSES,
    CLOSED_STATUSES,
    DEFAULT_PRIORITY,
    DEFAULT_STATUS,
    DICTIONARY_TYPES,
    PRIORITIES,
    STATUS_ISSUED,
    STATUS_READY,
    STATUS_REFUSED,
    STATUSES,
    WARRANTIES,
)

__all__ = [
    "CLIENT_STATUSES",
    "CLOSED_STATUSES",
    "DEFAULT_PRIORITY",
    "DEFAULT_STATUS",
    "DICTIONARY_TYPES",
    "PRIORITIES",
    "STATUS_ISSUED",
    "STATUS_READY",
    "STATUS_REFUSED",
    "STATUSES",
    "WARRANTIES",
]
