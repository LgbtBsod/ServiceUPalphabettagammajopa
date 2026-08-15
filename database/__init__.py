#!/usr/bin/env python3

"""Модуль для работы с базой данных"""

from .client_db import ClientDatabaseManager
from .db_config import DatabaseConfig, DatabaseType, get_db_config
from .db_manager import Database as LegacyDatabase
from .models import Device, WorkItem, WorkItemsManager
from .sqlalchemy_database import Database
from .sqlalchemy_models import Base, Client, Settings, WorkTemplate
from .sqlalchemy_models import Device as DeviceModel

# ВАЖНО: `Database` — это database.sqlalchemy_database.Database (реальный,
# зарегистрированный в Kernel facade). Раньше здесь экспортировался
# db_manager.Database (сырой sqlite3) под тем же именем — GUI-диалоги
# типизировались на неверный класс без .conn (см. AUDIT_REPORT_v21.md).
# Явный доступ к legacy-классу — через LegacyDatabase.
#
# database/repositories/ (Repository/UnitOfWork/DatabaseFactory) удалены:
# несмотря на импорт при каждом старте приложения (через этот файл),
# ни разу не вызывались живым кодом — sqlalchemy_database.py::Database
# не использует ни один из этих классов. Единственными потребителями
# были уже удалённые services/service_layer.py и тестовые файлы,
# тестировавшие исключительно этот мёртвый стек. См. AUDIT_REPORT_v21.md.

__all__ = [
    # SQLAlchemy models
    "Base",
    "Client",
    "ClientDatabaseManager",
    # Facade (SQLAlchemy, зарегистрирован в Kernel как 'db_access')
    "Database",
    # Configuration
    "DatabaseConfig",
    "DatabaseType",
    "Device",
    "DeviceModel",
    # Legacy raw-sqlite3 API (не использовать напрямую в новом коде)
    "LegacyDatabase",
    "Settings",
    "WorkItem",
    "WorkItemsManager",
    "WorkTemplate",
    "get_db_config",
]
