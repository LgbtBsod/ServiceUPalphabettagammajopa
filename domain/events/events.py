"""
Domain events - события предметной области.

События используются для реализации Event-Driven Architecture
и слабой связанности между компонентами системы.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
from enum import Enum


class EventType(str, Enum):
    """Типы доменных событий."""
    ORDER_CREATED = "order.created"
    ORDER_UPDATED = "order.updated"
    ORDER_STATUS_CHANGED = "order.status_changed"
    ORDER_COMPLETED = "order.completed"
    ORDER_ISSUED = "order.issued"
    ORDER_CANCELLED = "order.cancelled"
    
    CLIENT_CREATED = "client.created"
    CLIENT_UPDATED = "client.updated"
    
    WORK_ITEM_ADDED = "work_item.added"
    WORK_ITEM_REMOVED = "work_item.removed"
    
    PHOTO_ADDED = "photo.added"
    PHOTO_REMOVED = "photo.removed"
    
    PAYMENT_RECEIVED = "payment.received"
    EXPENSE_ADDED = "expense.added"


@dataclass(slots=True, frozen=True)
class DomainEvent:
    """
    Базовый класс доменного события.
    
    Все события неизменяемы (frozen) для обеспечения целостности.
    """
    event_type: EventType
    aggregate_id: Optional[int]
    occurred_at: datetime = field(default_factory=datetime.now)
    payload: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Сериализация события."""
        return {
            'event_type': self.event_type.value,
            'aggregate_id': self.aggregate_id,
            'occurred_at': self.occurred_at.isoformat(),
            'payload': self.payload,
        }


# ============================================================================
# События заказов
# ============================================================================

@dataclass(slots=True, frozen=True)
class OrderCreatedEvent(DomainEvent):
    """Событие создания заказа."""
    order_number: str = ""
    client_name: str = ""
    device_type: str = ""
    brand: str = ""
    model: str = ""
    
    @classmethod
    def create(
        cls,
        aggregate_id: Optional[int],
        order_number: str,
        client_name: str,
        device_type: str,
        brand: str,
        model: str,
        extra_payload: Optional[Dict[str, Any]] = None,
    ) -> OrderCreatedEvent:
        """Фабричный метод создания события."""
        payload = {
            'order_number': order_number,
            'client_name': client_name,
            'device_type': device_type,
            'brand': brand,
            'model': model,
        }
        if extra_payload:
            payload.update(extra_payload)
        
        return cls(
            event_type=EventType.ORDER_CREATED,
            aggregate_id=aggregate_id,
            payload=payload,
            order_number=order_number,
            client_name=client_name,
            device_type=device_type,
            brand=brand,
            model=model,
        )


@dataclass(slots=True, frozen=True)
class OrderStatusChangedEvent(DomainEvent):
    """Событие изменения статуса заказа."""
    old_status: str = ""
    new_status: str = ""
    
    @classmethod
    def create(
        cls,
        aggregate_id: Optional[int],
        old_status: str,
        new_status: str,
        extra_payload: Optional[Dict[str, Any]] = None,
    ) -> OrderStatusChangedEvent:
        """Фабричный метод создания события."""
        payload = {
            'old_status': old_status,
            'new_status': new_status,
        }
        if extra_payload:
            payload.update(extra_payload)
        
        return cls(
            event_type=EventType.ORDER_STATUS_CHANGED,
            aggregate_id=aggregate_id,
            payload=payload,
            old_status=old_status,
            new_status=new_status,
        )


@dataclass(slots=True, frozen=True)
class OrderCompletedEvent(DomainEvent):
    """Событие завершения заказа."""
    total_price: float = 0.0
    expense: float = 0.0
    profit: float = 0.0
    
    @classmethod
    def create(
        cls,
        aggregate_id: Optional[int],
        total_price: float,
        expense: float,
        profit: float,
        extra_payload: Optional[Dict[str, Any]] = None,
    ) -> OrderCompletedEvent:
        """Фабричный метод создания события."""
        payload = {
            'total_price': total_price,
            'expense': expense,
            'profit': profit,
        }
        if extra_payload:
            payload.update(extra_payload)
        
        return cls(
            event_type=EventType.ORDER_COMPLETED,
            aggregate_id=aggregate_id,
            payload=payload,
            total_price=total_price,
            expense=expense,
            profit=profit,
        )


# ============================================================================
# События клиентов
# ============================================================================

@dataclass(slots=True, frozen=True)
class ClientCreatedEvent(DomainEvent):
    """Событие создания клиента."""
    client_name: str = ""
    phone: str = ""
    
    @classmethod
    def create(
        cls,
        aggregate_id: Optional[int],
        client_name: str,
        phone: str,
        extra_payload: Optional[Dict[str, Any]] = None,
    ) -> ClientCreatedEvent:
        """Фабричный метод создания события."""
        payload = {
            'client_name': client_name,
            'phone': phone,
        }
        if extra_payload:
            payload.update(extra_payload)
        
        return cls(
            event_type=EventType.CLIENT_CREATED,
            aggregate_id=aggregate_id,
            payload=payload,
            client_name=client_name,
            phone=phone,
        )


# ============================================================================
# События работ и фото
# ============================================================================

@dataclass(slots=True, frozen=True)
class WorkItemAddedEvent(DomainEvent):
    """Событие добавления работы."""
    description: str = ""
    price: float = 0.0
    quantity: int = 1
    
    @classmethod
    def create(
        cls,
        aggregate_id: Optional[int],
        description: str,
        price: float,
        quantity: int = 1,
        extra_payload: Optional[Dict[str, Any]] = None,
    ) -> WorkItemAddedEvent:
        """Фабричный метод создания события."""
        payload = {
            'description': description,
            'price': price,
            'quantity': quantity,
            'total': price * quantity,
        }
        if extra_payload:
            payload.update(extra_payload)
        
        return cls(
            event_type=EventType.WORK_ITEM_ADDED,
            aggregate_id=aggregate_id,
            payload=payload,
            description=description,
            price=price,
            quantity=quantity,
        )


@dataclass(slots=True, frozen=True)
class PhotoAddedEvent(DomainEvent):
    """Событие добавления фотографии."""
    file_path: str = ""
    photo_type: str = ""
    
    @classmethod
    def create(
        cls,
        aggregate_id: Optional[int],
        file_path: str,
        photo_type: str = "device",
        extra_payload: Optional[Dict[str, Any]] = None,
    ) -> PhotoAddedEvent:
        """Фабричный метод создания события."""
        payload = {
            'file_path': file_path,
            'photo_type': photo_type,
        }
        if extra_payload:
            payload.update(extra_payload)
        
        return cls(
            event_type=EventType.PHOTO_ADDED,
            aggregate_id=aggregate_id,
            payload=payload,
            file_path=file_path,
            photo_type=photo_type,
        )
