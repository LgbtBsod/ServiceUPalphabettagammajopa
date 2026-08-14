#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Сервисный слой для бизнес-логики.

Отделяет бизнес-правила от слоя доступа к данным (Repositories) и слоя представления (GUI/API).
Соблюдает принципы SOLID, особенно Single Responsibility Principle (SRP).
"""

from services.service_layer import (
    BaseService,
    OrderService,
    ClientService,
    create_services,
)

__all__ = [
    'BaseService',
    'OrderService',
    'ClientService',
    'create_services',
]
