"""Core Events Module.

Система событий для связи между компонентами системы.
"""

from core.events.event_bus import (
    DomainEvent,
    Event,
    EventBus,
    EventFilter,
    EventPriority,
    EventTypeFilter,
    IntegrationEvent,
    async_on_event,
    get_event_bus,
    on_event,
    reset_event_bus,
)

# Тип события как строка (упрощённая система типов)
EventType = str

__all__ = [
    "DomainEvent",
    "Event",
    "EventBus",
    "EventFilter",
    "EventPriority",
    "EventType",
    "EventTypeFilter",
    "IntegrationEvent",
    "async_on_event",
    "get_event_bus",
    "on_event",
    "reset_event_bus",
]
