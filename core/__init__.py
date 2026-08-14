"""
Core Package Initialization
Экспорт основных компонентов ядра приложения.
Реализует паттерн Facade для упрощения доступа к подсистемам.
SSOT: Единая точка входа во все контракты и сервисы ядра.
"""
from core.application import CoreApplication, AppState, LoadingProgress, get_app
from core.events import EventBus, Event, EventType, get_event_bus
from core.base import (
    BaseService,
    BaseRepository,
    BaseViewModel,
    BaseGenerator,
    LoggableMixin,
    ExceptionHandlingMixin,
    DependencyInjectableMixin,
)
from core.logging import (
    # Logger
    get_logger,
    setup_logging,
    LogContext,
    # Exceptions
    BaseAppError,
    AppException,  # Legacy alias
    CoreError,
    ConfigurationError,
    AuthenticationError,
    PermissionError,
    DomainException,
    NotFoundError,
    EntityNotFoundException,  # Legacy alias
    ValidationError,
    BusinessRuleViolation,
    ServiceError,
    NotificationError,
    AnalyticsError,
    ApplicationException,  # Legacy alias
    ServiceUnavailableError,  # Legacy alias
    CommandExecutionError,  # Legacy alias
    QueryExecutionError,  # Legacy alias
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
    BluetoothError,
    BluetoothConnectionError,
    BluetoothCallError,
    MobileConnectionError,  # Legacy alias
    WebSocketError,  # Legacy alias
    PresentationException,  # Legacy alias
    UIComponentError,  # Legacy alias
    DataBindingError,  # Legacy alias
    DIContainerError,  # Legacy alias
    ServiceNotRegisteredError,  # Legacy alias
)
from core.contracts import (
    # DTOs
    BaseDTO,
    OrderDTO,
    ClientDTO,
    # Repository Protocols
    IOrderRepository,
    IClientRepository,
    # DI Container
    CoreContainer,
    kernel,
)
from core.module_registry import ModuleRegistry, ModuleBase, ModuleInfo, get_module_registry
from core.module_loader import initialize_modules, shutdown_modules

__version__ = "24.0"
__author__ = "ServiceUP Team"

__all__ = [
    # Application
    'CoreApplication',
    'AppState',
    'LoadingProgress',
    'get_app',
    
    # Events
    'EventBus',
    'Event',
    'EventType',
    'get_event_bus',
    
    # Base Classes (New Architecture)
    'BaseService',
    'BaseRepository',
    'BaseViewModel',
    'BaseGenerator',
    'LoggableMixin',
    'ExceptionHandlingMixin',
    'DependencyInjectableMixin',
    
    # Module System (v24.0)
    'ModuleRegistry',
    'ModuleBase',
    'ModuleInfo',
    'get_module_registry',
    'initialize_modules',
    'shutdown_modules',
    
    # Exceptions
    'AppException',
    'DomainException',
    'EntityNotFoundException',
    'ValidationError',
    'BusinessRuleViolation',
    'ApplicationException',
    'ServiceUnavailableError',
    'CommandExecutionError',
    'QueryExecutionError',
    'InfrastructureException',
    'DatabaseError',
    'RepositoryError',
    'ExternalServiceError',
    'ConfigurationError',
    'FileOperationError',
    'PDFGenerationError',
    'TemplateNotFoundError',
    'QRCodeGenerationError',
    'MobileConnectionError',
    'WebSocketError',
    'PresentationException',
    'UIComponentError',
    'DataBindingError',
    'DIContainerError',
    'ServiceNotRegisteredError',
    
    # Contracts & Ports (Clean Architecture)
    'BaseDTO',
    'OrderDTO',
    'ClientDTO',
    'IOrderRepository',
    'IClientRepository',
    'CoreContainer',
    'kernel',
]
