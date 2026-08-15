"""Repository для работы с заказами.
Infrastructure слой - реализует контракт IOrderRepository из ядра.

Принципы:
- DIP: Реализует абстракцию из core.contracts
- SRP: Отвечает только за доступ к данным заказов
- Don't Reinvent the Wheel: Использует SQLAlchemy вместо самописных SQL запросов
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.contracts import IOrderRepository, OrderDTO
from features.orders.models import RepairOrder


class SQLAlchemyOrderRepository(IOrderRepository):
    """Реализация репозитория заказов на основе SQLAlchemy.

    Использует Session для управления транзакциями.
    Все методы работают с DTO (Data Transfer Objects).
    """

    def __init__(self, session: Session):
        """Инициализация репозитория.

        Args:
            session: SQLAlchemy сессия для работы с БД.
        """
        self._session = session

    def _model_to_dto(self, model: RepairOrder) -> OrderDTO:
        """Преобразование ORM модели в DTO."""
        return OrderDTO(
            id=model.id,
            order_number=model.order_number,
            client_id=model.client_id,
            status=model.status.value
            if hasattr(model.status, "value")
            else str(model.status),
            priority=model.priority.value
            if hasattr(model.priority, "value")
            else str(model.priority),
            total_amount=model.total_amount or 0.0,
            created_at=model.created_at,
            updated_at=model.updated_at,
            metadata={
                "diagnosis": model.diagnosis,
                "complaint": model.complaint,
                "work_items": model.get_work_items(),
                "parts_used": model.get_parts_used(),
            },
        )

    def get_by_id(self, order_id: int) -> OrderDTO | None:
        """Получить заказ по ID."""
        stmt = select(RepairOrder).where(RepairOrder.id == order_id)
        model = self._session.execute(stmt).scalar_one_or_none()

        if model is None:
            return None

        return self._model_to_dto(model)

    def get_all(self, filters: dict[str, Any] | None = None) -> list[OrderDTO]:
        """Получить все заказы с фильтрацией.

        Args:
            filters: Словарь фильтров:
                - status: фильтр по статусу
                - priority: фильтр по приоритету
                - client_id: фильтр по клиенту
                - date_from: заказы от даты
                - date_to: заказы до даты
        """
        stmt = select(RepairOrder)

        if filters:
            conditions = []

            if filters.get("status"):
                conditions.append(RepairOrder.status == filters["status"])

            if filters.get("priority"):
                conditions.append(RepairOrder.priority == filters["priority"])

            if "client_id" in filters and filters["client_id"] is not None:
                conditions.append(RepairOrder.client_id == filters["client_id"])

            if filters.get("date_from"):
                conditions.append(RepairOrder.created_at >= filters["date_from"])

            if filters.get("date_to"):
                conditions.append(RepairOrder.created_at <= filters["date_to"])

            if conditions:
                stmt = stmt.where(*conditions)

        models = self._session.execute(stmt).scalars().all()
        return [self._model_to_dto(m) for m in models]

    def save(self, dto: OrderDTO) -> OrderDTO:
        """Сохранить заказ (создать или обновить).

        Args:
            dto: DTO заказа для сохранения.

        Returns:
            Сохраненный DTO заказа.
        """
        if dto.id is not None:
            # Обновление существующего
            stmt = select(RepairOrder).where(RepairOrder.id == dto.id)
            model = self._session.execute(stmt).scalar_one_or_none()

            if model is None:
                raise ValueError(f"Order with id {dto.id} not found")

            # Обновление полей
            model.order_number = dto.order_number
            model.client_id = dto.client_id
            model.status = dto.status
            model.priority = dto.priority
            model.total_amount = dto.total_amount

            # Метаданные
            if "diagnosis" in dto.metadata:
                model.diagnosis = dto.metadata["diagnosis"]
            if "complaint" in dto.metadata:
                model.complaint = dto.metadata["complaint"]
            if "work_items" in dto.metadata:
                model.set_work_items(dto.metadata["work_items"])
            if "parts_used" in dto.metadata:
                model.set_parts_used(dto.metadata["parts_used"])

            model.updated_at = func.now()
        else:
            # Создание нового
            model = RepairOrder(
                order_number=dto.order_number,
                client_id=dto.client_id,
                status=dto.status,
                priority=dto.priority,
                total_amount=dto.total_amount,
                diagnosis=dto.metadata.get("diagnosis"),
                complaint=dto.metadata.get("complaint"),
            )

            if "work_items" in dto.metadata:
                model.set_work_items(dto.metadata["work_items"])
            if "parts_used" in dto.metadata:
                model.set_parts_used(dto.metadata["parts_used"])

            self._session.add(model)

        self._session.commit()
        self._session.refresh(model)

        return self._model_to_dto(model)

    def delete(self, order_id: int) -> bool:
        """Удалить заказ по ID.

        Args:
            order_id: ID заказа для удаления.

        Returns:
            True если удалено, False если не найдено.
        """
        stmt = select(RepairOrder).where(RepairOrder.id == order_id)
        model = self._session.execute(stmt).scalar_one_or_none()

        if model is None:
            return False

        self._session.delete(model)
        self._session.commit()
        return True

    def count(self, filters: dict[str, Any] | None = None) -> int:
        """Подсчет заказов с фильтрацией."""
        stmt = select(func.count()).select_from(RepairOrder)

        if filters:
            conditions = []

            if filters.get("status"):
                conditions.append(RepairOrder.status == filters["status"])

            if "client_id" in filters and filters["client_id"] is not None:
                conditions.append(RepairOrder.client_id == filters["client_id"])

            if conditions:
                stmt = stmt.where(*conditions)

        return self._session.execute(stmt).scalar() or 0
