"""Domain aggregates - агрегаты доменных сущностей.

Агрегаты обеспечивают целостность бизнес-транзакций и инкапсулируют
бизнес-логику работы с группами связанных сущностей.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .entities import Client, Device, FinanceRecord, Photo, RepairHistory, WorkItem


@dataclass(slots=True)
class OrderAggregate:
    """Агрегат заказа - объединяет устройство, клиента и историю ремонтов.

    Отвечает за:
    - Целостность данных заказа
    - Бизнес-правила создания/изменения заказа
    - Расчеты стоимости и прибыли
    - Валидацию статусов
    """

    device: Device
    client: Client | None = None
    history: list[RepairHistory] = field(default_factory=list)

    @classmethod
    def create_new_order(
        cls,
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
    ) -> OrderAggregate:
        """Создание нового заказа."""
        from .entities import OrderStatus, Priority

        device = Device(
            device_type=device_type,
            brand=brand,
            model=model,
            serial_number=serial_number,
            defect=defect,
            appearance=appearance,
            completeness=completeness,
            client_name=client_name,
            phone=phone,
            notes=notes,
            priority=Priority(priority),
            status=OrderStatus.DIAGNOSTICS,
        )

        return cls(device=device)

    def add_work_item(self, description: str, price: float, quantity: int = 1) -> None:
        """Добавление работы в заказ."""
        work_item = WorkItem(
            description=description,
            price=price,
            quantity=quantity,
        )
        self.device.add_work_item(work_item)

    def remove_work_item(self, index: int) -> None:
        """Удаление работы из заказа."""
        self.device.remove_work_item(index)

    def update_status(self, new_status: str) -> bool:
        """Обновление статуса заказа с проверкой бизнес-правил.

        Правила:
        - Нельзя изменить статус выданного заказа
        - Нельзя пропустить обязательные этапы
        """
        from .entities import OrderStatus

        if self.device.status == OrderStatus.ISSUED:
            return False  # Выданный заказ нельзя изменять

        try:
            new_status_enum = OrderStatus(new_status)
        except ValueError:
            return False

        # Проверка допустимых переходов
        allowed_transitions = {
            OrderStatus.DIAGNOSTICS: [
                OrderStatus.WAITING_PARTS,
                OrderStatus.IN_PROGRESS,
                OrderStatus.CANCELLED,
            ],
            OrderStatus.WAITING_PARTS: [OrderStatus.IN_PROGRESS, OrderStatus.CANCELLED],
            OrderStatus.IN_PROGRESS: [OrderStatus.READY, OrderStatus.CANCELLED],
            OrderStatus.READY: [OrderStatus.ISSUED],
            OrderStatus.ISSUED: [],
            OrderStatus.CANCELLED: [],
        }

        if new_status_enum not in allowed_transitions.get(self.device.status, []):
            return False

        self.device.status = new_status_enum

        if new_status_enum == OrderStatus.READY:
            self.device.completion_date = datetime.now()

        return True

    def calculate_total(self) -> float:
        """Расчет общей стоимости заказа."""
        return sum(wi.total for wi in self.device.work_items)

    def calculate_profit(self) -> float:
        """Расчет прибыли."""
        return self.device.total_price - self.device.expense

    def add_photo(
        self, file_path: str, filename: str, photo_type: str = "device"
    ) -> None:
        """Добавление фотографии."""
        photo = Photo(
            file_path=file_path,
            filename=filename,
            photo_type=photo_type,
            sort_order=len(self.device.photos),
        )
        self.device.photos.append(photo)

    def remove_photo(self, index: int) -> None:
        """Удаление фотографии."""
        if 0 <= index < len(self.device.photos):
            self.device.photos.pop(index)
            # Пересчитываем sort_order
            for i, photo in enumerate(self.device.photos):
                photo.sort_order = i

    def to_finance_record(self) -> FinanceRecord | None:
        """Создание финансовой записи из заказа (при завершении)."""
        if not self.device.completion_date:
            return None

        return FinanceRecord(
            order_number=self.device.order_number or "",
            completion_date=self.device.completion_date,
            income=self.device.total_price,
            expense=self.device.expense,
        )

    def validate(self) -> list[str]:
        """Валидация заказа.

        Returns:
            Список ошибок валидации (пустой если все корректно)
        """
        errors = []

        if not self.device.client_name.strip():
            errors.append("Не указано имя клиента")

        if not self.device.phone.strip():
            errors.append("Не указан телефон клиента")

        if not self.device.device_type.strip():
            errors.append("Не указан тип устройства")

        if not self.device.defect.strip():
            errors.append("Не описана неисправность")

        if self.device.total_price < 0:
            errors.append("Отрицательная стоимость работ")

        if self.device.expense < 0:
            errors.append("Отрицательные расходы")

        return errors

    def can_be_issued(self) -> bool:
        """Проверка возможности выдачи заказа."""
        from .entities import OrderStatus

        return (
            self.device.status == OrderStatus.READY
            and self.device.total_price > 0
            and self.device.client_name.strip()
            and self.device.phone.strip()
        )

    def get_summary(self) -> dict[str, Any]:
        """Получение сводной информации по заказу."""
        return {
            "order_number": self.device.order_number,
            "status": self.device.status.value,
            "client": self.device.client_name,
            "device": f"{self.device.device_type} {self.device.brand} {self.device.model}",
            "total_price": self.device.total_price,
            "expense": self.device.expense,
            "profit": self.calculate_profit(),
            "days_in_repair": self.device.days_in_repair,
            "is_overdue": self.device.is_overdue,
            "work_items_count": len(self.device.work_items),
            "photos_count": len(self.device.photos),
        }
