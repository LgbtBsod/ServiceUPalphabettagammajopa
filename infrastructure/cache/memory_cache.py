"""Memory Cache Implementation.

Простой кэш в памяти с TTL поддержкой.
"""

import logging
from datetime import datetime, timedelta
from threading import RLock
from typing import Any

from core.base import LoggableMixin

logger = logging.getLogger(__name__)


class MemoryCache(LoggableMixin):
    """Кэш в памяти с поддержкой TTL.

    Features:
    - Автоматическое удаление просроченных записей
    - Thread-safe операции
    - Ограничение по размеру (LRU eviction)
    """

    def __init__(self, max_size: int = 1000, default_ttl_seconds: int = 3600):
        super().__init__()
        self._cache: dict[str, dict[str, Any]] = {}
        self._access_order: list = []
        self._max_size = max_size
        self._default_ttl = timedelta(seconds=default_ttl_seconds)
        self._lock = RLock()

        self.logger.debug(
            f"MemoryCache initialized: max_size={max_size}, default_ttl={default_ttl_seconds}s"
        )

    def get(self, key: str) -> Any | None:
        """Получает значение из кэша."""
        with self._lock:
            if key not in self._cache:
                return None

            entry = self._cache[key]

            # Проверяем TTL
            if entry["expires_at"] < datetime.now():
                self._remove(key)
                return None

            # Обновляем порядок доступа (LRU)
            self._update_access_order(key)

            return entry["value"]

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Устанавливает значение в кэш."""
        with self._lock:
            # Вычисляем время жизни
            ttl = timedelta(seconds=ttl_seconds) if ttl_seconds else self._default_ttl
            expires_at = datetime.now() + ttl

            # Если ключ уже существует, обновляем
            if key in self._cache:
                self._cache[key]["value"] = value
                self._cache[key]["expires_at"] = expires_at
                self._update_access_order(key)
                return

            # Проверяем размер и делаем eviction если нужно
            if len(self._cache) >= self._max_size:
                self._evict()

            # Добавляем новую запись
            self._cache[key] = {
                "value": value,
                "expires_at": expires_at,
                "created_at": datetime.now(),
            }
            self._access_order.append(key)

            self.logger.debug(f"Cache set: {key}")

    def delete(self, key: str) -> bool:
        """Удаляет значение из кэша."""
        with self._lock:
            return self._remove(key)

    def clear(self) -> None:
        """Очищает весь кэш."""
        with self._lock:
            self._cache.clear()
            self._access_order.clear()
            self.logger.info("Cache cleared")

    def contains(self, key: str) -> bool:
        """Проверяет наличие ключа в кэше (с учетом TTL)."""
        with self._lock:
            if key not in self._cache:
                return False

            entry = self._cache[key]
            if entry["expires_at"] < datetime.now():
                self._remove(key)
                return False

            return True

    def _remove(self, key: str) -> bool:
        """Внутренний метод удаления."""
        if key in self._cache:
            del self._cache[key]
            if key in self._access_order:
                self._access_order.remove(key)
            return True
        return False

    def _update_access_order(self, key: str) -> None:
        """Обновляет порядок доступа для LRU."""
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

    def _evict(self) -> None:
        """Выполняет LRU eviction oldest entries."""
        # Удаляем сначала просроченные
        now = datetime.now()
        expired_keys = [k for k, v in self._cache.items() if v["expires_at"] < now]
        for key in expired_keys:
            self._remove(key)

        # Если все еще переполнен, удаляем самые старые по доступу
        while len(self._cache) >= self._max_size and self._access_order:
            oldest_key = self._access_order.pop(0)
            if oldest_key in self._cache:
                del self._cache[oldest_key]
                self.logger.debug(f"Cache evicted: {oldest_key}")

    def size(self) -> int:
        """Возвращает текущий размер кэша."""
        return len(self._cache)

    def cleanup_expired(self) -> int:
        """Очищает просроченные записи. Возвращает количество удаленных."""
        with self._lock:
            now = datetime.now()
            expired_keys = [k for k, v in self._cache.items() if v["expires_at"] < now]

            count = 0
            for key in expired_keys:
                if self._remove(key):
                    count += 1

            if count > 0:
                self.logger.debug(f"Cleaned up {count} expired cache entries")

            return count


# Глобальный экземпляр кэша
_global_cache: MemoryCache | None = None


def get_cache(max_size: int = 1000, default_ttl_seconds: int = 3600) -> MemoryCache:
    """Получает глобальный экземпляр кэша."""
    global _global_cache
    if _global_cache is None:
        _global_cache = MemoryCache(max_size, default_ttl_seconds)
    return _global_cache


def reset_cache() -> None:
    """Сбрасывает глобальный кэш (для тестов)."""
    global _global_cache
    _global_cache = None
