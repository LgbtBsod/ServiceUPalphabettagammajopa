"""
Core Events Module.

Система событий для связи между компонентами системы.
"""

from core.events.event_bus import (
    Event,
    DomainEvent,
    IntegrationEvent,
    EventFilter,
    EventTypeFilter,
    EventPriority,
    EventBus,
    get_event_bus,
    reset_event_bus,
    on_event,
    async_on_event,
)

# Тип события как строка (упрощённая система типов)
EventType = str

__all__ = [
    "Event",
    "DomainEvent",
    "IntegrationEvent",
    "EventFilter",
    "EventTypeFilter",
    "EventPriority",
    "EventBus",
    "get_event_bus",
    "reset_event_bus",
    "on_event",
    "async_on_event",
    "EventType",
]
