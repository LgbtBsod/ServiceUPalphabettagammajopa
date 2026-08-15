"""Plugin Architecture for ServiceUp - Modular, Extensible, Decoupled.

This module defines the plugin system that allows features to be developed
as independent modules that can be enabled/disabled without affecting the core.

Principles:
- SRP: Each plugin has single responsibility
- OCP: Open/Closed - extend without modifying core
- DIP: Depend on abstractions (IPlugin interface)
- COLID: Command-Query separation in plugin API
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.base import LoggableMixin


class PluginState(Enum):
    """Plugin lifecycle states."""

    UNLOADED = "unloaded"
    LOADING = "loading"
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"
    UNLOADING = "unloading"


@dataclass
class PluginMetadata:
    """Metadata describing a plugin."""

    name: str
    version: str
    description: str
    author: str
    dependencies: list[str] = field(default_factory=list)
    min_core_version: str = "24.0"
    standalone: bool = False  # Can work independently


class IPlugin(ABC, LoggableMixin):
    """Interface all plugins must implement.

    This ensures consistent lifecycle management across all plugins.
    """

    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""

    @abstractmethod
    def initialize(self) -> bool:
        """Initialize plugin resources.

        Returns:
            True if initialization successful, False otherwise

        Note: Should not throw exceptions - catch and return False
        """

    @abstractmethod
    def shutdown(self) -> None:
        """Cleanup plugin resources.

        Must be idempotent (safe to call multiple times).
        """

    @abstractmethod
    def get_api(self) -> Any | None:
        """Return plugin's public API.

        This is how other plugins/modules interact with this plugin.
        Return None if plugin doesn't expose an API.
        """

    def configure(self, config: dict) -> None:
        """Configure plugin with external settings.

        Default implementation does nothing. Override if needed.
        """

    def health_check(self) -> bool:
        """Check if plugin is healthy and operational.

        Default implementation returns True for active plugins.
        Override in subclasses for more sophisticated health checks.
        """
        # Active state means healthy by default
        return hasattr(self, "_state") and self._state == PluginState.ACTIVE


class PluginError(Exception):
    """Base exception for plugin-related errors."""


class PluginNotFoundError(PluginError):
    """Raised when requested plugin is not found."""


class PluginDependencyError(PluginError):
    """Raised when plugin dependency cannot be satisfied."""


class PluginManager(LoggableMixin):
    """Central registry and lifecycle manager for all plugins.

    Features:
    - Plugin discovery and registration
    - Dependency resolution
    - Lifecycle management (load/enable/disable/unload)
    - Health monitoring
    """

    def __init__(self):
        self._plugins: dict[str, IPlugin] = {}
        self._states: dict[str, PluginState] = {}
        self._apis: dict[str, Any] = {}

    def register(self, plugin: IPlugin) -> None:
        """Register a plugin instance."""
        name = plugin.metadata.name

        if name in self._plugins:
            self.logger.warning(f"Plugin {name} already registered, replacing")

        self._plugins[name] = plugin
        self._states[name] = PluginState.UNLOADED
        # Set state reference on plugin for health_check
        plugin._state = PluginState.UNLOADED
        self.logger.info(f"Plugin '{name}' v{plugin.metadata.version} registered")

    def unregister(self, plugin_name: str) -> None:
        """Unregister a plugin (must be unloaded first)."""
        if plugin_name not in self._plugins:
            raise PluginNotFoundError(f"Plugin '{plugin_name}' not found")

        if self._states[plugin_name] != PluginState.UNLOADED:
            raise PluginError(
                f"Plugin '{plugin_name}' must be unloaded before unregistering"
            )

        del self._plugins[plugin_name]
        del self._states[plugin_name]
        if plugin_name in self._apis:
            del self._apis[plugin_name]

        self.logger.info(f"Plugin '{plugin_name}' unregistered")

    def load(self, plugin_name: str) -> bool:
        """Load a plugin (call initialize)."""
        if plugin_name not in self._plugins:
            raise PluginNotFoundError(f"Plugin '{plugin_name}' not found")

        plugin = self._plugins[plugin_name]

        # Check dependencies
        for dep in plugin.metadata.dependencies:
            if dep not in self._plugins or self._states.get(dep) != PluginState.ACTIVE:
                self.logger.error(
                    f"Plugin '{plugin_name}' requires '{dep}' which is not active"
                )
                self._states[plugin_name] = PluginState.ERROR
                raise PluginDependencyError(f"Missing dependency: {dep}")

        self._states[plugin_name] = PluginState.LOADING

        try:
            success = plugin.initialize()
            if success:
                self._states[plugin_name] = PluginState.ACTIVE
                plugin._state = PluginState.ACTIVE  # Update plugin's internal state
                self._apis[plugin_name] = plugin.get_api()
                self.logger.info(f"Plugin '{plugin_name}' loaded successfully")
                return True
            else:
                self._states[plugin_name] = PluginState.ERROR
                plugin._state = PluginState.ERROR
                self.logger.error(f"Plugin '{plugin_name}' initialization failed")
                return False
        except Exception as e:
            self._states[plugin_name] = PluginState.ERROR
            plugin._state = PluginState.ERROR
            self.logger.exception(f"Plugin '{plugin_name}' initialization error: {e}")
            return False

    def unload(self, plugin_name: str) -> None:
        """Unload a plugin (call shutdown)."""
        if plugin_name not in self._plugins:
            raise PluginNotFoundError(f"Plugin '{plugin_name}' not found")

        plugin = self._plugins[plugin_name]
        self._states[plugin_name] = PluginState.UNLOADING

        try:
            plugin.shutdown()
            self._states[plugin_name] = PluginState.UNLOADED
            if plugin_name in self._apis:
                del self._apis[plugin_name]
            self.logger.info(f"Plugin '{plugin_name}' unloaded successfully")
        except Exception as e:
            self._states[plugin_name] = PluginState.ERROR
            self.logger.exception(f"Plugin '{plugin_name}' shutdown error: {e}")
            raise

    def enable(self, plugin_name: str) -> bool:
        """Enable a loaded plugin (mark as active)."""
        if plugin_name not in self._plugins:
            raise PluginNotFoundError(f"Plugin '{plugin_name}' not found")

        if self._states[plugin_name] == PluginState.ACTIVE:
            return True

        if self._states[plugin_name] != PluginState.UNLOADED:
            self.logger.warning(
                f"Plugin '{plugin_name}' is in {self._states[plugin_name]} state"
            )
            return False

        return self.load(plugin_name)

    def disable(self, plugin_name: str) -> None:
        """Disable a plugin (unload and mark as disabled)."""
        if plugin_name not in self._plugins:
            raise PluginNotFoundError(f"Plugin '{plugin_name}' not found")

        if self._states[plugin_name] == PluginState.DISABLED:
            return

        self.unload(plugin_name)
        self._states[plugin_name] = PluginState.DISABLED
        self.logger.info(f"Plugin '{plugin_name}' disabled")

    def get_plugin(self, plugin_name: str) -> IPlugin:
        """Get plugin instance by name."""
        if plugin_name not in self._plugins:
            raise PluginNotFoundError(f"Plugin '{plugin_name}' not found")
        return self._plugins[plugin_name]

    def get_api(self, plugin_name: str) -> Any | None:
        """Get plugin's public API by name."""
        return self._apis.get(plugin_name)

    def get_state(self, plugin_name: str) -> PluginState:
        """Get plugin's current state."""
        if plugin_name not in self._plugins:
            raise PluginNotFoundError(f"Plugin '{plugin_name}' not found")
        return self._states[plugin_name]

    def list_plugins(self) -> list[dict]:
        """List all registered plugins with their states."""
        return [
            {
                "name": name,
                "version": plugin.metadata.version,
                "description": plugin.metadata.description,
                "state": self._states[name].value,
                "healthy": plugin.health_check(),
            }
            for name, plugin in self._plugins.items()
        ]

    def health_check_all(self) -> dict[str, bool]:
        """Check health of all active plugins."""
        return {
            name: plugin.health_check()
            for name, plugin in self._plugins.items()
            if self._states[name] == PluginState.ACTIVE
        }


# Global plugin manager instance
_plugin_manager: PluginManager | None = None


def get_plugin_manager() -> PluginManager:
    """Get global plugin manager instance (singleton)."""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager


__all__ = [
    # Interface
    "IPlugin",
    "PluginDependencyError",
    # Exceptions
    "PluginError",
    # Manager
    "PluginManager",
    # Data classes
    "PluginMetadata",
    "PluginNotFoundError",
    # Enums
    "PluginState",
    "get_plugin_manager",
]
