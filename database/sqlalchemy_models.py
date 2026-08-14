#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SQLAlchemy ORM модели данных.

Использует SQLAlchemy 2.0+ с декларативным стилем.
Заменяет ручные SQL запросы на типобезопасный ORM API.
"""

from datetime import datetime
from typing import Optional, List, Any
import json

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, ForeignKey,
    create_engine, event
)
from sqlalchemy.orm import (
    DeclarativeBase, relationship, Session, Mapped, mapped_column,
    sessionmaker, validates
)
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Базовый класс для всех ORM моделей."""
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    def to_dict(self) -> dict[str, Any]:
        """Преобразование модели в словарь."""
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }
    
    def update_from_dict(self, data: dict[str, Any]) -> None:
        """Обновление полей из словаря."""
        for key, value in data.items():
            if hasattr(self, key) and key != 'id':
                setattr(self, key, value)


class Client(Base):
    """Модель клиента."""
    
    __tablename__ = 'clients'
    
    # Основные поля
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default='Новый')
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Статистика
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    completed_orders: Mapped[int] = mapped_column(Integer, default=0)
    total_spent: Mapped[float] = mapped_column(Float, default=0.0)
    last_order_date: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Связи
    devices: Mapped[List['Device']] = relationship(
        'Device',
        back_populates='client_rel',
        cascade='all, delete-orphan'
    )
    
    # Временные метки
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    @validates('phone')
    def validate_phone(self, key: str, value: str) -> str:
        """Валидация телефонного номера."""
        if not value or not value.strip():
            raise ValueError("Телефон не может быть пустым")
        return value.strip()
    
    @validates('name')
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
        last_order_date: Optional[str] = None
    ) -> None:
        """Обновление статистики клиента."""
        self.total_orders = total_orders
        self.completed_orders = completed_orders
        self.total_spent = total_spent
        if last_order_date:
            self.last_order_date = last_order_date


class Device(Base):
    """Модель устройства/заказа."""
    
    __tablename__ = 'devices'
    
    # Идентификаторы
    order_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    client_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey('clients.id', ondelete='SET NULL'), nullable=True, index=True
    )
    
    # Дублируем имя клиента и телефон для быстрого доступа (denormalization)
    client_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    client_status: Mapped[Optional[str]] = mapped_column(String(50), default='Новый')
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Даты
    receipt_date: Mapped[str] = mapped_column(String(50), nullable=False)
    completion_date: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ready_date: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Информация об устройстве
    device_type: Mapped[str] = mapped_column(String(100), nullable=False)
    brand: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    serial_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Описание проблемы
    defect: Mapped[str] = mapped_column(Text, nullable=False, default='')
    appearance: Mapped[str] = mapped_column(Text, nullable=False, default='')
    completeness: Mapped[str] = mapped_column(Text, nullable=False, default='')
    
    # Работы (JSON) - храним как work_items для совместимости с legacy кодом
    work_items: Mapped[str] = mapped_column(Text, nullable=False, default='[]')
    
    # Финансы
    total_price: Mapped[float] = mapped_column(Float, default=0.0)
    prepayment: Mapped[float] = mapped_column(Float, default=0.0)
    expense: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default='0')
    diagnostic_cost: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    repair_cost: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Статус и приоритет
    status: Mapped[str] = mapped_column(String(50), default='Диагностика')
    priority: Mapped[str] = mapped_column(String(50), default='Обычный')
    engineer: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    warranty: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Заметки и фото
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    photos: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Временные метки
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    # Связи
    client_rel: Mapped['Client'] = relationship('Client', back_populates='devices')
    
    @validates('order_number')
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
            price = float(item.get('price', 0) or 0)
            qty = int(item.get('quantity', 1) or 1)
            total += price * qty
        return total


class WorkTemplate(Base):
    """Модель шаблона работы."""
    
    __tablename__ = 'work_templates'
    
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


class Settings(Base):
    """Модель настроек приложения."""
    
    __tablename__ = 'settings'
    
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


def create_database_engine(db_url: str, echo: bool = False) -> Any:
    """
    Создание движка базы данных.
    
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
        connect_args={'check_same_thread': False} if db_url.startswith('sqlite') else {}
    )
    
    # Включаем foreign keys для SQLite
    if db_url.startswith('sqlite'):
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
