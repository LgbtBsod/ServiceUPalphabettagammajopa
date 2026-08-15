"""Core DI Module.

Система внедрения зависимостей (Dependency Injection).
"""

from core.di.container import (
    CircularDependencyError,
    DIContainer,
    DIScope,
    ResolutionError,
    ServiceDescriptor,
    ServiceLifetime,
    ServiceNotFoundError,
    auto_wire,
    get_container,
    inject,
    reset_container,
)

__all__ = [
    "CircularDependencyError",
    "DIContainer",
    "DIScope",
    "ResolutionError",
    "ServiceDescriptor",
    "ServiceLifetime",
    "ServiceNotFoundError",
    "auto_wire",
    "get_container",
    "inject",
    "reset_container",
]
