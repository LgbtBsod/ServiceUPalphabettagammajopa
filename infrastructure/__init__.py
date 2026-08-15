"""Infrastructure Layer.

Реализации интерфейсов для работы с внешними системами:
- Базы данных (SQLite, PostgreSQL)
- Кэширование (Redis, Memory)
- Очереди сообщений
- Файловое хранилище
"""

from infrastructure.cache.memory_cache import MemoryCache
from infrastructure.db.connection import DatabaseConnection, get_db_connection
from infrastructure.db.repositories import (
    BaseRepository,
    ClientRepository,
    DeviceRepository,
)
from infrastructure.licensing import LicenseService
from infrastructure.messaging.event_publisher import EventPublisher
from infrastructure.storage.file_storage import FileStorage

__all__ = [
    # DB
    "BaseRepository",
    "ClientRepository",
    "DatabaseConnection",
    "DeviceRepository",
    # Messaging
    "EventPublisher",
    # Storage
    "FileStorage",
    # Licensing
    "LicenseService",
    # Cache
    "MemoryCache",
    "get_db_connection",
]
