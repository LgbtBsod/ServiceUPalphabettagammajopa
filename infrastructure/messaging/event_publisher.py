"""Event Publisher for Messaging.

Публикация событий в шину событий.
"""

import logging
from typing import Any

from core.base import LoggableMixin
from core.events import Event, EventBus, get_event_bus

logger = logging.getLogger(__name__)


class EventPublisher(LoggableMixin):
    """Публикатор событий.

    Обертка над EventBus для удобной публикации событий
    из инфраструктурного слоя.
    """

    def __init__(self, event_bus: EventBus | None = None):
        super().__init__()
        self._event_bus = event_bus or get_event_bus()
        self.logger.debug("EventPublisher initialized")

    def publish(
        self, event_type: str, data: dict[str, Any], source: str = "infrastructure"
    ) -> None:
        """Публикует событие.

        Args:
            event_type: Тип события
            data: Данные события
            source: Источник события
        """
        event = Event(
            event_type=event_type,
            source=source,
            data=data,
        )

        self.logger.debug(f"Publishing event: {event_type}")
        self._event_bus.publish(event)

    def publish_domain_event(
        self,
        event_type: str,
        aggregate_id: str,
        aggregate_type: str,
        data: dict[str, Any],
    ) -> None:
        """Публикует доменное событие."""
        from core.events import DomainEvent

        event = DomainEvent(
            event_type=event_type,
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            data=data,
        )

        self.logger.debug(
            f"Publishing domain event: {event_type} for {aggregate_type}#{aggregate_id}"
        )
        self._event_bus.publish(event)

    def publish_integration_event(
        self,
        event_type: str,
        data: dict[str, Any],
        correlation_id: str | None = None,
    ) -> None:
        """Публикует интеграционное событие."""
        from core.events import IntegrationEvent

        event = IntegrationEvent(
            event_type=event_type,
            data=data,
            correlation_id=correlation_id,
        )

        self.logger.debug(f"Publishing integration event: {event_type}")
        self._event_bus.publish(event)


# Глобальный экземпляр
_global_publisher: EventPublisher | None = None


def get_event_publisher() -> EventPublisher:
    """Получает глобальный публикатор событий."""
    global _global_publisher
    if _global_publisher is None:
        _global_publisher = EventPublisher()
    return _global_publisher


def reset_event_publisher() -> None:
    """Сбрасывает глобальный публикатор (для тестов)."""
    global _global_publisher
    _global_publisher = None
