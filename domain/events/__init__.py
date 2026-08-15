"""Domain events module - события предметной области."""

from .events import (
    ClientCreatedEvent,
    DomainEvent,
    EventType,
    OrderCompletedEvent,
    OrderCreatedEvent,
    OrderStatusChangedEvent,
    PhotoAddedEvent,
    WorkItemAddedEvent,
)

__all__ = [
    "ClientCreatedEvent",
    "DomainEvent",
    "EventType",
    "OrderCompletedEvent",
    "OrderCreatedEvent",
    "OrderStatusChangedEvent",
    "PhotoAddedEvent",
    "WorkItemAddedEvent",
]
