#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модели данных на основе Pydantic для валидации и сериализации.

Использует Pydantic v2 для:
- Валидации данных при создании/изменении
- Сериализации в JSON для хранения
- Типизации всех полей
- Автоматической конвертации типов

Python 3.14+ совместимость:
- Аннотации типов без кавычек (PEP 649)
- TypedDict с total=False для опциональных полей
"""

from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Literal, Annotated
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from pydantic.functional_validators import AfterValidator
import phonenumbers
from phonenumbers import NumberParseException


# =============================================================================
# ENUMS
# =============================================================================

class OrderStatus(str, Enum):
    """Статусы заказов"""
    DIAGNOSTICS = "Диагностика"
    WAITING_PARTS = "Ожидание запчастей"
    IN_REPAIR = "В ремонте"
    READY = "Готов к выдаче"
    ISSUED = "Выдан клиенту"
    REFUSED = "Отказ от ремонта"


class Priority(str, Enum):
    """Приоритеты заказов"""
    LOW = "Низкий"
    NORMAL = "Обычный"
    HIGH = "Высокий"
    URGENT = "Срочный"


class ClientStatus(str, Enum):
    """Статусы клиентов"""
    NEW = "Новый"
    REGULAR = "Постоянный"
    VIP = "VIP"
    PROBLEMATIC = "Проблемный"


class DeviceType(str, Enum):
    """Типы устройств"""
    LAPTOP = "Ноутбук"
    PC = "ПК"
    SMARTPHONE = "Смартфон"
    TABLET = "Планшет"
    MONITOR = "Монитор"
    PRINTER = "Принтер"
    TV = "Телевизор"
    AUDIO = "Аудио"
    CAMERA = "Фотоаппарат"
    CONSOLE = "Игровая консоль"
    OTHER = "Другое"


# =============================================================================
# CUSTOM TYPES & VALIDATORS
# =============================================================================

def validate_phone_number(value: str) -> str:
    """Валидация и нормализация телефона через phonenumbers library."""
    if not value or not str(value).strip():
        raise ValueError("Телефон не может быть пустым")
    
    try:
        parsed = phonenumbers.parse(str(value), "RU")
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("Неверный формат номера телефона")
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    except NumberParseException as e:
        raise ValueError(f"Ошибка парсинга телефона: {e}")


def validate_price_value(value: Optional[str | int | float | Decimal]) -> Optional[Decimal]:
    """Валидация цены с поддержкой разных форматов."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    
    try:
        if isinstance(value, Decimal):
            price = value
        elif isinstance(value, (int, float)):
            price = Decimal(str(value))
        else:
            # Очищаем строку от форматирования
            cleaned = str(value).strip()
            cleaned = cleaned.replace(',', '.').replace(' ', '').replace('\u00a0', '')
            cleaned = cleaned.replace('₽', '').replace('$', '').replace('€', '')
            price = Decimal(cleaned)
        
        if price < 0:
            raise ValueError("Цена не может быть отрицательной")
        
        return price.quantize(Decimal('0.01'))
    except Exception as e:
        raise ValueError(f"Некорректная цена: {e}")


PriceField = Annotated[Optional[Decimal], AfterValidator(validate_price_value)]
PhoneField = Annotated[str, AfterValidator(validate_phone_number)]


# =============================================================================
# BASE MODELS
# =============================================================================

class Client(BaseModel):
    """Модель клиента"""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        use_enum_values=False,
        validate_assignment=True,
        extra='ignore'
    )
    
    id: Optional[int] = None
    full_name: str = Field(..., min_length=1, max_length=200, description="ФИО клиента")
    phone: PhoneField = Field(..., description="Телефон клиента")
    email: Optional[str] = Field(None, pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    status: ClientStatus = Field(default=ClientStatus.NEW)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    notes: Optional[str] = Field(None, max_length=1000)


class Device(BaseModel):
    """Модель устройства"""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='ignore'
    )
    
    id: Optional[int] = None
    device_type: DeviceType = Field(..., description="Тип устройства")
    brand: str = Field(..., min_length=1, max_length=100, description="Бренд")
    model: str = Field(..., min_length=1, max_length=200, description="Модель")
    serial_number: Optional[str] = Field(None, max_length=100)
    color: Optional[str] = Field(None, max_length=50)
    password: Optional[str] = Field(None, max_length=100)
    
    appearance: Optional[str] = Field(None, max_length=200)
    completeness: Optional[str] = Field(None, max_length=200)
    defects: Optional[str] = Field(..., min_length=1, max_length=1000, description="Описание неисправности")


class WorkItem(BaseModel):
    """Модель выполненной работы"""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='ignore'
    )
    
    id: Optional[int] = None
    name: str = Field(..., min_length=1, max_length=300, description="Название работы")
    price: PriceField = Field(None, description="Стоимость работы")
    warranty: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = Field(None, max_length=500)


class Order(BaseModel):
    """Модель заказа-наряда"""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='ignore'
    )
    
    id: Optional[int] = None
    order_number: str = Field(..., min_length=1, max_length=20, description="Номер заказа")
    client_id: Optional[int] = None
    
    # Информация об устройстве (денормализация для быстрого доступа)
    device_type: DeviceType
    brand: str
    model: str
    serial_number: Optional[str] = None
    defects: str
    appearance: Optional[str] = None
    completeness: Optional[str] = None
    
    # Статус и приоритет
    status: OrderStatus = Field(default=OrderStatus.DIAGNOSTICS)
    priority: Priority = Field(default=Priority.NORMAL)
    
    # Финансы
    diagnostic_cost: PriceField = Field(None, description="Стоимость диагностики")
    repair_cost: PriceField = Field(None, description="Стоимость ремонта")
    total_cost: PriceField = Field(None, description="Итоговая стоимость")
    
    # Даты
    receipt_date: datetime = Field(default_factory=datetime.now)
    ready_date: Optional[datetime] = None
    issue_date: Optional[datetime] = None
    
    # Дополнительно
    engineer: Optional[str] = Field(None, max_length=200)
    warranty: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = Field(None, max_length=1000)
    payment_status: Literal["paid", "partial", "unpaid"] = Field(default="unpaid")
    
    @model_validator(mode='before')
    @classmethod
    def calculate_total(cls, values: dict) -> dict:
        """Автоматический расчет итоговой стоимости"""
        diagnostic_cost = values.get('diagnostic_cost')
        repair_cost = values.get('repair_cost')
        
        if diagnostic_cost and repair_cost:
            values['total_cost'] = diagnostic_cost + repair_cost
        elif diagnostic_cost:
            values['total_cost'] = diagnostic_cost
        elif repair_cost:
            values['total_cost'] = repair_cost
        
        return values
    
    @property
    def days_in_service(self) -> int:
        """Количество дней в сервисе"""
        delta = datetime.now() - self.receipt_date
        return delta.days
    
    @property
    def is_overdue(self) -> bool:
        """Проверка на просрочку (более 14 дней)"""
        return self.days_in_service > 14


class Settings(BaseModel):
    """Модель настроек приложения"""
    model_config = ConfigDict(
        validate_assignment=True,
        extra='allow'
    )
    
    theme: Literal["light", "dark", "system"] = Field(default="light")
    accent_color: str = Field(default="#0078d4", pattern=r'^#[0-9A-Fa-f]{6}$')
    fullscreen: bool = False
    confirm_delete: bool = True
    confirm_exit: bool = False
    auto_save_on_close: bool = True
    default_status: OrderStatus = Field(default=OrderStatus.DIAGNOSTICS)
    default_priority: Priority = Field(default=Priority.NORMAL)
    remind_overdue: bool = True
    overdue_days: int = Field(default=14, ge=1, le=365)
    notify_on_ready: bool = True
    auto_backup: bool = True
    backup_interval: int = Field(default=24, ge=1, le=168)  # часы
    backup_count: int = Field(default=10, ge=1, le=100)
    compress_backups: bool = True
    photo_quality: int = Field(default=85, ge=1, le=100)
    create_thumbnails: bool = True
    window_width: int = Field(default=1280, ge=800, le=3840)
    window_height: int = Field(default=720, ge=600, le=2160)
    
    pwa_port: int = Field(default=5000, ge=1, le=65535)
    pwa_auto_start: bool = False
    pwa_auto_sync: bool = True
    pwa_sync_interval: int = Field(default=30, ge=1, le=3600)


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

def create_test_order() -> Order:
    """Создание тестового заказа для демонстрации"""
    return Order(
        order_number="00001",
        device_type=DeviceType.LAPTOP,
        brand="Apple",
        model="MacBook Pro 13",
        serial_number="C02XY1ABCD12",
        defects="Не включается, возможно проблема с материнской платой",
        status=OrderStatus.IN_REPAIR,
        priority=Priority.HIGH,
        diagnostic_cost=Decimal("1500.00"),
        repair_cost=Decimal("8500.00"),
        engineer="Иноагент",
    )


def create_test_client() -> Client:
    """Создание тестового клиента"""
    return Client(
        full_name="Иванов Иван Иванович",
        phone="+7 (999) 123-45-67",
        email="ivan@example.com",
        status=ClientStatus.REGULAR,
    )


if __name__ == "__main__":
    # Демонстрация работы моделей
    print("=" * 60)
    print("ServiceUP v15.0 - Pydantic Models Demo")
    print("=" * 60)
    
    # Создание и валидация клиента
    client = create_test_client()
    print(f"\n✅ Клиент: {client.full_name}")
    print(f"   Телефон: {client.phone}")
    print(f"   Статус: {client.status.value}")
    
    # Создание и валидация заказа
    order = create_test_order()
    print(f"\n✅ Заказ №{order.order_number}")
    print(f"   Устройство: {order.brand} {order.model}")
    print(f"   Статус: {order.status.value}")
    print(f"   Дней в сервисе: {order.days_in_service}")
    print(f"   Итоговая стоимость: {order.total_cost} ₽")
    
    # Тест валидации
    print("\n🧪 Тест валидации:")
    try:
        invalid_client = Client(
            full_name="",
            phone="invalid",
        )
    except Exception as e:
        print(f"   ❌ Ожидаемая ошибка: {e}")
    
    print("\n" + "=" * 60)
