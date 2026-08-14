"""
Интеграция Модульной Системы v24.0 в Core Application

Теперь приложение автоматически загружает все модули из папки modules/
при старте и корректно останавливает их при закрытии.
"""

from pathlib import Path
from typing import Optional
from .module_registry import ModuleRegistry, get_module_registry


def initialize_modules(app_container=None, modules_path: Optional[Path] = None):
    """
    Инициализация системы модулей.
    
    Вызывается при старте приложения после создания DI контейнера.
    
    Args:
        app_container: DI контейнер приложения
        modules_path: Путь к папке с модулями (по умолчанию ./modules)
        
    Returns:
        ModuleRegistry: Экземпляр реестра модулей
    """
    registry = get_module_registry(modules_path)
    
    # Обнаружение модулей
    discovered = registry.discover_modules()
    
    if not discovered:
        return registry
        
    # Инициализация модулей с инъекцией зависимостей
    registry.initialize_all(app_container)
    
    # Запуск модулей
    registry.start_all()
    
    return registry


def shutdown_modules():
    """
    Корректная остановка всех модулей.
    
    Вызывается при закрытии приложения.
    """
    registry = get_module_registry()
    registry.stop_all()


# Экспорт для удобного импорта
__all__ = ["initialize_modules", "shutdown_modules", "get_module_registry"]
