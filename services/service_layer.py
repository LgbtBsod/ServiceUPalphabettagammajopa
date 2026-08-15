#!/usr/bin/env python3

"""Сервисный слой для бизнес-логики с использованием Factory паттерна.

Отделяет бизнес-правила от слоя доступа к данным (Repositories) и слоя представления (GUI/API).
Соблюдает принципы SOLID, особенно Single Responsibility Principle (SRP) и Dependency Injection.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, TypeVar

from database.factories import get_database_factory
from database.repositories.unit_of_work import UnitOfWork
from models.pydantic_models import (
    Client,
    Order,
    OrderStatus,
    Priority,
    WorkItem,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BaseService[T]:
    """Базовый класс для всех сервисов.

    Предоставляет общую функциональность для CRUD операций.
    Использует Dependency Injection через фабрику базы данных.
    """

    def __init__(self, factory=None):
        """Инициализация сервиса.

        Args:
            factory: Фабрика базы данных или callable для получения UnitOfWork.
                    Если не указана, используется глобальная фабрика.
        """
        self._factory = factory or get_database_factory()

    def _get_uow(self) -> UnitOfWork:
        """Получение нового Unit of Work для транзакций."""
        # Поддержка как фабрики с методом create_unit_of_work, так и callable
        if callable(self._factory) and not hasattr(
            self._factory, "create_unit_of_work"
        ):
            return self._factory()
        return self._factory.create_unit_of_work()


class OrderService(BaseService[Order]):
    """Сервис для управления заказами.

    Инкапсулирует бизнес-логику работы с заказами:
    - Создание заказов с автоматической нумерацией
    - Расчет стоимости
    - Управление статусами
    - Поиск и фильтрация
    """

    def create_order(self, order_data: dict[str, Any]) -> Order:
        """Создание нового заказа.

        Бизнес-правила:
        - Автоматическая генерация номера заказа
        - Установка статуса по умолчанию
        - Валидация данных через Pydantic

        Args:
            order_data: Данные заказа.

        Returns:
            Созданный объект Order.

        Raises:
            ValueError: При некорректных данных.
        """
        with self._get_uow() as uow:
            # Генерация номера заказа
            order_number = self._generate_order_number(uow)
            order_data["order_number"] = order_number

            # Установка значений по умолчанию
            if "status" not in order_data:
                order_data["status"] = OrderStatus.DIAGNOSTICS.value
            if "priority" not in order_data:
                order_data["priority"] = Priority.NORMAL.value
            if "receipt_date" not in order_data:
                order_data["receipt_date"] = datetime.now().isoformat()

            # Создание записи в БД
            device_repo = uow.devices
            created_device = device_repo.create(order_data)

            # Конвертация в Pydantic модель
            order = self._device_to_order(created_device)

            logger.info(f"Создан заказ №{order.order_number}")
            return order

    def get_order(self, order_id: int) -> Order | None:
        """Получение заказа по ID.

        Args:
            order_id: Идентификатор заказа.

        Returns:
            Объект Order или None.
        """
        with self._get_uow() as uow:
            device = uow.devices.get(order_id)
            return self._device_to_order(device) if device else None

    def get_order_by_number(self, order_number: str) -> Order | None:
        """Получение заказа по номеру.

        Args:
            order_number: Номер заказа.

        Returns:
            Объект Order или None.
        """
        with self._get_uow() as uow:
            device = uow.devices.get_by_order_number(order_number)
            return self._device_to_order(device) if device else None

    def update_order_status(self, order_id: int, status: OrderStatus) -> Order | None:
        """Обновление статуса заказа.

        Бизнес-правила:
        - Нельзя выдать отказанный заказ
        - При установке статуса "Готов к выдаче" фиксируется дата готовности

        Args:
            order_id: Идентификатор заказа.
            status: Новый статус.

        Returns:
            Обновленный объект Order.
        """
        with self._get_uow() as uow:
            order = self.get_order(order_id)
            if not order:
                return None

            # Проверка бизнес-правил
            if (
                order.status == OrderStatus.REFUSED.value
                and status != OrderStatus.REFUSED
            ):
                raise ValueError("Нельзя изменить статус отказанного заказа")

            update_data = {"status": status.value}

            if status == OrderStatus.READY and not order.ready_date:
                update_data["ready_date"] = datetime.now().isoformat()

            updated_device = uow.devices.update(order_id, update_data)
            logger.info(
                f"Заказ №{order.order_number}: статус изменен на {status.value}"
            )

            return self._device_to_order(updated_device) if updated_device else None

    def add_work_item(self, order_id: int, work_item: WorkItem) -> Order | None:
        """Добавление работы к заказу.

        Args:
            order_id: Идентификатор заказа.
            work_item: Работа для добавления.

        Returns:
            Обновленный объект Order.
        """
        with self._get_uow() as uow:
            order = self.get_order(order_id)
            if not order:
                return None

            # Получение текущих работ
            current_works = uow.devices.get_work_items(order_id)

            # Добавление новой работы
            work_dict = work_item.model_dump(mode="json")
            current_works.append(work_dict)

            # Обновление в БД
            updated_device = uow.devices.update_work_items(order_id, current_works)

            logger.info(
                f"Заказ №{order.order_number}: добавлена работа '{work_item.name}'"
            )
            return self._device_to_order(updated_device) if updated_device else None

    def search_orders(self, query: str) -> list[Order]:
        """Поиск заказов по строке.

        Args:
            query: Строка поиска.

        Returns:
            Список найденных заказов.
        """
        with self._get_uow() as uow:
            devices = uow.devices.search(query)
            return [self._device_to_order(d) for d in devices]

    def get_overdue_orders(self, days: int = 14) -> list[Order]:
        """Получение просроченных заказов.

        Args:
            days: Количество дней для проверки.

        Returns:
            Список просроченных заказов.
        """
        with self._get_uow() as uow:
            all_devices = uow.devices.get_all()
            overdue = []

            for device in all_devices:
                order = self._device_to_order(device)
                if order.days_in_service > days:
                    overdue.append(order)

            return overdue

    def _generate_order_number(self, uow: UnitOfWork) -> str:
        """Генерация уникального номера заказа."""
        count = uow.devices.count()
        return f"{count + 1:05d}"

    def _device_to_order(self, device: Any) -> Order:
        """Конвертация устройства из БД в модель Order."""
        # Обработка разных типов устройств
        if hasattr(device, "__dict__") and hasattr(device, "_fields"):
            # namedtuple или похожий объект
            device_dict = (
                device._asdict() if hasattr(device, "_asdict") else vars(device)
            )
        elif hasattr(device, "model_dump"):
            # Pydantic модель
            device_dict = device.model_dump(mode="python")
        elif hasattr(device, "__dict__"):
            # Обычный объект с __dict__
            device_dict = vars(device)
        elif isinstance(device, dict):
            device_dict = device
        else:
            # Пробуем преобразовать через dict()
            try:
                device_dict = dict(device)
            except (TypeError, ValueError):
                device_dict = vars(device) if hasattr(device, "__dict__") else {}

        # Парсинг цен
        diagnostic_cost = self._parse_price(device_dict.get("diagnostic_cost", "0"))
        repair_cost = self._parse_price(device_dict.get("repair_cost", "0"))

        receipt_date_val = device_dict.get("receipt_date")
        ready_date_val = device_dict.get("ready_date")

        return Order(
            id=device_dict.get("id"),
            order_number=device_dict.get("order_number", ""),
            device_type=device_dict.get("device_type", "other"),
            brand=device_dict.get("brand", ""),
            model=device_dict.get("model", ""),
            serial_number=device_dict.get("serial_number"),
            defects=device_dict.get("defect", ""),
            appearance=device_dict.get("appearance"),
            completeness=device_dict.get("completeness"),
            status=device_dict.get("status", "Диагностика"),
            priority=device_dict.get("priority", "Обычный"),
            diagnostic_cost=diagnostic_cost,
            repair_cost=repair_cost,
            total_cost=(diagnostic_cost or 0) + (repair_cost or 0),
            receipt_date=datetime.fromisoformat(receipt_date_val)
            if receipt_date_val
            else datetime.now(),
            ready_date=datetime.fromisoformat(ready_date_val)
            if ready_date_val
            else None,
            engineer=device_dict.get("engineer"),
            warranty=device_dict.get("warranty"),
            notes=device_dict.get("notes"),
        )

    def _parse_price(self, value: Any) -> Decimal | None:
        """Парсинг цены из различных форматов."""
        if value is None or value == "":
            return None
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value).replace(",", ".").replace(" ", ""))
        except Exception:
            return None


class ClientService(BaseService[Client]):
    """Сервис для управления клиентами.

    Бизнес-логика:
    - Валидация телефонов
    - Статистика клиентов
    - Поиск дубликатов
    """

    def create_client(self, client_data: dict[str, Any]) -> Client:
        """Создание нового клиента.

        Args:
            client_data: Данные клиента.

        Returns:
            Созданный объект Client.
        """
        with self._get_uow() as uow:
            # Проверка на дубликат по телефону
            phone = client_data.get("phone", "")
            existing = uow.clients.get_by_phone(phone)

            if existing:
                logger.warning(f"Клиент с телефоном {phone} уже существует")
                return self._dict_to_client(existing)

            # Создание клиента
            created_client = uow.clients.create(client_data)
            logger.info(f"Создан клиент: {client_data.get('full_name', 'Unknown')}")

            return self._dict_to_client(created_client)

    def get_client_by_phone(self, phone: str) -> Client | None:
        """Получение клиента по телефону.

        Args:
            phone: Телефон клиента.

        Returns:
            Объект Client или None.
        """
        with self._get_uow() as uow:
            client_dict = uow.clients.get_by_phone(phone)
            return self._dict_to_client(client_dict) if client_dict else None

    def search_clients(self, query: str) -> list[Client]:
        """Поиск клиентов по имени или телефону.

        Args:
            query: Строка поиска.

        Returns:
            Список найденных клиентов.
        """
        with self._get_uow() as uow:
            clients = uow.clients.search(query)
            return [self._dict_to_client(c) for c in clients]

    def update_client_stats(self, client_id: int) -> Client | None:
        """Обновление статистики клиента на основе заказов.

        Бизнес-правила:
        - Подсчет общего количества заказов
        - Подсчет завершенных заказов
        - Расчет общей суммы

        Args:
            client_id: Идентификатор клиента.

        Returns:
            Обновленный объект Client.
        """
        with self._get_uow() as uow:
            # Получение всех заказов клиента
            orders = uow.devices.get_all({"client_id": client_id})

            total_orders = len(orders)
            completed_orders = sum(
                1 for o in orders if dict(o).get("status") == OrderStatus.ISSUED.value
            )

            # Расчет общей суммы из завершенных заказов
            total_spent = 0.0
            last_order_date = None

            for order in orders:
                order_dict = dict(order) if hasattr(order, "__dict__") else order
                # Считаем только завершенные заказы
                if order_dict.get("status") == OrderStatus.ISSUED.value:
                    # Берем total_price или сумму diagnostic_cost + repair_cost
                    total_price_val = order_dict.get("total_price", "0") or "0"
                    with contextlib.suppress(ValueError, TypeError):
                        total_spent += float(
                            str(total_price_val).replace(",", ".").strip() or 0
                        )

                # Получение даты последнего заказа
                receipt_date = order_dict.get("receipt_date")
                if receipt_date:
                    if last_order_date is None or receipt_date > last_order_date:
                        last_order_date = receipt_date

            # Обновление статистики
            updated_client = uow.clients.update_stats(
                client_id=client_id,
                total_orders=total_orders,
                completed_orders=completed_orders,
                total_spent=total_spent,
                last_order_date=last_order_date,
            )

            logger.info(
                f"Обновлена статистика клиента ID={client_id}: сумма={total_spent}"
            )
            return self._dict_to_client(updated_client) if updated_client else None

    def _dict_to_client(self, client_dict: dict[str, Any]) -> Client:
        """Конвертация словаря из БД в модель Client."""
        full_name = client_dict.get("name", "") or client_dict.get("full_name", "")

        return Client(
            id=client_dict.get("id"),
            full_name=full_name or "Неизвестный клиент",
            phone=client_dict.get("phone", ""),
            email=client_dict.get("email"),
            status=client_dict.get("status", "Новый"),
            notes=client_dict.get("notes"),
        )


# Factory для создания сервисов
def create_services(factory=None) -> dict[str, BaseService]:
    """Фабрика для создания сервисов.

    Args:
        factory: Фабрика базы данных. Если не указана, используется глобальная.

    Returns:
        Словарь с сервисами.
    """
    db_factory = factory or get_database_factory()
    return {
        "orders": OrderService(db_factory),
        "clients": ClientService(db_factory),
    }
