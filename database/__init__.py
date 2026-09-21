#!/usr/bin/env python3

"""Модуль для работы с базой данных"""

from .client_db import ClientDatabaseManager
from .db_config import DatabaseConfig, DatabaseType, get_db_config
from .models import Device, WorkItem, WorkItemsManager
from .sqlalchemy_database import Database, OptimisticLockError, QueryError
from .sqlalchemy_models import Base, Client, Settings, WorkTemplate
from .sqlalchemy_models import Device as DeviceModel

# ВАЖНО: `Database` — это database.sqlalchemy_database.Database (реальный,
# зарегистрированный в Kernel facade). Раньше здесь экспортировался
# db_manager.Database (сырой sqlite3) под тем же именем — GUI-диалоги
# типизировались на неверный класс без .conn (см. AUDIT_REPORT_v21.md).
# Легаси-класс (database.db_manager.Database) больше не реэкспортируется
# отсюда как LegacyDatabase — оба его реальных потребителя
# (database/facade/clients_mixin.py::migrate_client_dbs,
# tools/migrate_to_sqlalchemy.py) уже делают собственный прямой
# `from database.db_manager import Database as _LegacyDatabase`, ни один
# не импортировал через этот пакетный реэкспорт (workflow-найденная
# мёртвая точка входа).
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
    "OptimisticLockError",
    "QueryError",
    "Settings",
    "WorkItem",
    "WorkItemsManager",
    "WorkTemplate",
    "get_db_config",
]
