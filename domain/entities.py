"""Domain entities - бизнес-сущности приложения.

Все сущности реализованы через dataclasses для Python 3.14.
Следуют принципам DDD (Domain-Driven Design).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class OrderStatus(StrEnum):
    """Статусы заказа."""

    DIAGNOSTICS = "Диагностика"
    WAITING_PARTS = "Ожидание запчастей"
    IN_PROGRESS = "В работе"
    READY = "Готов"
    ISSUED = "Выдан"
    CANCELLED = "Отменен"


class Priority(StrEnum):
    """Приоритеты заказа."""

    LOW = "Низкий"
    NORMAL = "Обычный"
    HIGH = "Срочный"
    CRITICAL = "Критический"


@dataclass(slots=True, frozen=False)
class WorkItem:
    """Элемент работы в заказе."""

    description: str
    price: float
    quantity: int = 1
    total: float = field(init=False)
    sort_order: int = 0

    def __post_init__(self):
        object.__setattr__(self, "total", self.price * self.quantity)

    def to_dict(self) -> dict[str, Any]:
        """Сериализация в dict."""
        return {
            "description": self.description,
            "price": self.price,
            "quantity": self.quantity,
            "total": self.total,
            "sort_order": self.sort_order,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkItem:
        """Десериализация из dict."""
        return cls(
            description=data["description"],
            price=float(data.get("price", 0)),
            quantity=int(data.get("quantity", 1)),
            sort_order=int(data.get("sort_order", 0)),
        )


@dataclass(slots=True, frozen=False)
class Photo:
    """Фотография устройства."""

    file_path: str
    filename: str
    photo_type: str = "device"  # device, client, defect
    sort_order: int = 0
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Сериализация в dict."""
        return {
            "file_path": self.file_path,
            "filename": self.filename,
            "photo_type": self.photo_type,
            "sort_order": self.sort_order,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Photo:
        """Десериализация из dict."""
        return cls(
            file_path=data["file_path"],
            filename=data["filename"],
            photo_type=data.get("photo_type", "device"),
            sort_order=data.get("sort_order", 0),
            created_at=datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.now(),
        )


@dataclass(slots=True, frozen=False)
class Device:
    """Устройство в ремонте."""

    id: int | None = None
    order_number: str | None = None
    receipt_date: datetime = field(default_factory=datetime.now)
    completion_date: datetime | None = None
    device_type: str = ""
    brand: str = ""
    model: str = ""
    serial_number: str = ""
    defect: str = ""
    appearance: str = ""
    completeness: str = ""
    work_items: list[WorkItem] = field(default_factory=list)
    client_name: str = ""
    client_status: str = "Новый"
    phone: str = ""
    total_price: float = 0.0
    prepayment: float = 0.0
    status: OrderStatus = OrderStatus.DIAGNOSTICS
    priority: Priority = Priority.NORMAL
    engineer: str = ""
    warranty: str = ""
    notes: str = ""
    photos: list[Photo] = field(default_factory=list)
    expense: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def profit(self) -> float:
        """Расчет прибыли."""
        return self.total_price - self.expense

    @property
    def is_overdue(self) -> bool:
        """Проверка на просрочку (более 14 дней в ремонте)."""
        if not self.receipt_date or self.completion_date:
            return False
        return (datetime.now() - self.receipt_date).days > 14

    @property
    def days_in_repair(self) -> int:
        """Количество дней в ремонте."""
        if self.completion_date:
            return (self.completion_date - self.receipt_date).days
        return (datetime.now() - self.receipt_date).days

    def add_work_item(self, work_item: WorkItem) -> None:
        """Добавление элемента работы."""
        self.work_items.append(work_item)
        self._recalculate_total()

    def remove_work_item(self, index: int) -> None:
        """Удаление элемента работы по индексу."""
        if 0 <= index < len(self.work_items):
            self.work_items.pop(index)
            self._recalculate_total()

    def _recalculate_total(self) -> None:
        """Пересчет общей стоимости работ."""
        self.total_price = sum(wi.total for wi in self.work_items)

    def to_dict(self) -> dict[str, Any]:
        """Сериализация в dict."""
        return {
            "id": self.id,
            "order_number": self.order_number,
            "receipt_date": self.receipt_date.isoformat()
            if self.receipt_date
            else None,
            "completion_date": self.completion_date.isoformat()
            if self.completion_date
            else None,
            "device_type": self.device_type,
            "brand": self.brand,
            "model": self.model,
            "serial_number": self.serial_number,
            "defect": self.defect,
            "appearance": self.appearance,
            "completeness": self.completeness,
            "work_items": [wi.to_dict() for wi in self.work_items],
            "client_name": self.client_name,
            "client_status": self.client_status,
            "phone": self.phone,
            "total_price": self.total_price,
            "prepayment": self.prepayment,
            "status": self.status.value,
            "priority": self.priority.value,
            "engineer": self.engineer,
            "warranty": self.warranty,
            "notes": self.notes,
            "photos": [p.to_dict() for p in self.photos],
            "expense": self.expense,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Device:
        """Десериализация из dict."""
        work_items = [WorkItem.from_dict(wi) for wi in data.get("work_items", [])]
        photos = [Photo.from_dict(p) for p in data.get("photos", [])]

        return cls(
            id=data.get("id"),
            order_number=data.get("order_number"),
            receipt_date=datetime.fromisoformat(data["receipt_date"])
            if data.get("receipt_date")
            else datetime.now(),
            completion_date=datetime.fromisoformat(data["completion_date"])
            if data.get("completion_date")
            else None,
            device_type=data.get("device_type", ""),
            brand=data.get("brand", ""),
            model=data.get("model", ""),
            serial_number=data.get("serial_number", ""),
            defect=data.get("defect", ""),
            appearance=data.get("appearance", ""),
            completeness=data.get("completeness", ""),
            work_items=work_items,
            client_name=data.get("client_name", ""),
            client_status=data.get("client_status", "Новый"),
            phone=data.get("phone", ""),
            total_price=float(data.get("total_price", 0)),
            prepayment=float(data.get("prepayment", 0)),
            status=OrderStatus(data.get("status", "Диагностика")),
            priority=Priority(data.get("priority", "Обычный")),
            engineer=data.get("engineer", ""),
            warranty=data.get("warranty", ""),
            notes=data.get("notes", ""),
            photos=photos,
            expense=float(data.get("expense", 0)),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else datetime.now(),
        )


@dataclass(slots=True, frozen=False)
class Client:
    """Клиент сервисного центра."""

    id: int | None = None
    name: str = ""
    phone: str = ""
    status: str = "Новый"
    total_orders: int = 0
    completed_orders: int = 0
    total_spent: float = 0.0
    first_order_date: datetime | None = None
    last_order_date: datetime | None = None
    favorite_device: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def avg_order_value(self) -> float:
        """Средняя стоимость заказа."""
        if self.total_orders == 0:
            return 0.0
        return self.total_spent / self.total_orders

    def to_dict(self) -> dict[str, Any]:
        """Сериализация в dict."""
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "status": self.status,
            "total_orders": self.total_orders,
            "completed_orders": self.completed_orders,
            "total_spent": self.total_spent,
            "first_order_date": self.first_order_date.isoformat()
            if self.first_order_date
            else None,
            "last_order_date": self.last_order_date.isoformat()
            if self.last_order_date
            else None,
            "favorite_device": self.favorite_device,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Client:
        """Десериализация из dict."""
        return cls(
            id=data.get("id"),
            name=data.get("name", ""),
            phone=data.get("phone", ""),
            status=data.get("status", "Новый"),
            total_orders=int(data.get("total_orders", 0)),
            completed_orders=int(data.get("completed_orders", 0)),
            total_spent=float(data.get("total_spent", 0)),
            first_order_date=datetime.fromisoformat(data["first_order_date"])
            if data.get("first_order_date")
            else None,
            last_order_date=datetime.fromisoformat(data["last_order_date"])
            if data.get("last_order_date")
            else None,
            favorite_device=data.get("favorite_device", ""),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else datetime.now(),
        )


@dataclass(slots=True, frozen=False)
class RepairHistory:
    """История ремонта клиента."""

    id: int | None = None
    client_id: int | None = None
    device_id: int | None = None
    order_number: str = ""
    receipt_date: datetime = field(default_factory=datetime.now)
    completion_date: datetime | None = None
    device_type: str = ""
    brand: str = ""
    model: str = ""
    serial_number: str = ""
    defect: str = ""
    work_items: str = ""  # JSON
    status: str = ""
    total_price: float = 0.0
    engineer: str = ""
    warranty: str = ""
    notes: str = ""
    photos: str = ""  # JSON
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Сериализация в dict."""
        return {
            "id": self.id,
            "client_id": self.client_id,
            "device_id": self.device_id,
            "order_number": self.order_number,
            "receipt_date": self.receipt_date.isoformat()
            if self.receipt_date
            else None,
            "completion_date": self.completion_date.isoformat()
            if self.completion_date
            else None,
            "device_type": self.device_type,
            "brand": self.brand,
            "model": self.model,
            "serial_number": self.serial_number,
            "defect": self.defect,
            "work_items": self.work_items,
            "status": self.status,
            "total_price": self.total_price,
            "engineer": self.engineer,
            "warranty": self.warranty,
            "notes": self.notes,
            "photos": self.photos,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RepairHistory:
        """Десериализация из dict."""
        return cls(
            id=data.get("id"),
            client_id=data.get("client_id"),
            device_id=data.get("device_id"),
            order_number=data.get("order_number", ""),
            receipt_date=datetime.fromisoformat(data["receipt_date"])
            if data.get("receipt_date")
            else datetime.now(),
            completion_date=datetime.fromisoformat(data["completion_date"])
            if data.get("completion_date")
            else None,
            device_type=data.get("device_type", ""),
            brand=data.get("brand", ""),
            model=data.get("model", ""),
            serial_number=data.get("serial_number", ""),
            defect=data.get("defect", ""),
            work_items=data.get("work_items", ""),
            status=data.get("status", ""),
            total_price=float(data.get("total_price", 0)),
            engineer=data.get("engineer", ""),
            warranty=data.get("warranty", ""),
            notes=data.get("notes", ""),
            photos=data.get("photos", ""),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else datetime.now(),
        )


@dataclass(slots=True, frozen=False)
class FinanceRecord:
    """Финансовая запись."""

    id: int | None = None
    order_number: str = ""
    completion_date: datetime = field(default_factory=datetime.now)
    income: float = 0.0
    expense: float = 0.0
    profit: float = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "profit", self.income - self.expense)

    def to_dict(self) -> dict[str, Any]:
        """Сериализация в dict."""
        return {
            "id": self.id,
            "order_number": self.order_number,
            "completion_date": self.completion_date.isoformat(),
            "income": self.income,
            "expense": self.expense,
            "profit": self.profit,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FinanceRecord:
        """Десериализация из dict."""
        return cls(
            id=data.get("id"),
            order_number=data.get("order_number", ""),
            completion_date=datetime.fromisoformat(data["completion_date"])
            if data.get("completion_date")
            else datetime.now(),
            income=float(data.get("income", 0)),
            expense=float(data.get("expense", 0)),
        )
