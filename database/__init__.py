#!/usr/bin/env python3

"""Модуль для работы с базой данных"""

from .client_db import ClientDatabaseManager
from .db_config import DatabaseConfig, DatabaseType, get_db_config
from .db_manager import Database
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
from .sqlalchemy_models import Base, Client, Settings, WorkTemplate
from .sqlalchemy_models import Device as DeviceModel

__all__ = [
    # SQLAlchemy models
    "Base",
    # Repository pattern
    "BaseRepository",
    "Client",
    "ClientDatabaseManager",
    "ClientRepository",
    # Legacy API
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
