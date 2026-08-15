#!/usr/bin/env python3

"""Модели данных"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


def _safe_price_to_float(price) -> float:
    """Безопасное преобразование цены (строка с запятой/пробелами/₽) в float."""
    if price is None or price == "":
        return 0.0
    try:
        cleaned = str(price).replace("\u00a0", " ").replace(",", ".")
        chars = [c for c in cleaned if c.isdigit() or c == "."]
        if not chars:
            return 0.0
        s = "".join(chars)
        if s.count(".") > 1:
            parts = s.split(".")
            s = parts[0] + "." + "".join(parts[1:])
        return float(s)
    except ValueError, TypeError:
        return 0.0


def _safe_int(value, default=1) -> int:
    """Надёжное приведение к int (устойчиво к строкам вроде '2')."""
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except ValueError, TypeError:
        try:
            return int(float(str(value).strip()))
        except ValueError, TypeError:
            return default


@dataclass
class WorkItem:
    """Модель выполненной работы"""

    description: str = ""
    price: str = ""
    quantity: int = 1

    def total_price(self) -> float:
        """Получение общей стоимости"""
        price_val = _safe_price_to_float(self.price)
        qty = _safe_int(self.quantity, 1)
        return price_val * qty

    def to_dict(self) -> dict[str, Any]:
        """Преобразование в словарь"""
        return {
            "description": self.description,
            "price": self.price,
            "quantity": _safe_int(self.quantity, 1),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkItem:
        """Создание из словаря"""
        return cls(
            description=data.get("description", ""),
            price=data.get("price", ""),
            quantity=_safe_int(data.get("quantity", 1), 1),
        )


@dataclass
class Device:
    """Модель устройства/заказа"""

    id: int | None = None
    order_number: str = ""
    receipt_date: str = ""
    completion_date: str = ""
    ready_date: str = ""  # Дата готовности заказа
    device_type: str = ""
    brand: str = ""
    model: str = ""
    serial_number: str = ""
    defect: str = ""
    appearance: str = ""
    completeness: str = ""
    work_items: str = ""
    client_name: str = ""
    client_status: str = "Новый"
    phone: str = ""
    total_price: str = ""
    prepayment: str = ""
    status: str = "Диагностика"
    priority: str = "Обычный"
    engineer: str = ""
    warranty: str = ""
    notes: str = ""
    photos: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Преобразование в словарь"""
        return {
            "id": self.id,
            "order_number": self.order_number,
            "receipt_date": self.receipt_date,
            "completion_date": self.completion_date,
            "ready_date": self.ready_date,
            "device_type": self.device_type,
            "brand": self.brand,
            "model": self.model,
            "serial_number": self.serial_number,
            "defect": self.defect,
            "appearance": self.appearance,
            "completeness": self.completeness,
            "work_items_json": self.work_items,
            "client_name": self.client_name,
            "client_status": self.client_status,
            "phone": self.phone,
            "total_price": self.total_price,
            "prepayment": self.prepayment,
            "status": self.status,
            "priority": self.priority,
            "engineer": self.engineer,
            "warranty": self.warranty,
            "notes": self.notes,
            "photos": self.photos,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Device:
        """Создание из словаря"""
        return cls(
            id=data.get("id"),
            order_number=data.get("order_number", ""),
            receipt_date=data.get("receipt_date", ""),
            completion_date=data.get("completion_date", ""),
            ready_date=data.get("ready_date", ""),
            device_type=data.get("device_type", ""),
            brand=data.get("brand", ""),
            model=data.get("model", ""),
            serial_number=data.get("serial_number", ""),
            defect=data.get("defect", ""),
            appearance=data.get("appearance", ""),
            completeness=data.get("completeness", ""),
            work_items=data.get("work_items_json", ""),
            client_name=data.get("client_name", ""),
            client_status=data.get("client_status", "Новый"),
            phone=data.get("phone", ""),
            total_price=data.get("total_price", ""),
            prepayment=data.get("prepayment", ""),
            status=data.get("status", "Диагностика"),
            priority=data.get("priority", "Обычный"),
            engineer=data.get("engineer", ""),
            warranty=data.get("warranty", ""),
            notes=data.get("notes", ""),
            photos=data.get("photos", ""),
            created_at=data.get("created_at", ""),
        )


@dataclass
class WorkItemsManager:
    """Менеджер для работы с работами"""

    items: list[WorkItem] = field(default_factory=list)

    def add_item(self, item: WorkItem) -> None:
        """Добавление работы"""
        self.items.append(item)

    def remove_item(self, index: int) -> None:
        """Удаление работы"""
        if 0 <= index < len(self.items):
            del self.items[index]

    def update_item(self, index: int, item: WorkItem) -> None:
        """Обновление работы"""
        if 0 <= index < len(self.items):
            self.items[index] = item

    def clear(self) -> None:
        """Очистка списка"""
        self.items.clear()

    def get_total_price(self) -> float:
        """Получение общей суммы"""
        return sum(item.total_price() for item in self.items)

    def get_description_summary(self) -> str:
        """Получение краткого описания"""
        if not self.items:
            return ""
        descriptions = []
        for item in self.items:
            qty = _safe_int(item.quantity, 1)
            if qty > 1:
                descriptions.append(f"{item.description} x{qty}")
            else:
                descriptions.append(item.description)
        return "; ".join(descriptions)

    def to_json(self) -> str:
        """Преобразование в JSON"""
        return json.dumps([item.to_dict() for item in self.items], ensure_ascii=False)

    def from_json(self, json_str: str) -> None:
        """Загрузка из JSON"""
        self.clear()
        if not json_str:
            return
        try:
            items_data = json.loads(json_str)
            for item_data in items_data:
                self.add_item(WorkItem.from_dict(item_data))
        except (ValueError, TypeError) as e:
            logger.exception(f"Ошибка разбора работ: {e}")
