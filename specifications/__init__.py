#!/usr/bin/env python3

"""Модуль спецификаций для бизнес-правил.

Экспортирует компоненты Specification Pattern для использования в приложении.
"""

from .order_specifications import (
    AndSpecification,
    CostRangeSpecification,
    HighPriorityUrgentSpecification,
    LambdaSpecification,
    NotSpecification,
    # Модели
    OrderCandidate,
    OrSpecification,
    OverdueSpecification,
    PrioritySpecification,
    ReadyForPickupSpecification,
    # Базовые классы
    Specification,
    # Фабрика
    SpecificationFactory,
    # Конкретные спецификации
    StatusSpecification,
    create_sample_orders,
    # Утилиты
    filter_orders,
)

__all__ = [
    "AndSpecification",
    "CostRangeSpecification",
    "HighPriorityUrgentSpecification",
    "LambdaSpecification",
    "NotSpecification",
    "OrSpecification",
    # Модели
    "OrderCandidate",
    "OverdueSpecification",
    "PrioritySpecification",
    "ReadyForPickupSpecification",
    # Базовые классы
    "Specification",
    # Фабрика
    "SpecificationFactory",
    # Конкретные спецификации
    "StatusSpecification",
    "create_sample_orders",
    # Утилиты
    "filter_orders",
]
