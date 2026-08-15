#!/usr/bin/env python3

"""Сервисный слой для бизнес-логики.

Отделяет бизнес-правила от слоя доступа к данным (Repositories) и слоя представления (GUI/API).
Соблюдает принципы SOLID, особенно Single Responsibility Principle (SRP).
"""

from services.service_layer import (
    BaseService,
    ClientService,
    OrderService,
    create_services,
)

__all__ = [
    "BaseService",
    "ClientService",
    "OrderService",
    "create_services",
]
