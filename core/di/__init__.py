"""
Core DI Module.

Система внедрения зависимостей (Dependency Injection).
"""

from core.di.container import (
    DIContainer,
    DIScope,
    ServiceLifetime,
    ServiceDescriptor,
    ResolutionError,
    CircularDependencyError,
    ServiceNotFoundError,
    get_container,
    reset_container,
    inject,
    auto_wire,
)

__all__ = [
    "DIContainer",
    "DIScope",
    "ServiceLifetime",
    "ServiceDescriptor",
    "ResolutionError",
    "CircularDependencyError",
    "ServiceNotFoundError",
    "get_container",
    "reset_container",
    "inject",
    "auto_wire",
]
