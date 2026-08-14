"""
Core Base Classes for Unified Architecture.
Provides logging, exception handling, and DI access out-of-the-box.
"""
import logging
from typing import Any, Optional, TypeVar
from abc import ABC

from core.application import CoreApplication
from core.logging.logger import get_logger
from core.logging.exceptions import CoreException

T = TypeVar('T')

class LoggableMixin:
    """Mixin providing automatic logger initialization."""
    
    _logger: logging.Logger
    
    def __init__(self, name: Optional[str] = None):
        if not hasattr(self, '_logger'):
            logger_name = name or self.__class__.__name__
            self._logger = get_logger(logger_name)
    
    @property
    def log(self) -> logging.Logger:
        return self._logger

class ExceptionHandlingMixin:
    """Mixin providing centralized exception handling."""
    
    def safe_execute(self, func, *args, default: Any = None, **kwargs):
        """Execute function with automatic exception handling and logging."""
        try:
            return func(*args, **kwargs)
        except CoreException:
            # Re-raise domain exceptions as is
            raise
        except Exception as e:
            self._logger.exception(f"Error in {func.__name__}: {str(e)}")
            if default is not None:
                return default
            raise

class DependencyInjectableMixin:
    """Mixin providing access to Core Application services."""
    
    _app: Optional[CoreApplication] = None
    
    @classmethod
    def set_application(cls, app: CoreApplication):
        cls._app = app
    
    @property
    def app(self) -> CoreApplication:
        if self._app is None:
            self._app = CoreApplication.get_instance()
        return self._app
    
    def get_service(self, service_type: type[T]) -> T:
        return self.app.get_service(service_type)
    
    def get_repository(self, repo_type: type[T]) -> T:
        return self.app.get_repository(repo_type)

class BaseService(LoggableMixin, ExceptionHandlingMixin, DependencyInjectableMixin, ABC):
    """
    Base class for all Application Services.
    Provides: logging, exception handling, DI access.
    """
    pass

class BaseRepository(LoggableMixin, ExceptionHandlingMixin, DependencyInjectableMixin, ABC):
    """
    Base class for all Infrastructure Repositories.
    Provides: logging, exception handling, DB access via DI.
    """
    pass

class BaseViewModel(LoggableMixin, ExceptionHandlingMixin, DependencyInjectableMixin, ABC):
    """
    Base class for all GUI ViewModels / Panels.
    Provides: logging, exception handling, service access.
    """
    pass

class BaseGenerator(LoggableMixin, ExceptionHandlingMixin, ABC):
    """
    Base class for generators (PDF, Reports, etc.).
    Provides: logging, exception handling.
    """
    pass
