#!/usr/bin/env python3

"""Модуль событий домена.

Экспортирует компоненты Domain Events для использования в приложении.
"""

from .domain_events import (
    ClientAnalyticsHandler,
    DomainEvent,
    EventBus,
    EventHandler,
    EventType,
    # Обработчики по умолчанию
    OrderNotificationHandler,
    OrderStatusLoggerHandler,
    create_event,
    event_bus,
    event_handler,
)

__all__ = [
    "ClientAnalyticsHandler",
    "DomainEvent",
    "EventBus",
    "EventHandler",
    "EventType",
    "OrderNotificationHandler",
    "OrderStatusLoggerHandler",
    "create_event",
    "event_bus",
    "event_handler",
]
