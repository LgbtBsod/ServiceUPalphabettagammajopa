"""
Система событий приложения (Event Bus).
Реализует паттерн Observer для слабой связанности компонентов.
Поддерживает асинхронную обработку и фильтрацию событий.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Callable, Any, Optional, TypeVar, Generic
from collections import defaultdict

from shared.logging_config import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


class EventType(Enum):
    """Типы событий в системе."""
    # Заказы
    ORDER_CREATED = auto()
    ORDER_UPDATED = auto()
    ORDER_STATUS_CHANGED = auto()
    ORDER_DELETED = auto()
    
    # Клиенты
    CLIENT_CREATED = auto()
    CLIENT_UPDATED = auto()
    
    # Уведомления
    NOTIFICATION_SENT = auto()
    NOTIFICATION_FAILED = auto()
    
    # Система
    APP_STARTED = auto()
    APP_SHUTDOWN = auto()
    CONFIG_RELOADED = auto()
    
    # UI
    UI_REFRESH_REQUESTED = auto()
    DATA_LOADED = auto()


@dataclass(frozen=True)
class Event(Generic[T]):
    """Базовый класс события."""
    type: EventType
    payload: T
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "unknown"
    
    def __str__(self) -> str:
        return f"Event({self.type.name}, source={self.source})"


EventHandler = Callable[[Event[Any]], None]
AsyncEventHandler = Callable[[Event[Any]], asyncio.Future]


class EventBus:
    """
    Шина событий (Event Bus).
    Реализует паттерн Mediator для коммуникации между компонентами.
    """
    
    def __init__(self) -> None:
        self._handlers: Dict[EventType, List[Callable]] = defaultdict(list)
        self._async_handlers: Dict[EventType, List[Callable]] = defaultdict(list)
        self._event_history: List[Event] = []
        self._max_history = 100
        self._running = False
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        
    def subscribe(
        self, 
        event_type: EventType, 
        handler: EventHandler | AsyncEventHandler
    ) -> None:
        """
        Подписка на событие.
        Автоматически определяет синхронный или асинхронный хендлер.
        """
        if asyncio.iscoroutinefunction(handler):
            self._async_handlers[event_type].append(handler)
            logger.debug(f"Subscribed async handler for {event_type.name}")
        else:
            self._handlers[event_type].append(handler)
            logger.debug(f"Subscribed sync handler for {event_type.name}")
    
    def unsubscribe(
        self, 
        event_type: EventType, 
        handler: EventHandler | AsyncEventHandler
    ) -> None:
        """Отписка от события."""
        if asyncio.iscoroutinefunction(handler):
            if handler in self._async_handlers[event_type]:
                self._async_handlers[event_type].remove(handler)
        else:
            if handler in self._handlers[event_type]:
                self._handlers[event_type].remove(handler)
    
    async def publish(self, event: Event[Any]) -> None:
        """
        Публикация события в шину.
        Асинхронно распределяет событие всем подписчикам.
        """
        logger.debug(f"Publishing event: {event}")
        
        # Сохранение в историю
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)
        
        # Обработка синхронных хендлеров в пуле потоков
        sync_handlers = self._handlers.get(event.type, [])
        if sync_handlers:
            loop = asyncio.get_event_loop()
            for handler in sync_handlers:
                try:
                    await loop.run_in_executor(None, handler, event)
                except Exception as e:
                    logger.error(f"Error in sync handler for {event.type.name}: {e}")
        
        # Обработка асинхронных хендлеров
        async_handlers = self._async_handlers.get(event.type, [])
        if async_handlers:
            tasks = [handler(event) for handler in async_handlers]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(
                        f"Error in async handler {async_handlers[i].__name__} "
                        f"for {event.type.name}: {result}"
                    )
    
    async def start(self) -> None:
        """Запуск обработчика очереди событий."""
        if self._running:
            return
            
        self._running = True
        self._worker_task = asyncio.create_task(self._process_queue())
        logger.info("Event bus started")
    
    async def stop(self) -> None:
        """Остановка обработчика очереди событий."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Event bus stopped")
    
    async def _process_queue(self) -> None:
        """Обработчик очереди событий (фоновая задача)."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self.publish(event)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing event queue: {e}")
    
    async def publish_queued(self, event: Event[Any]) -> None:
        """Публикация события через очередь (неблокирующая)."""
        await self._queue.put(event)
    
    def get_history(self, event_type: Optional[EventType] = None) -> List[Event]:
        """Получение истории событий с фильтрацией."""
        if event_type is None:
            return list(self._event_history)
        return [e for e in self._event_history if e.type == event_type]
    
    def clear_history(self) -> None:
        """Очистка истории событий."""
        self._event_history.clear()


# Глобальный экземпляр (Singleton)
_event_bus_instance: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Получение глобального экземпляра шины событий."""
    global _event_bus_instance
    if _event_bus_instance is None:
        _event_bus_instance = EventBus()
    return _event_bus_instance
