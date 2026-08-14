"""
Core Package Initialization
Экспорт основных компонентов ядра приложения.
Реализует паттерн Facade для упрощения доступа к подсистемам.
SSOT: Единая точка входа во все контракты и сервисы ядра.
"""
from core.application import CoreApplication, AppState, LoadingProgress, get_app
from core.events import EventBus, Event, EventType, get_event_bus
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

__version__ = "21.0"
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
    
    # Contracts & Ports (Clean Architecture)
    'BaseDTO',
    'OrderDTO',
    'ClientDTO',
    'IOrderRepository',
    'IClientRepository',
    'CoreContainer',
    'kernel',
]
