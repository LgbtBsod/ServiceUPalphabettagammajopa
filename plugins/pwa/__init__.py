"""PWA Plugin - Progressive Web App server functionality.

This plugin provides web interface capabilities:
- REST API endpoints
- Static file serving
- WebSocket support for real-time updates
- Authentication and authorization

Principles:
- SRP: Only web server logic
- DIP: Depends on abstractions
- Don't Reinvent: Uses existing web frameworks
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.base import BaseService
from core.plugin_system import IPlugin, PluginMetadata, get_plugin_manager

# =============================================================================
# DOMAIN ENTITIES
# =============================================================================


@dataclass
class ApiEndpoint:
    """API endpoint definition."""

    path: str
    method: str  # GET, POST, PUT, DELETE
    handler: Callable
    description: str
    requires_auth: bool = True
    rate_limit: int = 100  # Requests per minute


@dataclass
class WebSocketConnection:
    """WebSocket connection info."""

    connection_id: str
    client_ip: str
    connected_at: datetime
    channels: list[str] = None

    def __post_init__(self):
        if self.channels is None:
            self.channels = []


# =============================================================================
# COMMANDS
# =============================================================================


@dataclass
class RegisterEndpointCommand:
    """Command to register an API endpoint."""

    path: str
    method: str
    handler: Callable
    description: str
    requires_auth: bool = True


@dataclass
class BroadcastMessageCommand:
    """Command to broadcast message to WebSocket clients."""

    channel: str
    message: dict[str, Any]
    exclude_connection_ids: list[str] = None


@dataclass
class StartServerCommand:
    """Command to start the PWA server."""

    host: str = "0.0.0.0"
    port: int = 8080
    ssl_cert: str | None = None
    ssl_key: str | None = None


@dataclass
class StopServerCommand:
    """Command to stop the PWA server."""

    graceful: bool = True  # Wait for active connections


# =============================================================================
# QUERIES
# =============================================================================


@dataclass
class GetEndpointsQuery:
    """Query to get registered endpoints."""

    method: str | None = None
    requires_auth: bool | None = None


@dataclass
class GetConnectionsQuery:
    """Query to get active WebSocket connections."""

    channel: str | None = None


@dataclass
class GetServerStatusQuery:
    """Query to get server status."""


# =============================================================================
# INTERFACES
# =============================================================================


class IWebServer:
    """Interface for web server implementation."""

    def start(self, host: str, port: int) -> bool:
        """Start the web server."""

    def stop(self, graceful: bool = True) -> None:
        """Stop the web server."""

    def register_route(self, path: str, method: str, handler: Callable) -> None:
        """Register a route handler."""

    def serve_static(self, directory: str, url_prefix: str = "/static") -> None:
        """Serve static files from directory."""

    def is_running(self) -> bool:
        """Check if server is running."""


class IWebSocketManager:
    """Interface for WebSocket connection management."""

    def broadcast(self, channel: str, message: dict[str, Any]) -> int:
        """Broadcast message to all clients in channel. Returns count of recipients."""

    def send_to_client(self, connection_id: str, message: dict[str, Any]) -> bool:
        """Send message to specific client."""

    def subscribe(self, connection_id: str, channel: str) -> bool:
        """Subscribe client to channel."""

    def unsubscribe(self, connection_id: str, channel: str) -> bool:
        """Unsubscribe client from channel."""

    def get_connections(self, channel: str | None = None) -> list[WebSocketConnection]:
        """Get active connections, optionally filtered by channel."""

    def disconnect(self, connection_id: str) -> bool:
        """Disconnect a client."""


class IApiRepository:
    """Interface for API metadata repository."""

    def get_endpoints(self, method: str | None = None) -> list[ApiEndpoint]:
        """Get registered endpoints."""

    def register_endpoint(self, endpoint: ApiEndpoint) -> bool:
        """Register an endpoint."""

    def unregister_endpoint(self, path: str, method: str) -> bool:
        """Unregister an endpoint."""


# =============================================================================
# SERVICES
# =============================================================================


class PwaService(BaseService):
    """PWA application service.

    Handles:
    - Server lifecycle
    - Endpoint registration
    - WebSocket management
    - API documentation
    """

    def __init__(
        self,
        web_server: IWebServer,
        websocket_manager: IWebSocketManager,
        api_repository: IApiRepository,
    ):
        self._web_server = web_server
        self._ws_manager = websocket_manager
        self._api_repo = api_repository

    def start_server(self, command: StartServerCommand) -> bool:
        """Start the PWA server."""
        try:
            self.logger.info(f"Starting PWA server on {command.host}:{command.port}")

            success = self.safe_execute(
                self._web_server.start, command.host, command.port, default=False
            )

            if success:
                self.logger.info("PWA server started successfully")
            else:
                self.logger.error("Failed to start PWA server")

            return success

        except Exception as e:
            self.logger.exception(f"Error starting PWA server: {e}")
            return False

    def stop_server(self, command: StopServerCommand) -> bool:
        """Stop the PWA server."""
        try:
            self.logger.info(f"Stopping PWA server (graceful={command.graceful})")

            self.safe_execute(self._web_server.stop, command.graceful, default=None)

            self.logger.info("PWA server stopped")
            return True

        except Exception as e:
            self.logger.exception(f"Error stopping PWA server: {e}")
            return False

    def register_endpoint(self, command: RegisterEndpointCommand) -> bool:
        """Register an API endpoint."""
        try:
            endpoint = ApiEndpoint(
                path=command.path,
                method=command.method,
                handler=command.handler,
                description=command.description,
                requires_auth=command.requires_auth,
            )

            # Register with web server
            self._web_server.register_route(
                command.path, command.method, command.handler
            )

            # Store metadata
            if self._api_repo.register_endpoint(endpoint):
                self.logger.info(
                    f"Endpoint registered: {command.method} {command.path}"
                )
                return True

            return False

        except Exception as e:
            self.logger.exception(f"Error registering endpoint: {e}")
            return False

    def broadcast(self, command: BroadcastMessageCommand) -> int:
        """Broadcast message to WebSocket clients."""
        try:
            return self.safe_execute(
                self._ws_manager.broadcast, command.channel, command.message, default=0
            )
        except Exception as e:
            self.logger.exception(f"Error broadcasting message: {e}")
            return 0

    def get_endpoints(self, query: GetEndpointsQuery) -> list[ApiEndpoint]:
        """Get registered endpoints."""
        return self.safe_execute(self._api_repo.get_endpoints, query.method, default=[])

    def get_connections(self, query: GetConnectionsQuery) -> list[WebSocketConnection]:
        """Get active WebSocket connections."""
        return self.safe_execute(
            self._ws_manager.get_connections, query.channel, default=[]
        )

    def get_server_status(self, query: GetServerStatusQuery) -> dict[str, Any]:
        """Get server status."""
        return {
            "running": self._web_server.is_running(),
            "host": getattr(self, "_host", "unknown"),
            "port": getattr(self, "_port", 0),
            "active_connections": len(self._ws_manager.get_connections()),
            "endpoints_count": len(self._api_repo.get_endpoints()),
        }


# =============================================================================
# PLUGIN IMPLEMENTATION
# =============================================================================


class PwaPlugin(IPlugin):
    """PWA feature plugin."""

    def __init__(self):
        self._service: PwaService | None = None
        self._web_server: IWebServer | None = None
        self._ws_manager: IWebSocketManager | None = None
        self._api_repo: IApiRepository | None = None

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="pwa",
            version="1.0.0",
            description="Progressive Web App server",
            author="ServiceUp Team",
            dependencies=["orders", "clients"],  # Needs business data
            min_core_version="24.0",
            standalone=False,
        )

    def initialize(self) -> bool:
        """Initialize PWA plugin."""
        try:
            self.logger.info("Initializing PWA Plugin")

            # TODO: Get dependencies from DI container
            # self._web_server = self._app.get_service(IWebServer)
            # self._ws_manager = self._app.get_service(IWebSocketManager)
            # self._api_repo = self._app.get_repository(IApiRepository)
            # self._service = PwaService(self._web_server, self._ws_manager, self._api_repo)

            self.logger.info("PWA Plugin initialized successfully")
            return True

        except Exception as e:
            self.logger.exception(f"Failed to initialize PWA Plugin: {e}")
            return False

    def shutdown(self) -> None:
        """Cleanup PWA plugin resources."""
        self.logger.info("Shutting down PWA Plugin")

        # Stop server if running
        if self._service:
            self._service.stop_server(StopServerCommand(graceful=True))

        self._service = None
        self._web_server = None
        self._ws_manager = None
        self._api_repo = None

    def get_api(self) -> PwaService | None:
        """Return PWA service API."""
        return self._service

    def configure(self, config: dict) -> None:
        """Configure PWA plugin."""
        self.logger.info(f"Configuring PWA Plugin: {config}")


# =============================================================================
# PLUGIN REGISTRATION
# =============================================================================


def register_plugin():
    """Register the PWA plugin with the plugin manager."""
    plugin_manager = get_plugin_manager()
    plugin = PwaPlugin()
    plugin_manager.register(plugin)
    return plugin


__all__ = [
    # Entities
    "ApiEndpoint",
    "BroadcastMessageCommand",
    "GetConnectionsQuery",
    # Queries
    "GetEndpointsQuery",
    "GetServerStatusQuery",
    "IApiRepository",
    # Interfaces
    "IWebServer",
    "IWebSocketManager",
    # Plugin
    "PwaPlugin",
    # Service
    "PwaService",
    # Enums
    # Commands
    "RegisterEndpointCommand",
    "StartServerCommand",
    "StopServerCommand",
    "WebSocketConnection",
    "register_plugin",
]
