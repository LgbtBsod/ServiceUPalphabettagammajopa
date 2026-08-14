"""
Core Package Initialization
Экспорт основных компонентов ядра приложения.
Реализует паттерн Facade для упрощения доступа к подсистемам.
"""
from core.application import CoreApplication, AppState, LoadingProgress, get_app
from core.events import EventBus, Event, EventType, get_event_bus

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
]
