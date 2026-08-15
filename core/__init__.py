"""Core Package Initialization
Экспорт основных компонентов ядра приложения.
Реализует паттерн Facade для упрощения доступа к подсистемам.
SSOT: Единая точка входа во все контракты и сервисы ядра.
"""

from core.application import AppState, CoreApplication, LoadingProgress, get_app
from core.base import (
    BaseGenerator,
    BaseRepository,
    BaseService,
    BaseViewModel,
    DependencyInjectableMixin,
    ExceptionHandlingMixin,
    LoggableMixin,
)
from core.contracts import (
    # DTOs
    BaseDTO,
    ClientDTO,
    # DI Container
    CoreContainer,
    IClientRepository,
    # Repository Protocols
    IOrderRepository,
    OrderDTO,
    kernel,
)
from core.events import Event, EventBus, EventType, get_event_bus
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
from core.module_loader import initialize_modules, shutdown_modules
from core.module_registry import (
    ModuleBase,
    ModuleInfo,
    ModuleRegistry,
    get_module_registry,
)

__version__ = "24.0"
__author__ = "ServiceUP Team"

__all__ = [
    # Application
    "AppState",
    # Exceptions
    "BaseAppError",
    # Base Classes (New Architecture)
    "BaseDTO",
    "BaseGenerator",
    "BaseRepository",
    "BaseService",
    "BaseViewModel",
    "BluetoothCallError",
    "BluetoothConnectionError",
    "BluetoothError",
    "BusinessRuleViolation",
    # Contracts & Ports (Clean Architecture)
    "ClientDTO",
    "ConfigurationError",
    "CoreApplication",
    "CoreContainer",
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
    "IClientRepository",
    "IOrderRepository",
    "InfrastructureError",
    "LoadingProgress",
    "LoggableMixin",
    # Module System (v24.0)
    "ModuleBase",
    "ModuleInfo",
    "ModuleRegistry",
    "NotFoundError",
    "NotificationError",
    "OrderDTO",
    "PDFGenerationError",
    "PermissionError",
    "ServiceError",
    "ValidationError",
    # Functions
    "get_app",
    "get_event_bus",
    "get_logger",
    "get_module_registry",
    "initialize_modules",
    "kernel",
    "setup_logging",
    "shutdown_modules",
]
