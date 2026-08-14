#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Модуль для работы с базой данных"""

from .db_manager import Database
from .client_db import ClientDatabaseManager
from .models import Device, WorkItem, WorkItemsManager
from .factories import DatabaseFactory, get_database_factory, reset_database_factory
from .repositories import (
    BaseRepository,
    DatabaseConnection,
    SQLAlchemyConnection,
    DeviceRepository,
    ClientRepository,
    UnitOfWork,
)
from .sqlalchemy_models import Base, Client, Device as DeviceModel, WorkTemplate, Settings
from .db_config import DatabaseConfig, DatabaseType, get_db_config

__all__ = [
    # Legacy API
    'Database',
    'ClientDatabaseManager',
    'Device',
    'WorkItem',
    'WorkItemsManager',
    # Factory pattern
    'DatabaseFactory',
    'get_database_factory',
    'reset_database_factory',
    # Repository pattern
    'BaseRepository',
    'DatabaseConnection',
    'SQLAlchemyConnection',
    'DeviceRepository',
    'ClientRepository',
    'UnitOfWork',
    # SQLAlchemy models
    'Base',
    'Client',
    'DeviceModel',
    'WorkTemplate',
    'Settings',
    # Configuration
    'DatabaseConfig',
    'DatabaseType',
    'get_db_config',
]
