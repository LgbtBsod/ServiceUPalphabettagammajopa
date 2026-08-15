#!/usr/bin/env python3
"""SQLAlchemy ORM модели данных.

Использует SQLAlchemy 2.0+ с декларативным стилем.
Заменяет ручные SQL запросы на типобезопасный ORM API.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
    validates,
)


class Base(DeclarativeBase):
    """Базовый класс для всех ORM моделей."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    def to_dict(self) -> dict[str, Any]:
        """Преобразование модели в словарь."""
        return {
            column.name: getattr(self, column.name) for column in self.__table__.columns
        }

    def update_from_dict(self, data: dict[str, Any]) -> None:
        """Обновление полей из словаря."""
        for key, value in data.items():
            if hasattr(self, key) and key != "id":
                setattr(self, key, value)


class Client(Base):
    """Модель клиента."""

    __tablename__ = "clients"

    # Основные поля
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(50), default="Новый")
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Статистика
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    completed_orders: Mapped[int] = mapped_column(Integer, default=0)
    total_spent: Mapped[float] = mapped_column(Float, default=0.0)
    first_order_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_order_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    favorite_device: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Связи
    devices: Mapped[list[Device]] = relationship(
        "Device", back_populates="client_rel", cascade="all, delete-orphan"
    )

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc), 
        nullable=False
    )

    @validates("phone")
    def validate_phone(self, key: str, value: str) -> str:
        """Валидация телефонного номера."""
        if not value or not value.strip():
            raise ValueError("Телефон не может быть пустым")
        return value.strip()

    @validates("name")
    def validate_name(self, key: str, value: str) -> str:
        """Валидация имени."""
        if not value or not value.strip():
            raise ValueError("Имя не может быть пустым")
        return value.strip()

    def update_stats(
        self,
        total_orders: int,
        completed_orders: int,
        total_spent: float,
        last_order_date: str | None = None,
    ) -> None:
        """Обновление статистики клиента."""
        self.total_orders = total_orders
        self.completed_orders = completed_orders
        self.total_spent = total_spent
        if last_order_date:
            self.last_order_date = last_order_date


class Device(Base):
    """Модель устройства/заказа."""

    __tablename__ = "devices"

    # Идентификаторы
    order_number: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    client_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Дублируем имя клиента и телефон для быстрого доступа (denormalization)
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_status: Mapped[str | None] = mapped_column(String(50), default="Новый")
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Даты
    receipt_date: Mapped[str] = mapped_column(String(50), nullable=False)
    completion_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ready_date: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Информация об устройстве
    device_type: Mapped[str] = mapped_column(String(100), nullable=False)
    brand: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Описание проблемы
    defect: Mapped[str] = mapped_column(Text, nullable=False, default="")
    appearance: Mapped[str] = mapped_column(Text, nullable=False, default="")
    completeness: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Работы (JSON) - храним как work_items для совместимости с legacy кодом
    work_items: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Финансы
    total_price: Mapped[float] = mapped_column(Float, default=0.0)
    prepayment: Mapped[float] = mapped_column(Float, default=0.0)
    expense: Mapped[str | None] = mapped_column(Text, nullable=True, default="0")
    diagnostic_cost: Mapped[str | None] = mapped_column(Text, nullable=True)
    repair_cost: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Статус и приоритет
    status: Mapped[str] = mapped_column(String(50), default="Диагностика")
    priority: Mapped[str] = mapped_column(String(50), default="Обычный")
    engineer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    warranty: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Заметки и фото
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    photos: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc), 
        nullable=False
    )

    # Связи
    client_rel: Mapped[Client] = relationship("Client", back_populates="devices")
    work_item_records: Mapped[list[WorkItemRecord]] = relationship(
        "WorkItemRecord", back_populates="device", cascade="all, delete-orphan"
    )
    photo_records: Mapped[list[PhotoRecord]] = relationship(
        "PhotoRecord", back_populates="device", cascade="all, delete-orphan"
    )

    @validates("order_number")
    def validate_order_number(self, key: str, value: str) -> str:
        """Валидация номера заказа."""
        if not value or not value.strip():
            raise ValueError("Номер заказа не может быть пустым")
        return value.strip()

    def get_work_items(self) -> list[dict]:
        """Получение списка работ из JSON."""
        if not self.work_items:
            return []
        try:
            return json.loads(self.work_items)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_work_items(self, items: list[dict]) -> None:
        """Установка списка работ в JSON."""
        self.work_items = json.dumps(items, ensure_ascii=False)

    def calculate_total_from_works(self) -> float:
        """Вычисление общей стоимости из работ."""
        items = self.get_work_items()
        total = 0.0
        for item in items:
            price = float(item.get("price", 0) or 0)
            qty = int(item.get("quantity", 1) or 1)
            total += price * qty
        return total


class WorkTemplate(Base):
    """Модель шаблона работы."""

    __tablename__ = "work_templates"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class Settings(Base):
    """Модель настроек приложения."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )


class Counter(Base):
    """Именованные счётчики (например, order_counter для номеров заказов).

    Схема 1:1 с legacy-таблицей `counters` (database/db_manager.py:69-74).
    """

    __tablename__ = "counters"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=True)
    value: Mapped[int] = mapped_column(Integer, default=1)


class DictionaryItem(Base):
    """Значения справочников (статусы/бренды/типы устройств и т.д.).

    Схема 1:1 с legacy-таблицей `dictionaries` (database/db_manager.py:147-156).
    """

    __tablename__ = "dictionaries"
    __table_args__ = (UniqueConstraint("dict_type", "value", name="uq_dict_type_value"),)

    dict_type: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    value: Mapped[str] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    additional_info: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class FinanceRecord(Base):
    """Финансовая запись по заказу (доход/расход/прибыль).

    Схема 1:1 с legacy-таблицей `finances` (database/db_manager.py:134-143).
    """

    __tablename__ = "finances"

    order_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=True)
    completion_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    income: Mapped[float] = mapped_column(Float, default=0.0)
    expense: Mapped[float] = mapped_column(Float, default=0.0)
    profit: Mapped[float] = mapped_column(Float, default=0.0)


class WorkItemRecord(Base):
    """Отдельная работа устройства (дочерняя таблица, dual-write с Device.work_items).

    Схема 1:1 с legacy-таблицей `work_items_db` (database/db_manager.py:161-171).
    Существует для быстрых запросов/отчётов — devices.work_items (JSON) остаётся
    основным источником для чтения формой устройства (см. AUDIT_REPORT_v20.md).
    """

    __tablename__ = "work_items_db"

    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    total: Mapped[float] = mapped_column(Float, default=0.0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    device: Mapped[Device] = relationship("Device", back_populates="work_item_records")


class PhotoRecord(Base):
    """Отдельное фото устройства (дочерняя таблица, dual-write с Device.photos).

    Схема 1:1 с legacy-таблицей `photos_db` (database/db_manager.py:176-186).
    """

    __tablename__ = "photos_db"

    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    photo_type: Mapped[str] = mapped_column(String(50), default="device")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    device: Mapped[Device] = relationship("Device", back_populates="photo_records")


class CompletedRepair(Base):
    """Запись о завершённом ремонте (архив выполненных работ по устройству).

    Схема 1:1 с legacy-таблицей `completed_repairs` (database/db_manager.py:117-130).
    """

    __tablename__ = "completed_repairs"

    device_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=True, index=True
    )
    order_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    completion_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    work_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_price: Mapped[str | None] = mapped_column(Text, nullable=True)
    engineer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    warranty: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class RepairHistoryMain(Base):
    """История ремонтов клиента в основной БД (замена DBClients/*.db).

    Схема 1:1 с legacy-таблицей `repair_history_main` (database/db_manager.py:209-232).
    """

    __tablename__ = "repair_history_main"

    client_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=True, index=True
    )
    device_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=True, index=True
    )
    order_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    receipt_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    completion_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    defect: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_items: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    total_price: Mapped[str | None] = mapped_column(Text, nullable=True)
    engineer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    warranty: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    photos: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


def create_database_engine(db_url: str, echo: bool = False) -> Any:
    """Создание движка базы данных.

    Args:
        db_url: URL подключения к БД.
        echo: Логировать SQL запросы.

    Returns:
        SQLAlchemy Engine.
    """
    engine = create_engine(
        db_url,
        echo=echo,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False}
        if db_url.startswith("sqlite")
        else {},
    )

    # Включаем foreign keys для SQLite
    if db_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_tables(engine: Any) -> None:
    """Создание всех таблиц в базе данных."""
    Base.metadata.create_all(engine)


def drop_tables(engine: Any) -> None:
    """Удаление всех таблиц из базы данных."""
    Base.metadata.drop_all(engine)


def get_session_factory(engine: Any) -> sessionmaker:
    """Получение фабрики сессий."""
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_session(session_factory: sessionmaker) -> Session:
    """Получение новой сессии."""
    return session_factory()
