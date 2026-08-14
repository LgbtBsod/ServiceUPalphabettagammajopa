#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль событий домена.

Экспортирует компоненты Domain Events для использования в приложении.
"""

from .domain_events import (
    EventType,
    DomainEvent,
    EventHandler,
    EventBus,
    event_handler,
    create_event,
    event_bus,
    # Обработчики по умолчанию
    OrderNotificationHandler,
    OrderStatusLoggerHandler,
    ClientAnalyticsHandler,
)

__all__ = [
    'EventType',
    'DomainEvent',
    'EventHandler',
    'EventBus',
    'event_handler',
    'create_event',
    'event_bus',
    'OrderNotificationHandler',
    'OrderStatusLoggerHandler',
    'ClientAnalyticsHandler',
]
