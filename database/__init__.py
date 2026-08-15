#!/usr/bin/env python3

"""Модуль для работы с базой данных"""

from .client_db import ClientDatabaseManager
from .db_config import DatabaseConfig, DatabaseType, get_db_config
from .db_manager import Database as LegacyDatabase
from .factories import DatabaseFactory, get_database_factory, reset_database_factory
from .models import Device, WorkItem, WorkItemsManager
from .repositories import (
    BaseRepository,
    ClientRepository,
    DatabaseConnection,
    DeviceRepository,
    SQLAlchemyConnection,
    UnitOfWork,
)
from .sqlalchemy_database import Database
from .sqlalchemy_models import Base, Client, Settings, WorkTemplate
from .sqlalchemy_models import Device as DeviceModel

# ВАЖНО: `Database` — это database.sqlalchemy_database.Database (реальный,
# зарегистрированный в Kernel facade). Раньше здесь экспортировался
# db_manager.Database (сырой sqlite3) под тем же именем — GUI-диалоги
# типизировались на неверный класс без .conn (см. AUDIT_REPORT_v21.md).
# Явный доступ к legacy-классу — через LegacyDatabase.

__all__ = [
    # SQLAlchemy models
    "Base",
    # Repository pattern
    "BaseRepository",
    "Client",
    "ClientDatabaseManager",
    "ClientRepository",
    # Facade (SQLAlchemy, зарегистрирован в Kernel как 'db_access')
    "Database",
    # Configuration
    "DatabaseConfig",
    "DatabaseConnection",
    # Factory pattern
    "DatabaseFactory",
    "DatabaseType",
    "Device",
    "DeviceModel",
    "DeviceRepository",
    # Legacy raw-sqlite3 API (не использовать напрямую в новом коде)
    "LegacyDatabase",
    "SQLAlchemyConnection",
    "Settings",
    "UnitOfWork",
    "WorkItem",
    "WorkItemsManager",
    "WorkTemplate",
    "get_database_factory",
    "get_db_config",
    "reset_database_factory",
]
