"""Core Package Initialization
Экспорт основных компонентов ядра приложения.
Реализует паттерн Facade для упрощения доступа к подсистемам.
SSOT: Единая точка входа во все контракты и сервисы ядра.
"""

from config import APP_VERSION
from core.base import (
    BaseGenerator,
    BaseRepository,
    BaseService,
    BaseViewModel,
    DependencyInjectableMixin,
    ExceptionHandlingMixin,
    LoggableMixin,
)
from core.events import Event, EventBus, EventType, get_event_bus
from core.kernel import ServiceUpCore, get_core
from core.logging import (
    # Exceptions
    BaseAppError,
    BluetoothCallError,
    BluetoothConnectionError,
    BluetoothError,
    BusinessRuleViolation,
    ConfigurationError,
    CoreError,
    DatabaseError,
    DomainException,
    ExternalServiceError,
    InfrastructureError,
    NotFoundError,
    NotificationError,
    PDFGenerationError,
    PermissionError,
    ServiceError,
    ValidationError,
    # Logger
    get_logger,
    setup_logging,
)

__version__ = APP_VERSION
__author__ = "ServiceUP Team"

__all__ = [
    # Exceptions
    "BaseAppError",
    # Base Classes (New Architecture)
    "BaseGenerator",
    "BaseRepository",
    "BaseService",
    "BaseViewModel",
    "BluetoothCallError",
    "BluetoothConnectionError",
    "BluetoothError",
    "BusinessRuleViolation",
    "ConfigurationError",
    "CoreError",
    "DatabaseError",
    # Mixins
    "DependencyInjectableMixin",
    "DomainException",
    # Events
    "Event",
    "EventBus",
    "EventType",
    "ExceptionHandlingMixin",
    "ExternalServiceError",
    "InfrastructureError",
    "LoggableMixin",
    "NotFoundError",
    "NotificationError",
    "PDFGenerationError",
    "PermissionError",
    "ServiceError",
    # Kernel (единственная точка входа — см. AUDIT_REPORT_v20.md)
    "ServiceUpCore",
    "ValidationError",
    "get_core",
    # Functions
    "get_event_bus",
    "get_logger",
    "setup_logging",
]
