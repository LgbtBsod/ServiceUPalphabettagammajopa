"""Order domain service - бизнес-сервис для работы с заказами.

Содержит бизнес-логику, не принадлежащую конкретной сущности.
Использует репозитории для персистентности и события для уведомлений.
"""

from __future__ import annotations

import logging
from typing import Protocol

from ..aggregates import OrderAggregate
from ..entities import Device, OrderStatus
from ..events import OrderCompletedEvent, OrderCreatedEvent, OrderStatusChangedEvent

logger = logging.getLogger(__name__)


class RepositoryProtocol(Protocol):
    """Протокол репозитория для инъекции зависимостей."""

    def get(self, order_id: int) -> Device | None: ...
    def get_by_order_number(self, order_number: str) -> Device | None: ...
    def get_all(self, filters: dict | None = None) -> list[Device]: ...
    def save(self, device: Device) -> Device: ...
    def delete(self, order_id: int) -> bool: ...
    def get_next_order_number(self) -> int: ...


class EventDispatcherProtocol(Protocol):
    """Протокол диспетчера событий для инъекции зависимостей."""

    def dispatch(
        self, event: OrderCreatedEvent | OrderStatusChangedEvent | OrderCompletedEvent
    ) -> None: ...


class OrderService:
    """Сервис для управления заказами.

    Отвечает за:
    - Создание новых заказов
    - Обновление статусов
    - Расчет статистики
    - Бизнес-валидацию
    """

    def __init__(
        self,
        repository: RepositoryProtocol,
        event_dispatcher: EventDispatcherProtocol | None = None,
    ):
        self._repository = repository
        self._event_dispatcher = event_dispatcher

    def create_order(
        self,
        device_type: str,
        brand: str,
        model: str,
        client_name: str,
        phone: str,
        defect: str,
        serial_number: str = "",
        appearance: str = "",
        completeness: str = "",
        notes: str = "",
        priority: str = "Обычный",
    ) -> tuple[bool, OrderAggregate | None, str]:
        """Создание нового заказа.

        Returns:
            Кортеж (успех, заказ или None, сообщение)
        """
        try:
            # Валидация входных данных
            errors = self._validate_order_data(
                device_type=device_type,
                brand=brand,
                client_name=client_name,
                phone=phone,
                defect=defect,
            )

            if errors:
                return False, None, "; ".join(errors)

            # Получение следующего номера заказа
            order_num = self._repository.get_next_order_number()
            order_number = f"{order_num:06d}"

            # Создание агрегата
            aggregate = OrderAggregate.create_new_order(
                device_type=device_type,
                brand=brand,
                model=model,
                client_name=client_name,
                phone=phone,
                defect=defect,
                serial_number=serial_number,
                appearance=appearance,
                completeness=completeness,
                notes=notes,
                priority=priority,
            )

            aggregate.device.order_number = order_number

            # Сохранение в репозиторий
            saved_device = self._repository.save(aggregate.device)
            aggregate.device.id = saved_device.id

            # Публикация события
            if self._event_dispatcher:
                event = OrderCreatedEvent.create(
                    aggregate_id=saved_device.id,
                    order_number=order_number,
                    client_name=client_name,
                    device_type=device_type,
                    brand=brand,
                    model=model,
                )
                self._event_dispatcher.dispatch(event)

            logger.info(f"Создан заказ {order_number} для клиента {client_name}")
            return True, aggregate, f"Заказ {order_number} создан"

        except Exception as e:
            logger.error(f"Ошибка создания заказа: {e}", exc_info=True)
            return False, None, f"Ошибка создания заказа: {e}"

    def update_status(
        self,
        order_id: int,
        new_status: str,
    ) -> tuple[bool, str | None]:
        """Обновление статуса заказа.

        Returns:
            Кортеж (успех, сообщение или ошибка)
        """
        try:
            device = self._repository.get(order_id)
            if not device:
                return False, f"Заказ #{order_id} не найден"

            aggregate = OrderAggregate(device=device)

            old_status = device.status.value

            if not aggregate.update_status(new_status):
                return (
                    False,
                    f"Недопустимый переход статуса: {old_status} -> {new_status}",
                )

            # Сохранение изменений
            self._repository.save(aggregate.device)

            # Публикация события
            if self._event_dispatcher:
                event = OrderStatusChangedEvent.create(
                    aggregate_id=order_id,
                    old_status=old_status,
                    new_status=new_status,
                )
                self._event_dispatcher.dispatch(event)

            logger.info(
                f"Статус заказа #{order_id} изменен: {old_status} -> {new_status}"
            )
            return True, f"Статус изменен на '{new_status}'"

        except Exception as e:
            logger.error(f"Ошибка обновления статуса: {e}", exc_info=True)
            return False, f"Ошибка обновления статуса: {e}"

    def complete_order(
        self,
        order_id: int,
        total_price: float,
        expense: float,
    ) -> tuple[bool, str | None]:
        """Завершение заказа с расчетом прибыли.

        Returns:
            Кортеж (успех, сообщение или ошибка)
        """
        try:
            device = self._repository.get(order_id)
            if not device:
                return False, f"Заказ #{order_id} не найден"

            aggregate = OrderAggregate(device=device)

            if not aggregate.can_be_issued():
                return False, "Заказ не готов к выдаче"

            profit = total_price - expense

            # Публикация события завершения
            if self._event_dispatcher:
                event = OrderCompletedEvent.create(
                    aggregate_id=order_id,
                    total_price=total_price,
                    expense=expense,
                    profit=profit,
                )
                self._event_dispatcher.dispatch(event)

            logger.info(f"Заказ #{order_id} завершен. Прибыль: {profit:.2f}")
            return True, f"Заказ завершен. Прибыль: {profit:.2f}"

        except Exception as e:
            logger.error(f"Ошибка завершения заказа: {e}", exc_info=True)
            return False, f"Ошибка завершения заказа: {e}"

    def get_overdue_orders(self) -> list[OrderAggregate]:
        """Получение просроченных заказов."""
        devices = self._repository.get_all()
        overdue = []

        for device in devices:
            if device.is_overdue and device.status != OrderStatus.ISSUED:
                overdue.append(OrderAggregate(device=device))

        return overdue

    def get_statistics(self, days: int = 30) -> dict:
        """Получение статистики по заказам.

        Args:
            days: Период статистики в днях
        """
        devices = self._repository.get_all()

        total_orders = len(devices)
        completed = sum(1 for d in devices if d.completion_date)
        cancelled = sum(1 for d in devices if d.status == OrderStatus.CANCELLED)
        in_progress = sum(
            1
            for d in devices
            if d.status in [OrderStatus.DIAGNOSTICS, OrderStatus.IN_PROGRESS]
        )

        total_revenue = sum(d.total_price for d in devices if d.completion_date)
        total_expense = sum(d.expense for d in devices if d.completion_date)
        total_profit = total_revenue - total_expense

        avg_repair_time = 0
        completed_devices = [d for d in devices if d.completion_date]
        if completed_devices:
            avg_repair_time = sum(d.days_in_repair for d in completed_devices) / len(
                completed_devices
            )

        return {
            "total_orders": total_orders,
            "completed": completed,
            "cancelled": cancelled,
            "in_progress": in_progress,
            "total_revenue": total_revenue,
            "total_expense": total_expense,
            "total_profit": total_profit,
            "avg_repair_time": avg_repair_time,
            "period_days": days,
        }

    def _validate_order_data(
        self,
        device_type: str,
        brand: str,
        client_name: str,
        phone: str,
        defect: str,
    ) -> list[str]:
        """Валидация данных заказа."""
        errors = []

        if not device_type.strip():
            errors.append("Не указан тип устройства")

        if not client_name.strip():
            errors.append("Не указано имя клиента")

        if not phone.strip():
            errors.append("Не указан телефон клиента")

        if not defect.strip():
            errors.append("Не описана неисправность")

        return errors
