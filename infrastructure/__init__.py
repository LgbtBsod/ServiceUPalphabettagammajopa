"""
Infrastructure module - инфраструктурные реализации.

Содержит реализации репозиториев, внешние сервисы и адаптеры.
"""

from .db import (
    DeviceRepository,
    ClientRepository,
    UnitOfWork,
    DatabaseConnection,
)

from .licensing import LicenseService

__all__ = [
    'DeviceRepository',
    'ClientRepository',
    'UnitOfWork',
    'DatabaseConnection',
    'LicenseService',
]
