"""Event Bus Module - Система событий для связи плагинов.

Реализует паттерн Event Bus / Event Mediator для слабой связности между плагинами.
"""

import asyncio
import inspect
import typing
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import (
    Any,
    TypeVar,
)

from core.base import LoggableMixin

# Типы для событий
T = TypeVar("T")
EventHandler = Callable[[Any], None]
AsyncEventHandler = Callable[[Any], typing.Coroutine]


@dataclass
class Event:
    """Базовый класс события."""

    event_type: str
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "unknown"
    data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.event_type:
            raise ValueError("Event type cannot be empty")


@dataclass
class DomainEvent(Event):
    """Событие предметной области."""

    aggregate_id: str | None = None
    aggregate_type: str | None = None


@dataclass
class IntegrationEvent(Event):
    """Интеграционное событие для межсервисного взаимодействия."""

    correlation_id: str | None = None
    causation_id: str | None = None


class EventFilter(ABC):
    """Фильтр событий."""

    @abstractmethod
    def matches(self, event: Event) -> bool:
        """Проверяет, соответствует ли событие фильтру."""


class EventTypeFilter(EventFilter):
    """Фильтр по типу события."""

    def __init__(self, event_types: str | list[str]):
        self.event_types = (
            {event_types} if isinstance(event_types, str) else set(event_types)
        )

    def matches(self, event: Event) -> bool:
        return event.event_type in self.event_types


class EventPriority:
    """Приоритеты обработчиков событий."""

    LOW = 0
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200


@dataclass
class Subscription:
    """Подписка на событие."""

    event_type: str
    handler: EventHandler
    priority: int = EventPriority.NORMAL
    is_async: bool = False
    filter: EventFilter | None = None


class EventBus(LoggableMixin):
    """Шина событий для связи между плагинами.

    Реализует:
    - Publish/Subscribe паттерн
    - Синхронные и асинхронные обработчики
    - Приоритеты обработчиков
    - Фильтрацию событий
    - Dead Letter Queue для ошибочных событий
    """

    def __init__(self):
        super().__init__()
        self._subscriptions: dict[str, list[Subscription]] = {}
        self._dead_letter_queue: list[dict[str, Any]] = []
        self._event_history: list[Event] = []
        self._max_history_size = 1000
        self._is_running = False

    def subscribe(
        self,
        event_type: str | type[Event],
        handler: EventHandler,
        priority: int = EventPriority.NORMAL,
        event_filter: EventFilter | None = None,
    ) -> None:
        """Подписывает обработчик на событие.

        Args:
            event_type: Тип события (строка или класс)
            handler: Функция-обработчик
            priority: Приоритет обработчика
            event_filter: Опциональный фильтр событий
        """
        event_type_str = (
            event_type if isinstance(event_type, str) else event_type.__name__
        )

        subscription = Subscription(
            event_type=event_type_str,
            handler=handler,
            priority=priority,
            is_async=inspect.iscoroutinefunction(handler),
            filter=event_filter,
        )

        if event_type_str not in self._subscriptions:
            self._subscriptions[event_type_str] = []

        self._subscriptions[event_type_str].append(subscription)
        # Сортируем по приоритету (убывание)
        self._subscriptions[event_type_str].sort(key=lambda s: s.priority, reverse=True)

        self.logger.debug(
            f"Subscribed handler {handler.__name__} to event {event_type_str}"
        )

    def unsubscribe(
        self,
        event_type: str | type[Event],
        handler: EventHandler,
    ) -> bool:
        """Отписывает обработчик от события."""
        event_type_str = (
            event_type if isinstance(event_type, str) else event_type.__name__
        )

        if event_type_str not in self._subscriptions:
            return False

        initial_count = len(self._subscriptions[event_type_str])
        self._subscriptions[event_type_str] = [
            s for s in self._subscriptions[event_type_str] if s.handler != handler
        ]

        return len(self._subscriptions[event_type_str]) < initial_count

    def publish(self, event: Event) -> None:
        """Публикует событие всем подписчикам.

        Args:
            event: Событие для публикации
        """
        self.logger.debug(f"Publishing event: {event.event_type}")

        # Сохраняем в историю
        self._event_history.append(event)
        if len(self._event_history) > self._max_history_size:
            self._event_history.pop(0)

        # Получаем всех подписчиков
        subscribers = self._get_subscribers(event)

        # Вызываем обработчики
        for subscription in subscribers:
            try:
                if subscription.filter and not subscription.filter.matches(event):
                    continue

                if subscription.is_async:
                    # Асинхронный обработчик
                    asyncio.create_task(
                        self._call_async_handler(subscription.handler, event)
                    )
                else:
                    # Синхронный обработчик
                    subscription.handler(event)

            except Exception as e:
                self.logger.exception(
                    f"Error in event handler {subscription.handler.__name__}: {e}"
                )
                self._add_to_dead_letter(event, subscription, e)

    async def publish_async(self, event: Event) -> None:
        """Асинхронная публикация события."""
        self.logger.debug(f"Publishing event (async): {event.event_type}")

        self._event_history.append(event)
        if len(self._event_history) > self._max_history_size:
            self._event_history.pop(0)

        subscribers = self._get_subscribers(event)

        tasks = []
        for subscription in subscribers:
            try:
                if subscription.filter and not subscription.filter.matches(event):
                    continue

                if subscription.is_async:
                    tasks.append(self._call_async_handler(subscription.handler, event))
                else:
                    # Запускаем синхронный обработчик в executor
                    loop = asyncio.get_event_loop()
                    tasks.append(
                        loop.run_in_executor(None, subscription.handler, event)
                    )

            except Exception as e:
                self.logger.exception(f"Error preparing event handler: {e}")
                self._add_to_dead_letter(event, subscription, e)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _get_subscribers(self, event: Event) -> list[Subscription]:
        """Получает всех подписчиков для события."""
        subscribers = []

        # Прямые подписчики
        if event.event_type in self._subscriptions:
            subscribers.extend(self._subscriptions[event.event_type])

        # Подписчики на базовый класс Event
        if event.event_type != "Event" and "Event" in self._subscriptions:
            subscribers.extend(self._subscriptions["Event"])

        return subscribers

    async def _call_async_handler(
        self,
        handler: EventHandler | AsyncEventHandler,
        event: Event,
    ) -> None:
        """Вызывает асинхронный обработчик."""
        if asyncio.iscoroutinefunction(handler):
            await handler(event)
        else:
            handler(event)

    def _add_to_dead_letter(
        self,
        event: Event,
        subscription: Subscription,
        error: Exception,
    ) -> None:
        """Добавляет событие в Dead Letter Queue."""
        self._dead_letter_queue.append(
            {
                "event": event,
                "subscription": subscription,
                "error": str(error),
                "timestamp": datetime.now(),
            }
        )

        # Ограничиваем размер DLQ
        if len(self._dead_letter_queue) > 100:
            self._dead_letter_queue.pop(0)

        self.logger.warning(f"Event {event.event_type} moved to DLQ: {error}")

    def get_dead_letter_queue(self) -> list[dict[str, Any]]:
        """Возвращает Dead Letter Queue."""
        return self._dead_letter_queue.copy()

    def clear_dead_letter_queue(self) -> None:
        """Очищает Dead Letter Queue."""
        self._dead_letter_queue.clear()

    def get_event_history(
        self,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """Возвращает историю событий."""
        if event_type:
            filtered = [e for e in self._event_history if e.event_type == event_type]
            return filtered[-limit:]
        return self._event_history[-limit:]

    def clear_history(self) -> None:
        """Очищает историю событий."""
        self._event_history.clear()

    @property
    def subscription_count(self) -> int:
        """Возвращает количество подписок."""
        return sum(len(subs) for subs in self._subscriptions.values())

    @property
    def event_types(self) -> set[str]:
        """Возвращает типы событий с подписчиками."""
        return set(self._subscriptions.keys())


# Глобальный экземпляр шины событий
_global_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Получает глобальную шину событий."""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus


def reset_event_bus() -> None:
    """Сбрасывает глобальную шину событий (для тестов)."""
    global _global_event_bus
    _global_event_bus = None


# Декораторы для удобной подписки
def on_event(event_type: str | type[Event], priority: int = EventPriority.NORMAL):
    """Декоратор для подписки на событие."""

    def decorator(handler: EventHandler) -> EventHandler:
        event_bus = get_event_bus()
        event_bus.subscribe(event_type, handler, priority)
        return handler

    return decorator


def async_on_event(event_type: str | type[Event], priority: int = EventPriority.NORMAL):
    """Декоратор для асинхронной подписки на событие."""

    def decorator(handler: AsyncEventHandler) -> AsyncEventHandler:
        event_bus = get_event_bus()
        event_bus.subscribe(event_type, handler, priority)
        return handler

    return decorator
