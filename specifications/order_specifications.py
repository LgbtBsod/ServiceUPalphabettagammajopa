#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Спецификация (Specification Pattern) для сложных запросов.

Реализует паттерн Specification для инкапсуляции бизнес-правил фильтрации.
Позволяет комбинировать правила с помощью логических операторов.
Соблюдает принципы SOLID, особенно Single Responsibility Principle.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar, Generic, List, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass

from models.pydantic_models import OrderStatus

T = TypeVar('T')


class Specification(ABC, Generic[T]):
    """
    Абстрактный класс спецификации.
    
    Спецификация инкапсулирует бизнес-правило проверки объекта.
    Соблюдает принцип Single Responsibility Principle (SRP).
    """
    
    @abstractmethod
    def is_satisfied_by(self, candidate: T) -> bool:
        """
        Проверка удовлетворения спецификации.
        
        Args:
            candidate: Кандидат на проверку.
            
        Returns:
            True если объект удовлетворяет спецификации.
        """
        pass
    
    def and_(self, other: Specification[T]) -> Specification[T]:
        """Логическое И между спецификациями."""
        return AndSpecification(self, other)
    
    def or_(self, other: Specification[T]) -> Specification[T]:
        """Логическое ИЛИ между спецификациями."""
        return OrSpecification(self, other)
    
    def not_(self) -> Specification[T]:
        """Логическое НЕ для спецификации."""
        return NotSpecification(self)


class AndSpecification(Specification[T]):
    """Спецификация логического И."""
    
    def __init__(self, left: Specification[T], right: Specification[T]):
        self._left = left
        self._right = right
    
    def is_satisfied_by(self, candidate: T) -> bool:
        return self._left.is_satisfied_by(candidate) and self._right.is_satisfied_by(candidate)


class OrSpecification(Specification[T]):
    """Спецификация логического ИЛИ."""
    
    def __init__(self, left: Specification[T], right: Specification[T]):
        self._left = left
        self._right = right
    
    def is_satisfied_by(self, candidate: T) -> bool:
        return self._left.is_satisfied_by(candidate) or self._right.is_satisfied_by(candidate)


class NotSpecification(Specification[T]):
    """Спецификация логического НЕ."""
    
    def __init__(self, spec: Specification[T]):
        self._spec = spec
    
    def is_satisfied_by(self, candidate: T) -> bool:
        return not self._spec.is_satisfied_by(candidate)


class LambdaSpecification(Specification[T]):
    """Спецификация на основе lambda функции."""
    
    def __init__(self, predicate: Callable[[T], bool]):
        self._predicate = predicate
    
    def is_satisfied_by(self, candidate: T) -> bool:
        return self._predicate(candidate)


# Спецификации для заказов

@dataclass
class OrderCandidate:
    """Кандидат заказа для проверки спецификациями."""
    id: int
    status: str
    priority: str
    receipt_date: datetime
    ready_date: Optional[datetime]
    total_cost: float
    days_in_service: int


class StatusSpecification(Specification[OrderCandidate]):
    """Спецификация по статусу заказа."""
    
    def __init__(self, status: str):
        self._status = status
    
    def is_satisfied_by(self, candidate: OrderCandidate) -> bool:
        return candidate.status == self._status


class PrioritySpecification(Specification[OrderCandidate]):
    """Спецификация по приоритету заказа."""
    
    def __init__(self, priority: str):
        self._priority = priority
    
    def is_satisfied_by(self, candidate: OrderCandidate) -> bool:
        return candidate.priority == self._priority


class OverdueSpecification(Specification[OrderCandidate]):
    """Спецификация просроченных заказов."""
    
    def __init__(self, max_days: int = 14):
        self._max_days = max_days
    
    def is_satisfied_by(self, candidate: OrderCandidate) -> bool:
        return candidate.days_in_service > self._max_days


class CostRangeSpecification(Specification[OrderCandidate]):
    """Спецификация по диапазону стоимости."""
    
    def __init__(self, min_cost: float = 0, max_cost: Optional[float] = None):
        self._min_cost = min_cost
        self._max_cost = max_cost
    
    def is_satisfied_by(self, candidate: OrderCandidate) -> bool:
        if candidate.total_cost < self._min_cost:
            return False
        if self._max_cost is not None and candidate.total_cost > self._max_cost:
            return False
        return True


class ReadyForPickupSpecification(Specification[OrderCandidate]):
    """Спецификация готовых к выдаче заказов."""
    
    def is_satisfied_by(self, candidate: OrderCandidate) -> bool:
        return (
            candidate.status == 'Готов к выдаче' and 
            candidate.ready_date is not None
        )


class HighPriorityUrgentSpecification(Specification[OrderCandidate]):
    """Спецификация срочных заказов с высоким приоритетом."""
    
    def is_satisfied_by(self, candidate: OrderCandidate) -> bool:
        return (
            candidate.priority == 'Срочный' and 
            candidate.days_in_service > 3
        )


# Фабрика для создания спецификаций

class SpecificationFactory:
    """Фабрика для создания спецификаций заказов."""
    
    @staticmethod
    def by_status(status: str) -> Specification[OrderCandidate]:
        """Создание спецификации по статусу."""
        return StatusSpecification(status)
    
    @staticmethod
    def by_priority(priority: str) -> Specification[OrderCandidate]:
        """Создание спецификации по приоритету."""
        return PrioritySpecification(priority)
    
    @staticmethod
    def overdue(days: int = 14) -> Specification[OrderCandidate]:
        """Создание спецификации просроченных заказов."""
        return OverdueSpecification(days)
    
    @staticmethod
    def cost_range(min_cost: float = 0, max_cost: Optional[float] = None) -> Specification[OrderCandidate]:
        """Создание спецификации диапазона стоимости."""
        return CostRangeSpecification(min_cost, max_cost)
    
    @staticmethod
    def ready_for_pickup() -> Specification[OrderCandidate]:
        """Создание спецификации готовых к выдаче заказов."""
        return ReadyForPickupSpecification()
    
    @staticmethod
    def high_priority_urgent() -> Specification[OrderCandidate]:
        """Создание спецификации срочных заказов."""
        return HighPriorityUrgentSpecification()
    
    @staticmethod
    def custom(predicate: Callable[[OrderCandidate], bool]) -> Specification[OrderCandidate]:
        """Создание пользовательской спецификации."""
        return LambdaSpecification(predicate)
    
    @staticmethod
    def active_orders() -> Specification[OrderCandidate]:
        """
        Создание спецификации активных заказов.
        
        Комбинирует несколько правил:
        - Не выдан и не отказан
        - Не просрочен более чем на 30 дней
        """
        not_issued = StatusSpecification(OrderStatus.ISSUED.value).not_()
        not_refused = StatusSpecification(OrderStatus.REFUSED.value).not_()
        not_overly_overdue = OverdueSpecification(30).not_()
        
        return not_issued.and_(not_refused).and_(not_overly_overdue)
    
    @staticmethod
    def needs_attention() -> Specification[OrderCandidate]:
        """
        Создание спецификации заказов требующих внимания.
        
        Комбинирует:
        - Просроченные (>14 дней)
        - Срочные в работе (>3 дней)
        - Готовые к выдаче
        """
        overdue = OverdueSpecification(14)
        urgent = HighPriorityUrgentSpecification()
        ready = ReadyForPickupSpecification()
        
        return overdue.or_(urgent).or_(ready)


# Примеры использования

def create_sample_orders() -> List[OrderCandidate]:
    """Создание тестовых заказов."""
    now = datetime.now()
    
    return [
        OrderCandidate(
            id=1, status='Диагностика', priority='Обычный',
            receipt_date=now - timedelta(days=5),
            ready_date=None, total_cost=5000, days_in_service=5
        ),
        OrderCandidate(
            id=2, status='В ремонте', priority='Срочный',
            receipt_date=now - timedelta(days=10),
            ready_date=None, total_cost=15000, days_in_service=10
        ),
        OrderCandidate(
            id=3, status='Готов к выдаче', priority='Обычный',
            receipt_date=now - timedelta(days=7),
            ready_date=now - timedelta(days=1),
            total_cost=8000, days_in_service=7
        ),
        OrderCandidate(
            id=4, status='Выдан', priority='Обычный',
            receipt_date=now - timedelta(days=20),
            ready_date=now - timedelta(days=10),
            total_cost=12000, days_in_service=20
        ),
        OrderCandidate(
            id=5, status='Диагностика', priority='Срочный',
            receipt_date=now - timedelta(days=2),
            ready_date=None, total_cost=3000, days_in_service=2
        ),
    ]


def filter_orders(orders: List[OrderCandidate], spec: Specification[OrderCandidate]) -> List[OrderCandidate]:
    """
    Фильтрация заказов по спецификации.
    
    Args:
        orders: Список заказов.
        spec: Спецификация для фильтрации.
        
    Returns:
        Отфильтрованный список заказов.
    """
    return [order for order in orders if spec.is_satisfied_by(order)]


# Демонстрация использования

if __name__ == '__main__':
    orders = create_sample_orders()
    
    print("Все заказы:")
    for order in orders:
        print(f"  #{order.id}: {order.status}, {order.priority}, {order.days_in_service} дн.")
    
    print("\n📋 Просроченные заказы (>7 дней):")
    overdue_spec = SpecificationFactory.overdue(7)
    overdue_orders = filter_orders(orders, overdue_spec)
    for order in overdue_orders:
        print(f"  #{order.id}: {order.status}, {order.days_in_service} дн.")
    
    print("\n⚠️ Заказы требующие внимания:")
    attention_spec = SpecificationFactory.needs_attention()
    attention_orders = filter_orders(orders, attention_spec)
    for order in attention_orders:
        print(f"  #{order.id}: {order.status}, {order.priority}, {order.days_in_service} дн.")
    
    print("\n💰 Заказы стоимостью > 10000:")
    expensive_spec = SpecificationFactory.cost_range(min_cost=10000)
    expensive_orders = filter_orders(orders, expensive_spec)
    for order in expensive_orders:
        print(f"  #{order.id}: {order.total_cost} руб.")
    
    print("\n🔥 Срочные и просроченные:")
    complex_spec = (
        SpecificationFactory.by_priority('Срочный')
        .and_(SpecificationFactory.overdue(5))
    )
    urgent_overdue = filter_orders(orders, complex_spec)
    for order in urgent_overdue:
        print(f"  #{order.id}: {order.status}, {order.priority}, {order.days_in_service} дн.")
