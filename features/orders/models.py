"""
SQLAlchemy ORM модель заказа.
Infrastructure слой - зависит от SQLAlchemy.
"""
from datetime import datetime
from typing import Optional, List, Any
import json

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, ForeignKey,
    Enum as SQLEnum
)
from sqlalchemy.orm import relationship, Mapped, mapped_column, DeclarativeBase

from shared.kernel import OrderStatus, Priority


class Base(DeclarativeBase):
    """Базовый класс для ORM моделей."""
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    def to_dict(self) -> dict[str, Any]:
        """Преобразование модели в словарь."""
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }


class RepairOrder(Base):
    """
    Модель заказа на ремонт.
    
    SSOT: Единственное определение структуры заказа в БД.
    """
    __tablename__ = 'repair_orders'
    
    # Основные поля
    order_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    client_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('clients.id'), nullable=True)
    
    # Статус и приоритет
    status: Mapped[str] = mapped_column(
        SQLEnum(OrderStatus, values_callable=lambda x: [e.value for e in x]),
        default=OrderStatus.DIAGNOSTICS,
        nullable=False
    )
    priority: Mapped[str] = mapped_column(
        SQLEnum(Priority, values_callable=lambda x: [e.value for e in x]),
        default=Priority.NORMAL,
        nullable=False
    )
    
    # Финансы
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Диагностика и описание
    diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    complaint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Работы и запчасти (JSON)
    work_items: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parts_used: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Связи
    client_rel: Mapped[Optional['Client']] = relationship(
        'Client',
        back_populates='orders_rel',
        foreign_keys=[client_id]
    )
    
    # Временные метки
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Методы для работы с JSON полями
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
    
    def get_parts_used(self) -> list[dict]:
        """Получение списка запчастей из JSON."""
        if not self.parts_used:
            return []
        try:
            return json.loads(self.parts_used)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_parts_used(self, parts: list[dict]) -> None:
        """Установка списка запчастей в JSON."""
        self.parts_used = json.dumps(parts, ensure_ascii=False)
    
    def calculate_total(self) -> float:
        """Вычисление общей стоимости из работ и запчастей."""
        total = 0.0
        
        # Работы
        for item in self.get_work_items():
            price = float(item.get('price', 0) or 0)
            qty = int(item.get('quantity', 1) or 1)
            total += price * qty
        
        # Запчасти
        for part in self.get_parts_used():
            price = float(part.get('price', 0) or 0)
            qty = int(part.get('quantity', 1) or 1)
            total += price * qty
        
        return total
    
    def to_dict(self) -> dict[str, Any]:
        """Расширенное преобразование в словарь."""
        data = super().to_dict()
        data['work_items'] = self.get_work_items()
        data['parts_used'] = self.get_parts_used()
        data['calculated_total'] = self.calculate_total()
        return data


# Импортируем Client для связи, если он существует
# Если нет - связь будет настроена позже
try:
    from database.sqlalchemy_models import Client
    Client.orders_rel = relationship(
        'RepairOrder',
        back_populates='client_rel',
        foreign_keys=[RepairOrder.client_id]
    )
except ImportError:
    pass
