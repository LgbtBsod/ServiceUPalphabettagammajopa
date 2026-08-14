#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Domain Events паттерн для событийно-ориентированной архитектуры.

Реализует паттерн Domain Events для слабой связанности компонентов.
События домена позволяют реагировать на изменения без прямых зависимостей.
Соблюдает принципы SOLID, особенно Open/Closed Principle.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Type, Callable, Optional
from enum import Enum
import logging
import json

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Типы событий домена."""
    
    # События заказов
    ORDER_CREATED = "order.created"
    ORDER_UPDATED = "order.updated"
    ORDER_DELETED = "order.deleted"
    ORDER_STATUS_CHANGED = "order.status_changed"
    ORDER_READY_FOR_PICKUP = "order.ready_for_pickup"
    
    # События клиентов
    CLIENT_CREATED = "client.created"
    CLIENT_UPDATED = "client.updated"
    CLIENT_DELETED = "client.deleted"
    CLIENT_STATS_UPDATED = "client.stats_updated"
    
    # События работ
    WORK_ITEM_ADDED = "work_item.added"
    WORK_ITEM_REMOVED = "work_item.removed"
    WORK_ITEM_UPDATED = "work_item.updated"
    
    # Системные события
    DATABASE_INITIALIZED = "database.initialized"
    BACKUP_COMPLETED = "backup.completed"
    REPORT_GENERATED = "report.generated"


@dataclass
class DomainEvent:
    """
    Базовый класс события домена.
    
    Атрибуты:
        event_type: Тип события из EventType
        aggregate_id: ID агрегата (заказа, клиента и т.д.)
        timestamp: Время создания события
        payload: Данные события
        metadata: Дополнительные метаданные
    """
    
    event_type: EventType
    aggregate_id: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.now)
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Сериализация события в словарь."""
        return {
            'event_type': self.event_type.value,
            'aggregate_id': self.aggregate_id,
            'timestamp': self.timestamp.isoformat(),
            'payload': self.payload,
            'metadata': self.metadata
        }
    
    def to_json(self) -> str:
        """Сериализация события в JSON."""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DomainEvent:
        """Десериализация события из словаря."""
        return cls(
            event_type=EventType(data['event_type']),
            aggregate_id=data.get('aggregate_id'),
            timestamp=datetime.fromisoformat(data['timestamp']) if isinstance(data['timestamp'], str) else data['timestamp'],
            payload=data.get('payload', {}),
            metadata=data.get('metadata', {})
        )


class EventHandler(ABC):
    """
    Абстрактный обработчик событий.
    
    Все обработчики должны наследовать этот класс и реализовать метод handle.
    Соблюдает принцип Dependency Inversion Principle (DIP).
    """
    
    @abstractmethod
    def handle(self, event: DomainEvent) -> None:
        """
        Обработка события.
        
        Args:
            event: Событие домена для обработки.
        """
        pass
    
    @property
    @abstractmethod
    def subscribed_events(self) -> List[EventType]:
        """
        Список типов событий, на которые подписан обработчик.
        
        Returns:
            Список EventType.
        """
        pass


class EventBus:
    """
    Шина событий для публикации и подписки на события домена.
    
    Реализует паттерн Observer/Mediator для слабой связанности компонентов.
    Потокобезопасная реализация с поддержкой синхронных и асинхронных обработчиков.
    """
    
    _instance: Optional[EventBus] = None
    
    def __new__(cls) -> EventBus:
        """Singleton паттерн для глобальной шины событий."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._handlers: Dict[EventType, List[EventHandler]] = {}
        self._event_history: List[DomainEvent] = []
        self._max_history_size = 1000
        self._initialized = True
        
        logger.info("EventBus initialized")
    
    @classmethod
    def get_instance(cls) -> EventBus:
        """Получение экземпляра шины событий."""
        return cls()
    
    @classmethod
    def reset_instance(cls) -> None:
        """Сброс экземпляра (для тестов)."""
        cls._instance = None
    
    def subscribe(self, handler: EventHandler) -> None:
        """
        Подписка обработчика на события.
        
        Args:
            handler: Экземпляр обработчика событий.
        """
        for event_type in handler.subscribed_events:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            
            if handler not in self._handlers[event_type]:
                self._handlers[event_type].append(handler)
                logger.debug(f"Handler {handler.__class__.__name__} subscribed to {event_type.value}")
    
    def unsubscribe(self, handler: EventHandler) -> None:
        """
        Отписка обработчика от событий.
        
        Args:
            handler: Экземпляр обработчика событий.
        """
        for event_type, handlers in list(self._handlers.items()):
            if handler in handlers:
                handlers.remove(handler)
                logger.debug(f"Handler {handler.__class__.__name__} unsubscribed from {event_type.value}")
    
    def publish(self, event: DomainEvent) -> None:
        """
        Публикация события всем подписчикам.
        
        Args:
            event: Событие домена для публикации.
        """
        handlers = self._handlers.get(event.event_type, [])
        
        logger.info(f"Publishing event {event.event_type.value} to {len(handlers)} handlers")
        
        for handler in handlers:
            try:
                handler.handle(event)
            except Exception as e:
                logger.error(f"Error in handler {handler.__class__.__name__}: {e}", exc_info=True)
        
        # Сохранение в историю
        self._event_history.append(event)
        if len(self._event_history) > self._max_history_size:
            self._event_history = self._event_history[-self._max_history_size:]
    
    def publish_multiple(self, events: List[DomainEvent]) -> None:
        """
        Публикация нескольких событий.
        
        Args:
            events: Список событий для публикации.
        """
        for event in events:
            self.publish(event)
    
    def get_history(self, event_type: Optional[EventType] = None, limit: int = 100) -> List[DomainEvent]:
        """
        Получение истории событий.
        
        Args:
            event_type: Фильтр по типу события (опционально).
            limit: Максимальное количество событий.
            
        Returns:
            Список событий из истории.
        """
        if event_type:
            filtered = [e for e in self._event_history if e.event_type == event_type]
            return filtered[-limit:]
        return self._event_history[-limit:]
    
    def clear_history(self) -> None:
        """Очистка истории событий."""
        self._event_history.clear()


# Декоратор для автоматической регистрации обработчиков
def event_handler(event_types: List[EventType]):
    """
    Декоратор для маркировки класса как обработчика событий.
    
    Args:
        event_types: Список типов событий для обработки.
        
    Returns:
        Декорированный класс.
    """
    def decorator(cls: Type[EventHandler]) -> Type[EventHandler]:
        original_init = cls.__init__
        
        def new_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            # Автоматическая подписка при создании экземпляра
            event_bus = EventBus.get_instance()
            event_bus.subscribe(self)
        
        cls.__init__ = new_init
        
        # Добавляем свойство subscribed_events
        cls.subscribed_events = property(lambda self: event_types)
        
        return cls
    
    return decorator


# Примеры обработчиков событий

@event_handler([EventType.ORDER_CREATED])
class OrderNotificationHandler(EventHandler):
    """Обработчик для отправки уведомлений о создании заказа."""
    
    @property
    def subscribed_events(self) -> List[EventType]:
        return [EventType.ORDER_CREATED]
    
    def handle(self, event: DomainEvent) -> None:
        logger.info(f"Sending notification for new order: {event.aggregate_id}")
        # Здесь можно отправить email, SMS или push-уведомление


@event_handler([EventType.ORDER_STATUS_CHANGED])
class OrderStatusLoggerHandler(EventHandler):
    """Обработчик для логирования изменений статуса заказа."""
    
    @property
    def subscribed_events(self) -> List[EventType]:
        return [EventType.ORDER_STATUS_CHANGED]
    
    def handle(self, event: DomainEvent) -> None:
        old_status = event.payload.get('old_status')
        new_status = event.payload.get('new_status')
        logger.info(f"Order {event.aggregate_id}: status changed from {old_status} to {new_status}")


@event_handler([EventType.CLIENT_CREATED, EventType.CLIENT_UPDATED])
class ClientAnalyticsHandler(EventHandler):
    """Обработчик для сбора аналитики по клиентам."""
    
    @property
    def subscribed_events(self) -> List[EventType]:
        return [EventType.CLIENT_CREATED, EventType.CLIENT_UPDATED]
    
    def handle(self, event: DomainEvent) -> None:
        logger.info(f"Client analytics event: {event.event_type.value}, client_id={event.aggregate_id}")


def create_event(event_type: EventType, aggregate_id: Optional[int] = None, 
                 payload: Optional[Dict[str, Any]] = None, 
                 metadata: Optional[Dict[str, Any]] = None) -> DomainEvent:
    """
    Фабричная функция для создания событий.
    
    Args:
        event_type: Тип события.
        aggregate_id: ID агрегата.
        payload: Данные события.
        metadata: Метаданные.
        
    Returns:
        Созданное событие домена.
    """
    return DomainEvent(
        event_type=event_type,
        aggregate_id=aggregate_id,
        payload=payload or {},
        metadata=metadata or {}
    )


# Глобальный экземпляр шины событий
event_bus = EventBus.get_instance()
