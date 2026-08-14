"""
Core Base Classes for Unified Architecture - v24.3 Refactored.

Provides logging, exception handling, and DI access out-of-the-box.
All classes inherit from appropriate base class to get these features automatically.

Principles applied:
- SRP: Each mixin has single responsibility
- DRY: No duplication of logging/exception handling code
- SSOT: Single source for base classes
- Dependency Injection: All classes can access DI container
"""
import logging
from typing import Any, Optional, TypeVar, Generic
from abc import ABC

from core.application import CoreApplication
from core.logging.logger import get_logger
from core.logging.exceptions import CoreException, BaseAppError

T = TypeVar('T')
R = TypeVar('R', covariant=True)  # Result type


class LoggableMixin:
    """
    Mixin providing automatic logger initialization.
    
    Usage:
        class MyService(LoggableMixin):
            def do_something(self):
                self.logger.info("Doing something")
    """
    
    _logger: Optional[logging.Logger] = None
    
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
    
    def log_error(self, message: str, exc: Optional[Exception] = None, **kwargs) -> None:
        """Log error message with optional exception."""
        if exc:
            self.logger.error(message, exc_info=exc, extra=kwargs if kwargs else {})
        else:
            self.logger.error(message, extra=kwargs if kwargs else {})
    
    def log_critical(self, message: str, exc: Optional[Exception] = None, **kwargs) -> None:
        """Log critical message with optional exception."""
        if exc:
            self.logger.critical(message, exc_info=exc, extra=kwargs if kwargs else {})
        else:
            self.logger.critical(message, extra=kwargs if kwargs else {})


class ExceptionHandlingMixin:
    """
    Mixin providing centralized exception handling.
    
    Usage:
        class MyService(ExceptionHandlingMixin):
            def do_something(self):
                return self.safe_execute(self._risky_operation, default=[])
    """
    
    def safe_execute(self, func, *args, default: Any = None, **kwargs):
        """
        Execute function with automatic exception handling and logging.
        
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
            self.logger.exception(f"Error in {func.__name__}: {str(e)}")
            if default is not None:
                return default
            raise


class DependencyInjectableMixin(Generic[T]):
    """
    Mixin providing access to Core Application services via DI.
    
    Usage:
        class OrderService(DependencyInjectableMixin):
            def get_order(self, order_id: int):
                repo = self.get_repository(OrderRepository)
                return repo.get_by_id(order_id)
    """
    
    _app: Optional[CoreApplication] = None
    
    @classmethod
    def set_application(cls, app: CoreApplication) -> None:
        """Set application instance (called during bootstrap)."""
        cls._app = app
    
    @property
    def app(self) -> CoreApplication:
        """Get application instance (lazy initialization)."""
        if self._app is None:
            self._app = CoreApplication.get_instance()
        return self._app
    
    def get_service(self, service_type: type[T]) -> T:
        """Get service instance from DI container."""
        return self.app.get_service(service_type)
    
    def get_repository(self, repo_type: type[T]) -> T:
        """Get repository instance from DI container."""
        return self.app.get_repository(repo_type)
    
    def get_config(self, config_type: type[T]) -> T:
        """Get configuration instance from DI container."""
        return self.app.get_config(config_type)


# =============================================================================
# BASE CLASSES - Inherit these for automatic logging + exception handling + DI
# =============================================================================

class BaseService(LoggableMixin, ExceptionHandlingMixin, DependencyInjectableMixin, ABC):
    """
    Base class for all Application Services.
    
    Provides: 
    - Automatic logger (self.logger)
    - Exception handling (self.safe_execute())
    - DI access (self.get_service(), self.get_repository())
    
    Usage:
        class OrderService(BaseService):
            def create_order(self, data: dict):
                return self.safe_execute(self._create_order_impl, default=None)
    """
    pass


class BaseRepository(LoggableMixin, ExceptionHandlingMixin, DependencyInjectableMixin, ABC, Generic[R]):
    """
    Base class for all Infrastructure Repositories.
    
    Provides:
    - Automatic logger (self.logger)
    - Exception handling (self.safe_execute())
    - DI access (self.get_service(), self.get_repository())
    - Generic type parameter for entity type
    
    Usage:
        class OrderRepository(BaseRepository[Order]):
            def get_by_id(self, id: int) -> Optional[Order]:
                return self.safe_execute(self._get_by_id_impl, default=None)
    """
    pass


class BaseViewModel(LoggableMixin, ExceptionHandlingMixin, DependencyInjectableMixin, ABC):
    """
    Base class for all GUI ViewModels / Panels.
    
    Provides:
    - Automatic logger (self.logger)
    - Exception handling (self.safe_execute())
    - Service access (self.get_service())
    
    Usage:
        class OrderViewModel(BaseViewModel):
            def load_order(self, order_id: int):
                return self.safe_execute(self._load_order_impl, default={})
    """
    pass


class BaseGenerator(LoggableMixin, ExceptionHandlingMixin, ABC):
    """
    Base class for generators (PDF, Reports, etc.).
    
    Provides:
    - Automatic logger (self.logger)
    - Exception handling (self.safe_execute())
    
    Usage:
        class PDFReportGenerator(BaseGenerator):
            def generate(self, data: dict) -> bytes:
                return self.safe_execute(self._generate_impl, default=b'')
    """
    pass


class BaseEntity(LoggableMixin, ABC):
    """
    Base class for domain entities.
    
    Provides:
    - Automatic logger (self.logger)
    
    Note: Entities should NOT have DI access or exception handling mixins
    to keep them pure and testable.
    """
    pass


class BaseValueObject(ABC):
    """
    Base class for value objects.
    
    Value objects should be:
    - Immutable (frozen dataclass)
    - Self-validating
    - Without side effects
    
    Note: No logging/DI for value objects to keep them pure.
    """
    pass


class BaseEvent(LoggableMixin, ABC):
    """
    Base class for domain events.
    
    Provides:
    - Automatic logger for event handlers
    
    Usage:
        @dataclass
        class OrderCreatedEvent(BaseEvent):
            order_id: int
            created_at: datetime
    """
    pass


class BaseCommand(LoggableMixin, ABC):
    """
    Base class for CQRS commands.
    
    Provides:
    - Automatic logger for command handlers
    
    Usage:
        @dataclass
        class CreateOrderCommand(BaseCommand):
            customer_id: int
            items: list[OrderItem]
    """
    pass


class BaseQuery(LoggableMixin, ABC):
    """
    Base class for CQRS queries.
    
    Provides:
    - Automatic logger for query handlers
    
    Usage:
        @dataclass
        class GetOrderByIdQuery(BaseQuery):
            order_id: int
    """
    pass


__all__ = [
    # Mixins
    'LoggableMixin',
    'ExceptionHandlingMixin',
    'DependencyInjectableMixin',
    # Base Classes
    'BaseService',
    'BaseRepository',
    'BaseViewModel',
    'BaseGenerator',
    'BaseEntity',
    'BaseValueObject',
    'BaseEvent',
    'BaseCommand',
    'BaseQuery',
]
