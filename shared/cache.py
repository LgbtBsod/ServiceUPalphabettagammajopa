#!/usr/bin/env python3

"""Кэширование часто используемых данных

Принципы:
- TTL (Time To Live) для актуальности
- LRU (Least Recently Used) для вытеснения
- Thread-safe для многопоточности
- Декораторы для простоты использования
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
K = TypeVar("K")


@dataclass
class CacheEntry[T]:
    """Запись кэша с временем жизни."""

    value: T
    created_at: float
    ttl_seconds: float

    def is_expired(self) -> bool:
        """Проверка истечения TTL."""
        return time.time() > (self.created_at + self.ttl_seconds)


class TTLCache[K, T]:
    """Потокобезопасный кэш с TTL и LRU eviction.

    Параметры:
        max_size: Максимальное количество записей (LRU)
        default_ttl: Время жизни по умолчанию (секунды)
    """

    def __init__(self, max_size: int = 1000, default_ttl: float = 300.0):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[K, CacheEntry[T]] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key: K) -> T | None:
        """Получение значения из кэша."""
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            entry = self._cache[key]

            # Проверка TTL
            if entry.is_expired():
                del self._cache[key]
                self._misses += 1
                logger.debug(f"Кэш: ключ {key} истёк (TTL)")
                return None

            # LRU: перемещаем в конец (свежий)
            self._cache.move_to_end(key)
            self._hits += 1
            return entry.value

    def set(self, key: K, value: T, ttl: float | None = None) -> None:
        """Установка значения в кэш."""
        with self._lock:
            # Если ключ существует - удаляем для обновления позиции
            if key in self._cache:
                del self._cache[key]

            # LRU eviction: удаляем oldest при превышении размера
            while len(self._cache) >= self.max_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                logger.debug(f"Кэш: вытеснена запись {oldest_key} (LRU)")

            entry = CacheEntry(
                value=value, created_at=time.time(), ttl_seconds=ttl or self.default_ttl
            )
            self._cache[key] = entry

    def delete(self, key: K) -> bool:
        """Удаление записи из кэша."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Очистка всего кэша."""
        with self._lock:
            self._cache.clear()
            logger.info("Кэш очищен")

    def cleanup_expired(self) -> int:
        """Удаление всех истёкших записей."""
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items() if entry.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)

    @property
    def stats(self) -> dict[str, Any]:
        """Статистика кэша."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0.0
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate_percent": round(hit_rate, 2),
                "expired_count": sum(1 for e in self._cache.values() if e.is_expired()),
            }

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def __contains__(self, key: K) -> bool:
        with self._lock:
            if key not in self._cache:
                return False
            entry = self._cache[key]
            if entry.is_expired():
                del self._cache[key]
                return False
            return True


# Глобальные кэши для различных данных
_order_cache = TTLCache[str, dict](max_size=500, default_ttl=60.0)
_client_cache = TTLCache[str, dict](max_size=1000, default_ttl=300.0)
_dictionary_cache = TTLCache[str, list](max_size=50, default_ttl=600.0)
_stats_cache = TTLCache[str, Any](max_size=20, default_ttl=30.0)


def cached_operation(
    cache: TTLCache,
    key_prefix: str = "",
    ttl: float | None = None,
    key_arg_index: int = 0,
):
    """Декоратор для кэширования результатов функций.

    Пример:
        @cached_operation(_order_cache, key_prefix="order:", ttl=60.0)
        def get_order(order_id: str) -> Dict:
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Формируем ключ из аргументов
            if key_arg_index < len(args):
                key_value = args[key_arg_index]
            elif kwargs:
                key_value = next(iter(kwargs.values()))
            else:
                key_value = "default"

            cache_key = f"{key_prefix}{hash(str(key_value))}"

            # Попытка получить из кэша
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Кэш: hit для {cache_key}")
                return cached_result

            # Вызов функции
            result = func(*args, **kwargs)

            # Сохранение в кэш
            cache.set(cache_key, result, ttl=ttl)
            logger.debug(f"Кэш: miss для {cache_key}, сохранено")

            return result

        return wrapper

    return decorator


def invalidate_cache(
    cache: TTLCache, key_prefix: str = "", key_value: Any = None
) -> None:
    """Утилита для инвалидации кэша."""
    if key_value is not None:
        cache_key = f"{key_prefix}{hash(str(key_value))}"
        cache.delete(cache_key)
        logger.info(f"Кэш: инвалидирован {cache_key}")
    else:
        cache.clear()
        logger.info("Кэш: полностью очищен")


def get_cache_stats() -> dict[str, Any]:
    """Получение статистики всех кэшей."""
    return {
        "orders": _order_cache.stats,
        "clients": _client_cache.stats,
        "dictionaries": _dictionary_cache.stats,
        "stats": _stats_cache.stats,
    }


def cleanup_all_caches() -> int:
    """Очистка истёкших записей во всех кэшах."""
    total_cleaned = 0
    total_cleaned += _order_cache.cleanup_expired()
    total_cleaned += _client_cache.cleanup_expired()
    total_cleaned += _dictionary_cache.cleanup_expired()
    total_cleaned += _stats_cache.cleanup_expired()

    if total_cleaned > 0:
        logger.info(f"Кэш: удалено {total_cleaned} истёкших записей")

    return total_cleaned
