"""Модуль централизованного логирования и обработки исключений.

Предоставляет единую точку входа для логирования во всех компонентах системы,
стандартизированные форматеры и обработчики исключений.
"""

from .exceptions import (
    # Base
    BaseAppError,
    BluetoothCallError,
    BluetoothConnectionError,
    # Bluetooth
    BluetoothError,
    BusinessRuleViolation,
    ConfigurationError,
    # Core
    CoreError,
    DatabaseError,
    # Domain
    DomainException,
    ExternalServiceError,
    # Infrastructure
    InfrastructureError,
    NotFoundError,
    NotificationError,
    PDFGenerationError,
    PermissionError,
    # Application/Service
    ServiceError,
    ValidationError,
)
from .logger import LogContext, LoggableMixin, get_logger, setup_logging

__all__ = [
    # Exceptions - Base
    "BaseAppError",
    "BluetoothCallError",
    "BluetoothConnectionError",
    # Bluetooth
    "BluetoothError",
    "BusinessRuleViolation",
    "ConfigurationError",
    # Core
    "CoreError",
    "DatabaseError",
    # Domain
    "DomainException",
    "ExternalServiceError",
    # Infrastructure
    "InfrastructureError",
    "LogContext",
    "LoggableMixin",
    "NotFoundError",
    "NotificationError",
    "PDFGenerationError",
    "PermissionError",
    # Application/Service
    "ServiceError",
    "ValidationError",
    # Logger
    "get_logger",
    "setup_logging",
]
