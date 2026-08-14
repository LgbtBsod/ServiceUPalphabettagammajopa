"""
Shared Kernel - общие типы, константы и утилиты для всех модулей.

Single Source of Truth (SSOT) для общих определений.
Следует принципу DRY - не дублировать определения в разных модулях.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum, StrEnum
from typing import TypeAlias, Protocol, runtime_checkable
from uuid import UUID, uuid4


# =============================================================================
# ENUMS - Single Source of Truth
# =============================================================================

class OrderStatus(StrEnum):
    """Статусы заказа - централизованное определение."""
    DIAGNOSTICS = "Диагностика"
    WAITING_PARTS = "Ожидание запчастей"
    IN_PROGRESS = "В работе"
    READY = "Готов к выдаче"
    ISSUED = "Выдан клиенту"
    CANCELLED = "Отменен"
    REFUSED = "Отказ от ремонта"


class Priority(StrEnum):
    """Приоритеты заказа - централизованное определение."""
    LOW = "Низкий"
    NORMAL = "Обычный"
    HIGH = "Высокий"
    URGENT = "Срочный"
    CRITICAL = "Критический"


class ClientStatus(StrEnum):
    """Статусы клиентов."""
    NEW = "Новый"
    REGULAR = "Постоянный"
    VIP = "VIP"
    PROBLEMATIC = "Проблемный"


class DeviceType(StrEnum):
    """Типы устройств - централизованный справочник."""
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


class PaymentMethod(StrEnum):
    """Способы оплаты."""
    CASH = "Наличные"
    CARD = "Карта"
    TRANSFER = "Перевод"
    CRYPTO = "Криптовалюта"


class NotificationType(StrEnum):
    """Типы уведомлений."""
    SMS = "sms"
    EMAIL = "email"
    TELEGRAM = "telegram"
    PUSH = "push"


# =============================================================================
# TYPE ALIASES - читаемые аннотации типов
# =============================================================================

Money: TypeAlias = Decimal
PhoneNumber: TypeAlias = str
Email: TypeAlias = str
UUIDStr: TypeAlias = str


# =============================================================================
# PROTOCOLS - интерфейсы для Dependency Injection
# =============================================================================

@runtime_checkable
class Identifiable(Protocol):
    """Протокол для сущностей с идентификатором."""
    id: int | None


@runtime_checkable
class Serializable(Protocol):
    """Протокол для сериализуемых объектов."""
    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> object: ...


@runtime_checkable
class Auditable(Protocol):
    """Протокол для сущностей с аудитом."""
    created_at: datetime
    updated_at: datetime | None


@runtime_checkable
class Repository(Protocol):
    """Протокол репозитория - Contract First подход."""
    def get_by_id(self, id: int) -> object | None: ...
    def get_all(self) -> list[object]: ...
    def add(self, entity: object) -> object: ...
    def update(self, entity: object) -> object: ...
    def delete(self, id: int) -> bool: ...


@runtime_checkable
class UnitOfWork(Protocol):
    """Протокол Unit of Work для транзакций."""
    def __enter__(self) -> UnitOfWork: ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


@runtime_checkable
class EventHandler(Protocol):
    """Протокол обработчика событий."""
    def handle(self, event: object) -> None: ...


@runtime_checkable
class NotificationSender(Protocol):
    """Протокол отправителя уведомлений."""
    def send(self, recipient: str, message: str, subject: str | None = None) -> bool: ...


# =============================================================================
# VALUE OBJECTS - неизменяемые объекты значений
# =============================================================================

@dataclass(slots=True, frozen=True)
class MoneyValue:
    """Неизменяемый объект денежного значения."""
    amount: Decimal = field(default=Decimal('0.00'))
    currency: str = field(default='RUB')

    def __post_init__(self):
        if self.amount < 0:
            raise ValueError("Сумма не может быть отрицательной")
        # Конвертируем в Decimal если передан float/int
        if not isinstance(self.amount, Decimal):
            object.__setattr__(self, 'amount', Decimal(str(self.amount)))
        object.__setattr__(self, 'amount', self.amount.quantize(Decimal('0.01')))

    def __str__(self) -> str:
        return f"{self.amount:.2f} {self.currency}"

    def __add__(self, other: MoneyValue) -> MoneyValue:
        if self.currency != other.currency:
            raise ValueError("Нельзя сложить разные валюты")
        return MoneyValue(self.amount + other.amount, self.currency)

    def __mul__(self, factor: int | float | Decimal) -> MoneyValue:
        return MoneyValue(self.amount * Decimal(str(factor)), self.currency)

    @classmethod
    def zero(cls, currency: str = 'RUB') -> MoneyValue:
        return cls(Decimal('0.00'), currency)


@dataclass(slots=True, frozen=True)
class DateRange:
    """Неизменяемый диапазон дат."""
    start: datetime
    end: datetime

    def __post_init__(self):
        if self.start > self.end:
            raise ValueError("Дата начала должна быть раньше даты окончания")

    def contains(self, date: datetime) -> bool:
        """Проверяет, находится ли дата в диапазоне."""
        return self.start <= date <= self.end

    @property
    def duration_days(self) -> int:
        """Длительность диапазона в днях."""
        return (self.end - self.start).days


@dataclass(slots=True, frozen=True)
class Address:
    """Неизменяемый объект адреса."""
    country: str = "Россия"
    city: str = ""
    street: str = ""
    building: str = ""
    apartment: str = ""
    postal_code: str = ""

    def __str__(self) -> str:
        parts = [self.country, self.city, self.street, self.building, self.apartment]
        return ", ".join(p for p in parts if p)

    @property
    def is_complete(self) -> bool:
        """Проверяет полноту адреса."""
        return all([self.city, self.street, self.building])


# =============================================================================
# CONSTANTS - централизованные константы
# =============================================================================

class Constants:
    """Централизованное хранилище констант приложения."""

    # Версия приложения
    VERSION = "17.0"
    NAME = "ServiceUP"
    DESCRIPTION = "Учет ремонта техники"

    # Лицензирование
    TRIAL_DAYS = 14
    LICENSE_FILE = ".license"

    # Валидация
    MAX_PHONE_LENGTH = 20
    MAX_EMAIL_LENGTH = 254
    MAX_NAME_LENGTH = 200
    MIN_PRICE = Decimal('0.00')
    MAX_PRICE = Decimal('999999999.99')

    # Пагинация
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

    # Кэширование
    CACHE_TTL_SECONDS = 300

    # Таймауты
    DB_TIMEOUT_SECONDS = 30
    API_TIMEOUT_SECONDS = 10

    # Логирование
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

    # Кодировки
    DEFAULT_ENCODING = "utf-8"


# =============================================================================
# UTILITIES - общие утилиты
# =============================================================================

def generate_uuid() -> UUID:
    """Генерирует новый UUID."""
    return uuid4()


def generate_uuid_str() -> UUIDStr:
    """Генерирует строковое представление UUID."""
    return str(generate_uuid())


def now_utc() -> datetime:
    """Возвращает текущее время в UTC."""
    return datetime.now(tz=None)  # Python 3.14: можно использовать tz=datetime.UTC


def sanitize_string(value: str, max_length: int = 1000) -> str:
    """Очищает строку от лишних пробелов и ограничивает длину."""
    if not value:
        return ""
    sanitized = " ".join(value.split())
    return sanitized[:max_length]


def safe_decimal(value: str | int | float | Decimal | None) -> Decimal:
    """Безопасное преобразование в Decimal."""
    if value is None:
        return Decimal('0.00')
    if isinstance(value, Decimal):
        return value.quantize(Decimal('0.01'))
    try:
        return Decimal(str(value)).quantize(Decimal('0.01'))
    except Exception:
        return Decimal('0.00')


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Enums
    'OrderStatus',
    'Priority',
    'ClientStatus',
    'DeviceType',
    'PaymentMethod',
    'NotificationType',
    # Type Aliases
    'Money',
    'PhoneNumber',
    'Email',
    'UUIDStr',
    # Protocols
    'Identifiable',
    'Serializable',
    'Auditable',
    'Repository',
    'UnitOfWork',
    'EventHandler',
    'NotificationSender',
    # Value Objects
    'MoneyValue',
    'DateRange',
    'Address',
    # Constants
    'Constants',
    # Utilities
    'generate_uuid',
    'generate_uuid_str',
    'now_utc',
    'sanitize_string',
    'safe_decimal',
]
