"""Кэш и управление доступом между модулями.

Этот модуль реализует:
1. Кэширование данных модулей в ядре
2. Синглетон-реестр экземпляров модулей
3. Контроль доступа между модулями только через ядро
4. Изоляцию db_access и других критических ресурсов

Принципы:
- Модули не общаются напрямую друг с другом
- Все межмодульные вызовы через ядро (ServiceUpCore)
- Ядро кэширует данные и предоставляет синглетоны модулей
- DB Access доступен только через ядро для предотвращения дублирования
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from threading import RLock
from typing import TYPE_CHECKING, Any

from core.base import LoggableMixin

if TYPE_CHECKING:
    from datetime import timedelta


@dataclass
class CacheEntry[T]:
    """Запись в кэше."""

    value: T
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """Проверяет истечение срока действия."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def touch(self) -> None:
        """Обновляет время последнего доступа."""
        self.last_accessed = time.time()
        self.access_count += 1


class ModuleCache(LoggableMixin):
    """Кэш для хранения данных модулей.

    Пример использования:
        cache = ModuleCache()

        # Установка значения с TTL 5 минут
        cache.set("orders:active", order_list, ttl_seconds=300)

        # Получение значения
        orders = cache.get("orders:active")

        # Вызов функции с кэшированием результата
        @cache.cached(key_func=lambda self, user_id: f"user:{user_id}")
        def get_user_data(user_id: int):
            return db.query(...)
    """

    def __init__(self, max_size: int = 1000, default_ttl_seconds: int | None = None):
        super().__init__()
        self._cache: dict[str, CacheEntry[Any]] = {}
        self._lock = RLock()
        self._max_size = max_size
        self._default_ttl = default_ttl_seconds
        self._hits = 0
        self._misses = 0

    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> None:
        """Устанавливает значение в кэш.

        Args:
            key: Уникальный ключ
            value: Значение для кэширования
            ttl_seconds: Время жизни в секундах (None = без ограничения)
        """
        with self._lock:
            # Удаляем старые записи если кэш переполнен
            if len(self._cache) >= self._max_size:
                self._evict_oldest()

            ttl = ttl_seconds or self._default_ttl
            expires_at = None
            if ttl is not None:
                expires_at = time.time() + ttl

            entry = CacheEntry(
                value=value,
                expires_at=expires_at,
            )

            self._cache[key] = entry
            self.logger.debug(f"Cache SET: {key} (TTL={ttl})")

    def get[T](self, key: str, default: T | None = None) -> T | None:
        """Получает значение из кэша.

        Args:
            key: Ключ
            default: Значение по умолчанию если ключ не найден

        Returns:
            Значение из кэша или default
        """
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._misses += 1
                self.logger.debug(f"Cache MISS: {key}")
                return default

            if entry.is_expired():
                del self._cache[key]
                self._misses += 1
                self.logger.debug(f"Cache EXPIRED: {key}")
                return default

            entry.touch()
            self._hits += 1
            self.logger.debug(f"Cache HIT: {key} (accesses={entry.access_count})")
            return entry.value

    def delete(self, key: str) -> bool:
        """Удаляет запись из кэша.

        Returns:
            True если запись существовала
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self.logger.debug(f"Cache DELETE: {key}")
                return True
            return False

    def clear(self) -> None:
        """Очищает весь кэш."""
        with self._lock:
            self._cache.clear()
            self.logger.info("Cache cleared")

    def invalidate_pattern(self, pattern: str) -> int:
        """Инвалидирует записи по шаблону.

        Args:
            pattern: Шаблон ключа (например "orders:*")

        Returns:
            Количество удалённых записей
        """
        import fnmatch

        with self._lock:
            keys_to_delete = [
                key for key in self._cache if fnmatch.fnmatch(key, pattern)
            ]
            for key in keys_to_delete:
                del self._cache[key]

            self.logger.debug(f"Invalidated {len(keys_to_delete)} keys matching '{pattern}'")
            return len(keys_to_delete)

    def cached(
        self,
        key: str | None = None,
        key_func: Callable[..., str] | None = None,
        ttl_seconds: int | None = None,
    ) -> Callable:
        """Декоратор для кэширования результатов функции.

        Args:
            key: Статический ключ кэша
            key_func: Функция для генерации ключа из аргументов
            ttl_seconds: Время жизни кэша

        Пример:
            @cache.cached(key_func=lambda self, user_id: f"user:{user_id}", ttl_seconds=60)
            def get_user_data(self, user_id: int):
                ...
        """

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Определяем ключ
                if key_func is not None:
                    cache_key = key_func(*args, **kwargs)
                elif key is not None:
                    cache_key = key
                else:
                    # Генерируем ключ из имени функции и аргументов
                    cache_key = f"{func.__module__}:{func.__name__}:{str(args)}:{str(kwargs)}"

                # Пытаемся получить из кэша
                cached_value = self.get(cache_key)
                if cached_value is not None:
                    return cached_value

                # Вызываем функцию
                result = func(*args, **kwargs)

                # Сохраняем в кэш
                self.set(cache_key, result, ttl_seconds=ttl_seconds)

                return result

            return wrapper

        return decorator

    def _evict_oldest(self) -> None:
        """Удаляет самую старую запись."""
        if not self._cache:
            return

        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].last_accessed,
        )
        del self._cache[oldest_key]
        self.logger.debug(f"Evicted oldest cache entry: {oldest_key}")

    def get_stats(self) -> dict[str, Any]:
        """Возвращает статистику кэша."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0

            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate_percent": round(hit_rate, 2),
                "default_ttl_seconds": self._default_ttl,
            }


@dataclass
class ModuleSingleton:
    """Информация о синглетоне модуля."""

    name: str
    instance: Any
    module_type: type
    initialized_at: float = field(default_factory=time.time)
    dependencies: list[str] = field(default_factory=list)
    api: Any | None = None


class ModuleRegistrySingleton(LoggableMixin):
    """Реестр синглетонов модулей.

    Хранит экземпляры всех модулей как синглетоны.
    Модули получают доступ друг к другу только через этот реестр.

    Пример:
        registry = ModuleRegistrySingleton()

        # Регистрация модуля
        registry.register("orders", orders_module_instance, OrdersModuleAPI)

        # Получение модуля
        orders_api = registry.get_api("orders")

        # Вызов метода другого модуля
        result = registry.call_method("billing", "calculate_total", order_id=123)
    """

    def __init__(self):
        super().__init__()
        self._modules: dict[str, ModuleSingleton] = {}
        self._apis: dict[str, Any] = {}
        self._lock = RLock()
        self._db_access_module: str | None = None  # Специальная ссылка на db_access

    def register(
        self,
        name: str,
        instance: Any,
        module_type: type,
        api: Any | None = None,
        dependencies: list[str] | None = None,
    ) -> None:
        """Регистрирует модуль как синглетон.

        Args:
            name: Уникальное имя модуля
            instance: Экземпляр модуля
            module_type: Тип модуля
            api: Публичный API модуля (если есть)
            dependencies: Список зависимостей от других модулей
        """
        with self._lock:
            if name in self._modules:
                self.logger.warning(f"Module '{name}' already registered, re-registering")

            # Особая обработка для db_access
            if name == "db_access":
                self._db_access_module = name

            singleton = ModuleSingleton(
                name=name,
                instance=instance,
                module_type=module_type,
                dependencies=dependencies or [],
                api=api,
            )

            self._modules[name] = singleton

            if api is not None:
                self._apis[name] = api

            self.logger.info(f"Module '{name}' registered as singleton")

    def get_instance(self, name: str) -> Any | None:
        """Получает экземпляр модуля по имени.

        WARNING: Прямой доступ к экземпляру нарушает инкапсуляцию.
        Используйте get_api() вместо этого.
        """
        with self._lock:
            singleton = self._modules.get(name)
            if singleton is None:
                self.logger.error(f"Module '{name}' not found")
                return None
            return singleton.instance

    def get_api(self, name: str) -> Any | None:
        """Получает публичный API модуля.

        Это предпочтительный способ взаимодействия с модулями.
        """
        with self._lock:
            api = self._apis.get(name)
            if api is None:
                self.logger.error(f"API for module '{name}' not found")
                return None
            return api

    def call_method(
        self,
        module_name: str,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Вызывает метод модуля через его API.

        Это основной способ межмодульного взаимодействия.
        Модули НЕ должны импортировать друг друга напрямую.

        Args:
            module_name: Имя целевого модуля
            method_name: Имя метода для вызова
            *args: Позиционные аргументы
            **kwargs: Именованные аргументы

        Returns:
            Результат вызова метода

        Raises:
            ValueError: Если модуль не найден
            AttributeError: Если метод не найден
        """
        api = self.get_api(module_name)
        if api is None:
            raise ValueError(f"Module '{module_name}' not found or has no API")

        method = getattr(api, method_name, None)
        if method is None:
            raise AttributeError(
                f"Module '{module_name}' has no method '{method_name}'"
            )

        self.logger.debug(f"Calling {module_name}.{method_name}()")
        
        # Проверяем что это не bound method с конфликтом имен
        import inspect
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())
        
        # Если первый параметр имеет то же имя что и module_name/method_name - это проблема
        # Но мы уже получили метод через getattr, так что это bound method или static
        return method(*args, **kwargs)

    def get_db_access(self) -> Any | None:
        """Получает доступ к модулю работы с БД.

        Это специальный метод для безопасного доступа к базе данных.
        Только один модуль (db_access) должен управлять подключениями.
        """
        if self._db_access_module is None:
            self.logger.error("DB Access module not registered")
            return None

        return self.get_api(self._db_access_module)

    def unregister(self, name: str) -> bool:
        """Отключает модуль от реестра.

        Returns:
            True если модуль был удалён
        """
        with self._lock:
            if name not in self._modules:
                return False

            del self._modules[name]
            self._apis.pop(name, None)

            if name == self._db_access_module:
                self._db_access_module = None

            self.logger.info(f"Module '{name}' unregistered")
            return True

    def list_modules(self) -> list[dict[str, Any]]:
        """Возвращает список зарегистрированных модулей."""
        with self._lock:
            return [
                {
                    "name": m.name,
                    "type": m.module_type.__name__,
                    "has_api": m.api is not None,
                    "dependencies": m.dependencies,
                    "initialized_at": m.initialized_at,
                }
                for m in self._modules.values()
            ]

    def get_dependencies(self, module_name: str) -> list[str]:
        """Получает список зависимостей модуля."""
        with self._lock:
            singleton = self._modules.get(module_name)
            if singleton is None:
                return []
            return singleton.dependencies.copy()

    def get_dependents(self, module_name: str) -> list[str]:
        """Находит все модули которые зависят от указанного."""
        with self._lock:
            dependents = []
            for m in self._modules.values():
                if module_name in m.dependencies:
                    dependents.append(m.name)
            return dependents


# Глобальные экземпляры (синглетоны)
_module_cache: ModuleCache | None = None
_module_singleton_registry: ModuleRegistrySingleton | None = None


def get_module_cache() -> ModuleCache:
    """Получает глобальный кэш модулей."""
    global _module_cache
    if _module_cache is None:
        _module_cache = ModuleCache()
    return _module_cache


def get_module_singleton_registry() -> ModuleRegistrySingleton:
    """Получает глобальный реестр синглетонов модулей."""
    global _module_singleton_registry
    if _module_singleton_registry is None:
        _module_singleton_registry = ModuleRegistrySingleton()
    return _module_singleton_registry


def reset_module_system() -> None:
    """Сбрасывает систему модулей (для тестов)."""
    global _module_cache, _module_singleton_registry
    if _module_cache:
        _module_cache.clear()
    _module_cache = None
    _module_singleton_registry = None


__all__ = [
    "ModuleCache",
    "ModuleRegistrySingleton",
    "ModuleSingleton",
    "CacheEntry",
    "get_module_cache",
    "get_module_singleton_registry",
    "reset_module_system",
]
