#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль спецификаций для бизнес-правил.

Экспортирует компоненты Specification Pattern для использования в приложении.
"""

from .order_specifications import (
    # Базовые классы
    Specification,
    AndSpecification,
    OrSpecification,
    NotSpecification,
    LambdaSpecification,
    
    # Модели
    OrderCandidate,
    
    # Конкретные спецификации
    StatusSpecification,
    PrioritySpecification,
    OverdueSpecification,
    CostRangeSpecification,
    ReadyForPickupSpecification,
    HighPriorityUrgentSpecification,
    
    # Фабрика
    SpecificationFactory,
    
    # Утилиты
    filter_orders,
    create_sample_orders,
)

__all__ = [
    # Базовые классы
    'Specification',
    'AndSpecification',
    'OrSpecification',
    'NotSpecification',
    'LambdaSpecification',
    
    # Модели
    'OrderCandidate',
    
    # Конкретные спецификации
    'StatusSpecification',
    'PrioritySpecification',
    'OverdueSpecification',
    'CostRangeSpecification',
    'ReadyForPickupSpecification',
    'HighPriorityUrgentSpecification',
    
    # Фабрика
    'SpecificationFactory',
    
    # Утилиты
    'filter_orders',
    'create_sample_orders',
]
