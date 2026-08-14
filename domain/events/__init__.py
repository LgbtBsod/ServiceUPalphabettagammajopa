"""
Domain events module - события предметной области.
"""

from .events import (
    EventType,
    DomainEvent,
    OrderCreatedEvent,
    OrderStatusChangedEvent,
    OrderCompletedEvent,
    ClientCreatedEvent,
    WorkItemAddedEvent,
    PhotoAddedEvent,
)

__all__ = [
    'EventType',
    'DomainEvent',
    'OrderCreatedEvent',
    'OrderStatusChangedEvent',
    'OrderCompletedEvent',
    'ClientCreatedEvent',
    'WorkItemAddedEvent',
    'PhotoAddedEvent',
]
