"""
Модуль централизованного логирования и обработки исключений.

Предоставляет единую точку входа для логирования во всех компонентах системы,
стандартизированные форматеры и обработчики исключений.
"""

from .logger import get_logger, setup_logging, LogContext, LoggableMixin
from .exceptions import (
    # Base
    BaseAppError,
    AppException,  # Legacy alias
    # Core
    CoreError,
    CoreException,  # Legacy alias
    ConfigurationError,
    AuthenticationError,
    PermissionError,
    # Domain
    DomainException,
    NotFoundError,
    EntityNotFoundException,  # Legacy alias
    ValidationError,
    BusinessRuleViolation,
    # Application/Service
    ServiceError,
    NotificationError,
    AnalyticsError,
    ApplicationException,  # Legacy alias
    ServiceUnavailableError,  # Legacy alias
    CommandExecutionError,  # Legacy alias
    QueryExecutionError,  # Legacy alias
    # Infrastructure
    InfrastructureError,
    InfrastructureException,  # Legacy alias
    DatabaseError,
    RepositoryError,  # Legacy alias
    ExternalServiceError,
    AppFileNotFoundError,
    FileOperationError,  # Legacy alias
    PDFGenerationError,
    TemplateNotFoundError,  # Legacy alias
    QRCodeGenerationError,  # Legacy alias
    # Bluetooth
    BluetoothError,
    BluetoothConnectionError,
    BluetoothCallError,
    MobileConnectionError,  # Legacy alias
    WebSocketError,  # Legacy alias
    # Presentation (Legacy aliases)
    PresentationException,  # Legacy alias
    UIComponentError,  # Legacy alias
    DataBindingError,  # Legacy alias
    # DI (Legacy aliases)
    DIContainerError,  # Legacy alias
    ServiceNotRegisteredError,  # Legacy alias
)

__all__ = [
    # Logger
    "get_logger",
    "setup_logging",
    "LogContext",
    "LoggableMixin",
    # Exceptions - Base
    "BaseAppError",
    "AppException",
    # Core
    "CoreError",
    "ConfigurationError",
    "AuthenticationError",
    "PermissionError",
    # Domain
    "DomainException",
    "NotFoundError",
    "EntityNotFoundException",
    "ValidationError",
    "BusinessRuleViolation",
    # Application/Service
    "ServiceError",
    "NotificationError",
    "AnalyticsError",
    "ApplicationException",
    "ServiceUnavailableError",
    "CommandExecutionError",
    "QueryExecutionError",
    # Infrastructure
    "InfrastructureError",
    "InfrastructureException",  # Legacy alias
    "DatabaseError",
    "RepositoryError",
    "ExternalServiceError",
    "AppFileNotFoundError",
    "FileOperationError",
    "PDFGenerationError",
    "TemplateNotFoundError",
    "QRCodeGenerationError",
    # Bluetooth
    "BluetoothError",
    "BluetoothConnectionError",
    "BluetoothCallError",
    "MobileConnectionError",
    "WebSocketError",
    # Presentation
    "PresentationException",
    "UIComponentError",
    "DataBindingError",
    # DI
    "DIContainerError",
    "ServiceNotRegisteredError",
]
