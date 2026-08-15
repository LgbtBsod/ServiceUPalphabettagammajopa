"""Dependency Injection Container.

Реализует легкий DI контейнер для управления зависимостями.
Поддерживает:
- Singleton и Transient жизненные циклы
- Автоматическое разрешение зависимостей
- Factory функции
- Lazy loading
"""

from __future__ import annotations

import contextlib
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import (
    TYPE_CHECKING,
    Any,
    Self,
    TypeVar,
    get_type_hints,
)

from core.base import LoggableMixin

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

T = TypeVar("T")


class ServiceLifetime(Enum):
    """Жизненный цикл сервиса."""

    SINGLETON = "singleton"  # Один экземпляр на все приложение
    TRANSIENT = "transient"  # Новый экземпляр при каждом запросе
    SCOPED = "scoped"  # Один экземпляр в рамках scope (не реализовано)


@dataclass
class ServiceDescriptor:
    """Описание зарегистрированного сервиса."""

    service_type: type
    implementation_type: type | None = None
    factory: Callable | None = None
    lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT
    instance: Any | None = None
    dependencies: set[type] = field(default_factory=set)


class ResolutionError(Exception):
    """Ошибка разрешения зависимости."""


class CircularDependencyError(ResolutionError):
    """Ошибка циклической зависимости."""


class ServiceNotFoundError(ResolutionError):
    """Сервис не найден."""


class DIContainer(LoggableMixin):
    """Контейнер внедрения зависимостей.

    Пример использования:
        container = DIContainer()

        # Регистрация
        container.register_singleton(Database, SQLAlchemyDatabase)
        container.register_transient(OrderService, OrderServiceImpl)
        container.register_factory(lambda c: Config.load_from_file())

        # Разрешение
        db = container.resolve(Database)
        order_service = container.resolve(OrderService)

        # Автоматическое создание
        order_service = container.create(OrderServiceImpl)
    """

    def __init__(self):
        super().__init__()
        self._services: dict[type, ServiceDescriptor] = {}
        self._aliases: dict[str, type] = {}
        self._resolution_stack: list[type] = []
        self._scopes: list[dict[type, Any]] = []

    def register_singleton(
        self,
        service_type: type[T],
        implementation: type[T] | Callable | None = None,
    ) -> DIContainer:
        """Регистрирует сервис как Singleton."""
        return self._register(
            service_type,
            implementation,
            ServiceLifetime.SINGLETON,
        )

    def register_transient(
        self,
        service_type: type[T],
        implementation: type[T] | Callable | None = None,
    ) -> DIContainer:
        """Регистрирует сервис как Transient."""
        return self._register(
            service_type,
            implementation,
            ServiceLifetime.TRANSIENT,
        )

    def register_factory(
        self,
        factory: Callable[[DIContainer], Any],
        service_type: type | None = None,
    ) -> DIContainer:
        """Регистрирует фабрику для создания сервиса."""
        if service_type is None:
            # Пытаемся определить тип возврата
            hints = get_type_hints(factory)
            service_type = hints.get("return", Any)

        descriptor = ServiceDescriptor(
            service_type=service_type,
            factory=factory,
            lifetime=ServiceLifetime.TRANSIENT,
        )

        self._services[service_type] = descriptor
        self.logger.debug(f"Registered factory for {service_type.__name__}")

        return self

    def register_instance(
        self,
        service_type: type[T],
        instance: T,
    ) -> DIContainer:
        """Регистрирует существующий экземпляр."""
        descriptor = ServiceDescriptor(
            service_type=service_type,
            instance=instance,
            lifetime=ServiceLifetime.SINGLETON,
        )

        self._services[service_type] = descriptor
        self.logger.debug(f"Registered instance for {service_type.__name__}")

        return self

    def add_alias(self, alias: str, service_type: type) -> DIContainer:
        """Добавляет именованный алиас для сервиса."""
        self._aliases[alias] = service_type
        self.logger.debug(f"Added alias '{alias}' for {service_type.__name__}")
        return self

    def resolve(self, service_type: type[T] | str) -> T:
        """Разрешает зависимость по типу или имени.

        Args:
            service_type: Тип сервиса или строковое имя

        Returns:
            Экземпляр сервиса

        Raises:
            ServiceNotFoundError: Сервис не найден
            CircularDependencyError: Обнаружена циклическая зависимость
        """
        # Разрешаем алиас
        if isinstance(service_type, str):
            if service_type not in self._aliases:
                raise ServiceNotFoundError(f"Alias '{service_type}' not found")
            service_type = self._aliases[service_type]

        # Проверяем наличие сервиса
        if service_type not in self._services:
            # Пытаемся авто-создать
            if inspect.isclass(service_type):
                self.logger.debug(f"Auto-registering {service_type.__name__}")
                return self._create_instance(service_type)
            raise ServiceNotFoundError(f"Service {service_type} not registered")

        descriptor = self._services[service_type]

        # Возвращаем существующий экземпляр для singleton
        if (
            descriptor.lifetime == ServiceLifetime.SINGLETON
            and descriptor.instance is not None
        ):
            return descriptor.instance

        # Создаем новый экземпляр
        instance = self._resolve_service(descriptor)

        # Сохраняем для singleton
        if descriptor.lifetime == ServiceLifetime.SINGLETON:
            descriptor.instance = instance

        return instance

    def resolve_all(self, service_type: type[T]) -> list[T]:
        """Разрешает все реализации интерфейса."""
        instances = []

        for desc in self._services.values():
            if desc.service_type == service_type or (
                inspect.isclass(desc.service_type)
                and inspect.isclass(service_type)
                and issubclass(desc.service_type, service_type)
            ):
                try:
                    instances.append(self.resolve(desc.service_type))
                except Exception as e:
                    self.logger.warning(f"Failed to resolve {desc.service_type}: {e}")

        return instances

    def create(self, cls: type[T]) -> T:
        """Создает экземпляр класса с автоматическим внедрением зависимостей."""
        return self._create_instance(cls)

    def create_scope(self) -> DIScope:
        """Создает новую область видимости (scope)."""
        scope = DIScope(self)
        self._scopes.append(scope.services)
        return scope

    def _register(
        self,
        service_type: type,
        implementation: type | Callable | None,
        lifetime: ServiceLifetime,
    ) -> DIContainer:
        """Внутренний метод регистрации."""
        if implementation is None:
            implementation = service_type

        descriptor = ServiceDescriptor(
            service_type=service_type,
            implementation_type=implementation
            if inspect.isclass(implementation)
            else None,
            factory=implementation
            if callable(implementation) and not inspect.isclass(implementation)
            else None,
            lifetime=lifetime,
        )

        # Определяем зависимости
        if inspect.isclass(implementation):
            descriptor.dependencies = self._get_dependencies(implementation)

        self._services[service_type] = descriptor
        self.logger.debug(
            f"Registered {service_type.__name__} ({lifetime.value})"
            f"{f' -> {implementation.__name__}' if implementation != service_type else ''}"
        )

        return self

    def _resolve_service(self, descriptor: ServiceDescriptor) -> Any:
        """Разрешает сервис из дескриптора."""
        if descriptor.instance is not None:
            return descriptor.instance

        if descriptor.factory is not None:
            return descriptor.factory(self)

        if descriptor.implementation_type is not None:
            return self._create_instance(descriptor.implementation_type)

        raise ResolutionError(f"Cannot resolve {descriptor.service_type}")

    def _create_instance(self, cls: type[T]) -> T:
        """Создает экземпляр класса с внедрением зависимостей."""
        # Проверка на циклические зависимости
        if cls in self._resolution_stack:
            cycle = " -> ".join(t.__name__ for t in [*self._resolution_stack, cls])
            raise CircularDependencyError(f"Circular dependency detected: {cycle}")

        self._resolution_stack.append(cls)

        try:
            # Получаем конструктор
            sig = inspect.signature(cls.__init__)
            params = sig.parameters

            # Определяем зависимости
            dependencies = {}
            for name, param in params.items():
                if name == "self":
                    continue

                # Получаем тип параметра
                param_type = param.annotation
                if param_type == inspect.Parameter.empty:
                    continue

                # Разрешаем зависимость
                try:
                    dependencies[name] = self.resolve(param_type)
                except ServiceNotFoundError:
                    if param.default != inspect.Parameter.empty:
                        dependencies[name] = param.default
                    else:
                        raise

            # Создаем экземпляр
            instance = cls(**dependencies)

            self.logger.debug(f"Created instance of {cls.__name__}")
            return instance

        finally:
            self._resolution_stack.pop()

    def _get_dependencies(self, cls: type) -> set[type]:
        """Получает список зависимостей класса."""
        dependencies = set()

        try:
            sig = inspect.signature(cls.__init__)
            for param in sig.parameters.values():
                if param.name == "self":
                    continue

                if param.annotation != inspect.Parameter.empty:
                    dependencies.add(param.annotation)
        except Exception:
            pass

        return dependencies

    def build(self) -> DIContainer:
        """Финализирует конфигурацию контейнера (для будущего расширения)."""
        self.logger.info(f"Container built with {len(self._services)} services")
        return self


class DIScope:
    """Область видимости для scoped сервисов."""

    def __init__(self, container: DIContainer):
        self.container = container
        self.services: dict[type, Any] = {}

    def resolve(self, service_type: type[T]) -> T:
        """Разрешает сервис в рамках scope."""
        if service_type in self.services:
            return self.services[service_type]

        instance = self.container.resolve(service_type)
        self.services[service_type] = instance
        return instance

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.services.clear()


# Глобальный контейнер
_global_container: DIContainer | None = None


def get_container() -> DIContainer:
    """Получает глобальный DI контейнер."""
    global _global_container
    if _global_container is None:
        _global_container = DIContainer()
    return _global_container


def reset_container() -> None:
    """Сбрасывает глобальный контейнер (для тестов)."""
    global _global_container
    _global_container = None


# Декораторы для автоматического внедрения
def inject(func: Callable) -> Callable:
    """Декоратор для автоматического внедрения зависимостей."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        container = get_container()
        hints = get_type_hints(func)

        # Внедряем зависимости из аннотаций типов
        for name, hint in hints.items():
            if name not in kwargs and name != "return":
                with contextlib.suppress(ServiceNotFoundError):
                    kwargs[name] = container.resolve(hint)

        return func(*args, **kwargs)

    return wrapper


def auto_wire[T](cls: type[T]) -> type[T]:
    """Декоратор класса для автоматического внедрения зависимостей."""
    original_init = cls.__init__

    @wraps(original_init)
    def new_init(self, *args, **kwargs):
        container = get_container()
        hints = get_type_hints(original_init)

        # Внедряем зависимости
        for name, hint in hints.items():
            if name == "self" or name in kwargs:
                continue

            with contextlib.suppress(ServiceNotFoundError):
                kwargs[name] = container.resolve(hint)

        original_init(self, *args, **kwargs)

    cls.__init__ = new_init
    return cls
