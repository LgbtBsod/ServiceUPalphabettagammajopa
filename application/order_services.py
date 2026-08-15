"""Order Application Services - Use Cases для управления заказами.

Следует принципам:
- SRP: каждый метод решает одну задачу
- CQRS: разделение команд (создание, обновление) и запросов (поиск, получение)
- Transaction Script: управление транзакциями через Unit of Work
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from domain.services import NotificationService, OrderService
from shared.kernel import MoneyValue, OrderStatus, Priority, UnitOfWork

logger = logging.getLogger(__name__)


class UnitOfWorkFactory(Protocol):
    """Протокол фабрики Unit of Work."""

    def __call__(self) -> UnitOfWork: ...


@dataclass(slots=True)
class OrderCreateResult:
    """Результат создания заказа."""

    order_id: int
    order_number: str
    success: bool
    message: str = ""


@dataclass(slots=True)
class OrderSearchResult:
    """Результат поиска заказов."""

    orders: list[dict[str, Any]]
    total_count: int
    page: int = 1
    page_size: int = 20


class OrderAppService:
    """Сервис приложения для управления заказами.

    Координирует работу доменных сервисов и репозиториев.
    Не содержит бизнес-логики предметной области - делегирует доменным сервисам.
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        order_service: OrderService,
        notification_service: NotificationService,
        max_workers: int = 4,
    ):
        self._uow_factory = uow_factory
        self._order_service = order_service
        self._notification_service = notification_service
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def create_order(self, order_data: dict[str, Any]) -> OrderCreateResult:
        """Создание нового заказа (Use Case).

        Бизнес-процесс:
        1. Валидация данных
        2. Генерация номера заказа
        3. Сохранение в БД (транзакция)
        4. Отправка уведомления клиенту

        Args:
            order_data: Данные заказа.

        Returns:
            Результат создания заказа.
        """
        try:
            # Делегируем доменному сервису
            created_order = self._order_service.create(order_data)

            # Асинхронная отправка уведомления (не блокируем основной поток)
            self._executor.submit(self._send_order_created_notification, created_order)

            return OrderCreateResult(
                order_id=created_order.get("id", 0),
                order_number=created_order.get("order_number", ""),
                success=True,
                message="Заказ успешно создан",
            )

        except ValueError as e:
            logger.warning(f"Валидация заказа не пройдена: {e}")
            return OrderCreateResult(
                order_id=0, order_number="", success=False, message=str(e)
            )
        except Exception as e:
            logger.error(f"Ошибка создания заказа: {e}", exc_info=True)
            return OrderCreateResult(
                order_id=0,
                order_number="",
                success=False,
                message=f"Ошибка сервера: {e}",
            )

    def get_order_by_id(self, order_id: int) -> dict[str, Any] | None:
        """Получение заказа по ID (Query)."""
        with self._uow_factory() as uow:
            return uow.devices.get_by_id(order_id)

    def search_orders(
        self,
        query: str | None = None,
        status: OrderStatus | None = None,
        priority: Priority | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> OrderSearchResult:
        """Поиск заказов с фильтрацией и пагинацией (Query).

        Args:
            query: Поисковый запрос (клиент, устройство, номер).
            status: Фильтр по статусу.
            priority: Фильтр по приоритету.
            date_from: Дата создания от.
            date_to: Дата создания до.
            page: Номер страницы.
            page_size: Размер страницы.

        Returns:
            Результаты поиска с мета-информацией.
        """
        with self._uow_factory() as uow:
            # Делегируем репозиторию
            orders, total = uow.devices.search(
                query=query,
                status=status.value if status else None,
                priority=priority.value if priority else None,
                date_from=date_from,
                date_to=date_to,
                offset=(page - 1) * page_size,
                limit=page_size,
            )

            return OrderSearchResult(
                orders=orders,
                total_count=total,
                page=page,
                page_size=page_size,
            )

    def update_order_status(self, order_id: int, new_status: OrderStatus) -> bool:
        """Обновление статуса заказа (Command).

        Бизнес-процесс:
        1. Проверка допустимости перехода статуса
        2. Обновление в БД (транзакция)
        3. Отправка уведомления клиенту

        Args:
            order_id: ID заказа.
            new_status: Новый статус.

        Returns:
            True если успешно, иначе False.
        """
        try:
            with self._uow_factory() as uow:
                order = uow.devices.get_by_id(order_id)
                if not order:
                    logger.warning(f"Заказ {order_id} не найден")
                    return False

                # Делегируем доменному сервису проверку переходов
                self._order_service.validate_status_transition(
                    order.get("status"), new_status.value
                )

                # Обновляем статус
                order["status"] = new_status.value
                order["updated_at"] = datetime.now().isoformat()
                uow.devices.update(order)

                # Асинхронное уведомление
                self._executor.submit(
                    self._send_status_change_notification, order, new_status
                )

                return True

        except ValueError as e:
            logger.warning(f"Недопустимый переход статуса: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка обновления статуса: {e}", exc_info=True)
            return False

    def calculate_order_total(self, order_id: int) -> MoneyValue:
        """Расчет полной стоимости заказа (Query).

        Суммирует:
        - Работы
        - Запчасти
        - Дополнительные услуги

        Args:
            order_id: ID заказа.

        Returns:
            Полную стоимость заказа.
        """
        with self._uow_factory() as uow:
            order = uow.devices.get_by_id(order_id)
            if not order:
                return MoneyValue.zero()

            # Делегируем доменному сервису
            total = self._order_service.calculate_total(order)
            return MoneyValue(total)

    def _send_order_created_notification(self, order: dict[str, Any]) -> None:
        """Отправляет уведомление о создании заказа."""
        try:
            client_phone = order.get("client_phone")
            order_number = order.get("order_number")

            if client_phone and order_number:
                message = f"Ваш заказ {order_number} принят в работу."
                self._notification_service.send_sms(client_phone, message)
        except Exception as e:
            logger.exception(f"Ошибка отправки уведомления: {e}")

    def _send_status_change_notification(
        self,
        order: dict[str, Any],
        new_status: OrderStatus,
    ) -> None:
        """Отправляет уведомление об изменении статуса."""
        try:
            client_phone = order.get("client_phone")
            order_number = order.get("order_number")

            if client_phone:
                message = (
                    f"Заказ {order_number}: статус изменен на '{new_status.value}'"
                )
                self._notification_service.send_sms(client_phone, message)
        except Exception as e:
            logger.exception(f"Ошибка отправки уведомления: {e}")

    def shutdown(self) -> None:
        """Корректное завершение работы сервиса."""
        self._executor.shutdown(wait=True)
