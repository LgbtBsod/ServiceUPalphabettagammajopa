"""Core Base Classes for Unified Architecture - v24.3 Refactored.

Provides logging, exception handling, and DI access out-of-the-box.
All classes inherit from appropriate base class to get these features automatically.

Principles applied:
- SRP: Each mixin has single responsibility
- DRY: No duplication of logging/exception handling code
- SSOT: Single source for base classes
- Dependency Injection: All classes can access DI container
"""

import logging
from abc import ABC
from collections.abc import Callable
from typing import Any

from core.logging.exceptions import BaseAppError
from core.logging.exceptions import PermissionError as PermissionDeniedError
from core.logging.logger import get_logger


class LoggableMixin:
    """Mixin providing automatic logger initialization.

    Usage:
        class MyService(LoggableMixin):
            def do_something(self):
                self.logger.info("Doing something")
    """

    _logger: logging.Logger | None = None

    @property
    def logger(self) -> logging.Logger:
        """Lazy-initialized logger with class name."""
        if self._logger is None:
            self._logger = get_logger(self.__class__.__name__)
        return self._logger

    @property
    def log(self) -> logging.Logger:
        """Alias for logger (backward compatibility)."""
        return self.logger

    def log_debug(self, message: str, **kwargs) -> None:
        """Log debug message with optional context."""
        self.logger.debug(message, extra=kwargs if kwargs else {})

    def log_info(self, message: str, **kwargs) -> None:
        """Log info message with optional context."""
        self.logger.info(message, extra=kwargs if kwargs else {})

    def log_warning(self, message: str, **kwargs) -> None:
        """Log warning message with optional context."""
        self.logger.warning(message, extra=kwargs if kwargs else {})

    def log_error(self, message: str, exc: Exception | None = None, **kwargs) -> None:
        """Log error message with optional exception."""
        if exc:
            self.logger.error(message, exc_info=exc, extra=kwargs if kwargs else {})
        else:
            self.logger.error(message, extra=kwargs if kwargs else {})

    def log_critical(
        self, message: str, exc: Exception | None = None, **kwargs
    ) -> None:
        """Log critical message with optional exception."""
        if exc:
            self.logger.critical(message, exc_info=exc, extra=kwargs if kwargs else {})
        else:
            self.logger.critical(message, extra=kwargs if kwargs else {})

    def msg(self, template: str, level: str = "info", **kwargs) -> str:
        """Форматирует code-based сообщение (utils.messages.Msg.*) И сразу
        логирует его на нужном уровне — одним вызовом вместо двух:

            self.msg(Msg.LOGIN_TAKEN, level="warning", login=command.login)
            # вместо self.logger.warning(Msg.LOGIN_TAKEN.format(login=...))

        Возвращает отформатированный текст — пригодится там, где помимо
        лога нужно ещё и показать сообщение пользователю (messagebox/jsonify),
        не форматируя его дважды. core/base.py намеренно НЕ импортирует
        utils.messages.Msg (не создаёт лишнюю связь между слоями) — сюда
        передаётся уже готовый код-код/шаблон, каким бы он ни был."""
        text = template.format(**kwargs) if kwargs else template
        log_fn = getattr(self.logger, level, None) or self.logger.info
        log_fn(text)
        return text


class ExceptionHandlingMixin:
    """Mixin providing centralized exception handling.

    Usage:
        class MyService(ExceptionHandlingMixin):
            def do_something(self):
                return self.safe_execute(self._risky_operation, default=[])
    """

    def safe_execute(self, func, *args, default: Any = None, **kwargs):
        """Execute function with automatic exception handling and logging.

        Args:
            func: Function to execute
            *args: Positional arguments for func
            default: Default value to return on error
            **kwargs: Keyword arguments for func

        Returns:
            Result of func or default value on error

        Raises:
            CoreException: Re-raised as is (domain exceptions)
            Exception: If no default provided
        """
        try:
            return func(*args, **kwargs)
        except BaseAppError:
            # Re-raise domain exceptions as is (they have proper logging)
            raise
        except Exception as e:
            self.logger.exception(f"Error in {func.__name__}: {e!s}")
            if default is not None:
                return default
            raise


class DependencyInjectableMixin[T]:
    """Mixin providing access to services via the application's DI container.

    Историческая реализация делегировала в core.application.CoreApplication —
    отдельное, неиспользуемое "ядро" (0 потребителей вне этого файла, требовало
    незаявленную зависимость `dependency_injector`, из-за чего падал импорт всего
    пакета core). Удалено при консолидации на единственное ядро
    core.kernel.ServiceUpCore (см. AUDIT_REPORT_v20.md).

    Usage:
        class OrderService(DependencyInjectableMixin):
            def get_order(self, order_id: int):
                repo = self.get_repository(OrderRepository)
                return repo.get_by_id(order_id)
    """

    def _get_core(self):
        from core.kernel import get_core

        return get_core()

    def get_service(self, service_type: type[T]) -> T:
        """Get service instance from the kernel's DI container."""
        return self._get_core().get_service(service_type)

    def get_repository(self, repo_type: type[T]) -> T:
        """Get repository instance from the kernel's DI container."""
        return self._get_core().get_service(repo_type)

    def get_config(self, config_type: type[T]) -> T:
        """Get configuration instance from the kernel's DI container."""
        return self._get_core().get_service(config_type)


# =============================================================================
# PERMISSIONS SCAFFOLDING (декларация, БЕЗ enforcement) — см. TODO_RBAC_ROADMAP.md
# =============================================================================


class PermissionObject:
    """Декларация "объекта полномочий" модуля — по аналогии с объектом
    авторизации SAP (SU21/PFCG): у модуля есть ИМЯ объекта, на который
    проверяются права, набор допустимых операций и опционально — таблица
    БД, которой этот объект соответствует напрямую.

    Это ЧИСТО декларативный каркас — ничего не проверяет само по себе.
    Реальная проверка (plugins.employees.EmployeeService.has_permission())
    сейчас всегда возвращает True. Когда появится ролевая модель (см.
    TODO_RBAC_ROADMAP.md), enforcement будет читать именно эти объявления,
    а не потребует переписывать сервисы заново.

    Пример объявления в сервисе::

        class DeviceService(BaseService):
            permission_object = PermissionObject(
                name="DEVICES",
                operations=("create", "read", "update", "delete"),
                table="devices",
            )
    """

    __slots__ = ("name", "operations", "table")

    def __init__(
        self, name: str, operations: tuple[str, ...], table: str | None = None
    ):
        self.name = name
        self.operations = operations
        self.table = table

    def __repr__(self) -> str:
        return (
            f"PermissionObject(name={self.name!r}, "
            f"operations={self.operations!r}, table={self.table!r})"
        )


class PermissionAwareMixin:
    """Даёт модулю (сервису/репозиторию) декларативную точку для объявления
    объекта полномочий, которым он управляет, + готовую (но по умолчанию
    неактивную) точку проверки — check_permission()/require_permission().

    По умолчанию — permission_object=None (модуль не участвует в
    разграничении прав, как и сейчас все модули приложения). Переопределите
    атрибут класса ``permission_object`` в наследнике, чтобы объявить его.

    check_permission()/require_permission() НИЧЕГО не проверяют сами по
    себе, пока вызывающий код не передаст свой ``checker`` — реальную
    ролевую модель ещё предстоит построить (см. TODO_RBAC_ROADMAP.md).
    Это точка ИНТЕГРАЦИИ, готовая для plugins.employees.EmployeeService.
    has_permission() (сейчас тоже всегда True) как естественной реализации
    checker'а: ``self.require_permission("delete", checker=lambda op:
    employees_api.has_permission(current_employee_id, op))``.
    """

    permission_object: PermissionObject | None = None

    def check_permission(
        self, operation: str, *, checker: Callable[[str], bool] | None = None
    ) -> bool:
        """True, если operation разрешена. Без permission_object или без
        checker — всегда True (тот же смысл, что и текущая заглушка
        EmployeeService.has_permission() — ничего не меняется в поведении,
        пока никто явно не подключил проверяющего).

        Raises:
            ValueError: operation не входит в permission_object.operations —
                программная ошибка вызывающего кода (модуль в принципе не
                заявлял, что управляет такой операцией), а не отказ в доступе.
        """
        if self.permission_object is None:
            return True
        if operation not in self.permission_object.operations:
            raise ValueError(
                f"{self.permission_object.name} не объявляет операцию "
                f"{operation!r} (доступны: {self.permission_object.operations})"
            )
        if checker is None:
            return True
        return checker(operation)

    def require_permission(
        self, operation: str, *, checker: Callable[[str], bool] | None = None
    ) -> None:
        """Как check_permission(), но бросает PermissionDeniedError вместо
        возврата False — удобно как первая строка метода сервиса."""
        if not self.check_permission(operation, checker=checker):
            raise PermissionDeniedError(
                action=operation,
                resource=self.permission_object.name if self.permission_object else "?",
            )


# =============================================================================
# BASE CLASSES - Inherit these for automatic logging + exception handling + DI
# =============================================================================


class BaseService(
    LoggableMixin,
    ExceptionHandlingMixin,
    DependencyInjectableMixin,
    PermissionAwareMixin,
    ABC,
):
    """Base class for all Application Services.

    Provides:
    - Automatic logger (self.logger)
    - Exception handling (self.safe_execute())
    - DI access (self.get_service(), self.get_repository())
    - Декларация объекта полномочий (self.permission_object, опционально)

    Usage:
        class OrderService(BaseService):
            def create_order(self, data: dict):
                return self.safe_execute(self._create_order_impl, default=None)
    """


class BaseRepository[R](
    LoggableMixin,
    ExceptionHandlingMixin,
    DependencyInjectableMixin,
    ABC,
):
    """Base class for all Infrastructure Repositories.

    Provides:
    - Automatic logger (self.logger)
    - Exception handling (self.safe_execute())
    - DI access (self.get_service(), self.get_repository())
    - Generic type parameter for entity type

    Без PermissionAwareMixin — полномочия объявляются на уровне Service
    (граница use-case'ов, см. TODO_RBAC_ROADMAP.md), репозиторий отвечает
    только за персистентность и ничего не решает о доступе.

    Usage:
        class OrderRepository(BaseRepository[Order]):
            def get_by_id(self, id: int) -> Order | None:
                return self.safe_execute(self._get_by_id_impl, default=None)
    """


class BaseViewModel(
    LoggableMixin, ExceptionHandlingMixin, DependencyInjectableMixin, ABC
):
    """Base class for all GUI ViewModels / Panels.

    Provides:
    - Automatic logger (self.logger)
    - Exception handling (self.safe_execute())
    - Service access (self.get_service())

    Usage:
        class OrderViewModel(BaseViewModel):
            def load_order(self, order_id: int):
                return self.safe_execute(self._load_order_impl, default={})
    """


class BaseGenerator(LoggableMixin, ExceptionHandlingMixin, ABC):
    """Base class for generators (PDF, Reports, etc.).

    Provides:
    - Automatic logger (self.logger)
    - Exception handling (self.safe_execute())

    Usage:
        class PDFReportGenerator(BaseGenerator):
            def generate(self, data: dict) -> bytes:
                return self.safe_execute(self._generate_impl, default=b'')
    """


class BaseEntity(LoggableMixin, ABC):
    """Base class for domain entities.

    Provides:
    - Automatic logger (self.logger)

    Note: Entities should NOT have DI access or exception handling mixins
    to keep them pure and testable.
    """


class BaseValueObject(ABC):
    """Base class for value objects.

    Value objects should be:
    - Immutable (frozen dataclass)
    - Self-validating
    - Without side effects

    Note: No logging/DI for value objects to keep them pure.
    """


class BaseEvent(LoggableMixin, ABC):
    """Base class for domain events.

    Provides:
    - Automatic logger for event handlers

    Usage:
        @dataclass
        class OrderCreatedEvent(BaseEvent):
            order_id: int
            created_at: datetime
    """


class BaseCommand(LoggableMixin, ABC):
    """Base class for CQRS commands.

    Provides:
    - Automatic logger for command handlers

    Usage:
        @dataclass
        class CreateOrderCommand(BaseCommand):
            customer_id: int
            items: list[OrderItem]
    """


class BaseQuery(LoggableMixin, ABC):
    """Base class for CQRS queries.

    Provides:
    - Automatic logger for query handlers

    Usage:
        @dataclass
        class GetOrderByIdQuery(BaseQuery):
            order_id: int
    """


__all__ = [
    "BaseCommand",
    "BaseEntity",
    "BaseEvent",
    "BaseGenerator",
    "BaseQuery",
    "BaseRepository",
    # Base Classes
    "BaseService",
    "BaseValueObject",
    "BaseViewModel",
    "DependencyInjectableMixin",
    "ExceptionHandlingMixin",
    # Mixins
    "LoggableMixin",
]
