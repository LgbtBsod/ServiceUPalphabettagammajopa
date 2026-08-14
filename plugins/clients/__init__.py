"""
Clients Plugin - Client management functionality.

This plugin encapsulates all client-related functionality:
- Client CRUD operations
- Client search and filtering
- Contact information management
- Client history tracking

Principles:
- SRP: Only client-related logic
- DIP: Depends on abstractions
- SSOT: Single source for client entities
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

from core.plugin_system import IPlugin, PluginMetadata, get_plugin_manager
from core.base import BaseService, BaseRepository
from shared.utils import normalize_phone, validate_email


# =============================================================================
# DOMAIN ENTITIES (SSOT)
# =============================================================================

@dataclass
class ClientEntity:
    """Client aggregate root."""
    id: int
    full_name: str
    phone: str
    email: Optional[str] = None
    address: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    notes: str = ""
    is_active: bool = True
    orders_count: int = 0
    total_spent: str = "0.00"
    
    def __post_init__(self):
        """Validate and normalize client data."""
        self.phone = normalize_phone(self.phone) or self.phone
        if self.email and not validate_email(self.email):
            self.email = None


# =============================================================================
# COMMANDS
# =============================================================================

@dataclass
class CreateClientCommand:
    """Command to create a new client."""
    full_name: str
    phone: str
    email: Optional[str] = None
    address: Optional[str] = None
    notes: str = ""


@dataclass
class UpdateClientCommand:
    """Command to update client information."""
    client_id: int
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


@dataclass
class DeleteClientCommand:
    """Command to delete a client."""
    client_id: int
    hard_delete: bool = False  # Soft delete by default


# =============================================================================
# QUERIES
# =============================================================================

@dataclass
class GetClientByIdQuery:
    """Query to get client by ID."""
    client_id: int


@dataclass
class GetClientByPhoneQuery:
    """Query to get client by phone."""
    phone: str


@dataclass
class SearchClientsQuery:
    """Query to search clients."""
    query: str  # Name, phone, or email
    limit: int = 50
    active_only: bool = True


@dataclass
class GetClientsWithOrdersQuery:
    """Query to get clients with order history."""
    min_orders: int = 1
    limit: int = 100


# =============================================================================
# REPOSITORIES
# =============================================================================

class IClientRepository(BaseRepository[ClientEntity]):
    """Interface for client repository."""
    
    def get_by_id(self, client_id: int) -> Optional[ClientEntity]:
        """Get client by ID."""
        pass
    
    def get_by_phone(self, phone: str) -> Optional[ClientEntity]:
        """Get client by phone number."""
        pass
    
    def get_by_email(self, email: str) -> Optional[ClientEntity]:
        """Get client by email."""
        pass
    
    def get_all(self, limit: int = 100, active_only: bool = True) -> List[ClientEntity]:
        """Get all clients."""
        pass
    
    def save(self, client: ClientEntity) -> bool:
        """Save client (insert or update)."""
        pass
    
    def delete(self, client_id: int, hard: bool = False) -> bool:
        """Delete client (soft or hard)."""
        pass
    
    def search(self, query: str, limit: int = 50, active_only: bool = True) -> List[ClientEntity]:
        """Search clients by name, phone, or email."""
        pass
    
    def get_with_order_history(self, min_orders: int = 1, limit: int = 100) -> List[ClientEntity]:
        """Get clients with order history."""
        pass


# =============================================================================
# SERVICES
# =============================================================================

class ClientService(BaseService):
    """
    Client application service.
    
    Handles:
    - Client creation and updates
    - Client search
    - Validation and normalization
    """
    
    def __init__(self, client_repository: IClientRepository):
        self._client_repo = client_repository
    
    def create_client(self, command: CreateClientCommand) -> Optional[ClientEntity]:
        """Create a new client with validation."""
        try:
            self.logger.info(f"Creating client: {command.full_name}")
            
            # Validate phone
            normalized_phone = normalize_phone(command.phone)
            if not normalized_phone:
                self.logger.warning(f"Invalid phone: {command.phone}")
                return None
            
            # Check if client already exists by phone
            existing = self._client_repo.get_by_phone(normalized_phone)
            if existing:
                self.logger.info(f"Client already exists with phone {normalized_phone}: ID {existing.id}")
                return existing
            
            # Validate email if provided
            email = None
            if command.email:
                if validate_email(command.email):
                    email = command.email
                else:
                    self.logger.warning(f"Invalid email: {command.email}")
            
            # Create client entity
            client = ClientEntity(
                id=0,  # Will be assigned by repository
                full_name=command.full_name.strip(),
                phone=normalized_phone,
                email=email,
                address=command.address,
                notes=command.notes
            )
            
            # Save client
            if self._client_repo.save(client):
                self.logger.info(f"Client created successfully: {client.full_name}")
                return client
            
            return None
            
        except Exception as e:
            self.logger.exception(f"Error creating client: {e}")
            return None
    
    def update_client(self, command: UpdateClientCommand) -> bool:
        """Update client information."""
        try:
            client = self._client_repo.get_by_id(command.client_id)
            if not client:
                self.logger.warning(f"Client {command.client_id} not found")
                return False
            
            # Update fields if provided
            if command.full_name is not None:
                client.full_name = command.full_name.strip()
            
            if command.phone is not None:
                normalized = normalize_phone(command.phone)
                if normalized:
                    client.phone = normalized
                else:
                    self.logger.warning(f"Invalid phone: {command.phone}")
                    return False
            
            if command.email is not None:
                if command.email == "":
                    client.email = None
                elif validate_email(command.email):
                    client.email = command.email
                else:
                    self.logger.warning(f"Invalid email: {command.email}")
                    return False
            
            if command.address is not None:
                client.address = command.address
            
            if command.notes is not None:
                client.notes = command.notes
            
            if command.is_active is not None:
                client.is_active = command.is_active
            
            client.updated_at = datetime.now()
            
            return self._client_repo.save(client)
            
        except Exception as e:
            self.logger.exception(f"Error updating client: {e}")
            return False
    
    def delete_client(self, command: DeleteClientCommand) -> bool:
        """Delete client (soft by default)."""
        try:
            return self.safe_execute(
                self._client_repo.delete,
                command.client_id,
                command.hard_delete,
                default=False
            )
        except Exception as e:
            self.logger.exception(f"Error deleting client: {e}")
            return False
    
    def get_client(self, query: GetClientByIdQuery) -> Optional[ClientEntity]:
        """Get client by ID."""
        return self.safe_execute(
            self._client_repo.get_by_id,
            query.client_id,
            default=None
        )
    
    def find_by_phone(self, query: GetClientByPhoneQuery) -> Optional[ClientEntity]:
        """Find client by phone."""
        normalized = normalize_phone(query.phone)
        if not normalized:
            return None
        
        return self.safe_execute(
            self._client_repo.get_by_phone,
            normalized,
            default=None
        )
    
    def search_clients(self, query: SearchClientsQuery) -> List[ClientEntity]:
        """Search clients."""
        return self.safe_execute(
            self._client_repo.search,
            query.query,
            query.limit,
            query.active_only,
            default=[]
        )
    
    def get_vip_clients(self, limit: int = 100) -> List[ClientEntity]:
        """Get clients with order history."""
        return self.safe_execute(
            self._client_repo.get_with_order_history,
            min_orders=1,
            limit=limit,
            default=[]
        )


# =============================================================================
# PLUGIN IMPLEMENTATION
# =============================================================================

class ClientsPlugin(IPlugin):
    """Clients feature plugin."""
    
    def __init__(self):
        self._service: Optional[ClientService] = None
        self._repository: Optional[IClientRepository] = None
    
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="clients",
            version="1.0.0",
            description="Client management system",
            author="ServiceUp Team",
            dependencies=[],  # No dependencies - base plugin
            min_core_version="24.0",
            standalone=True
        )
    
    def initialize(self) -> bool:
        """Initialize clients plugin."""
        try:
            self.logger.info("Initializing Clients Plugin")
            
            # TODO: Get repository from DI container
            # self._repository = self._app.get_repository(IClientRepository)
            # self._service = ClientService(self._repository)
            
            self.logger.info("Clients Plugin initialized successfully")
            return True
            
        except Exception as e:
            self.logger.exception(f"Failed to initialize Clients Plugin: {e}")
            return False
    
    def shutdown(self) -> None:
        """Cleanup clients plugin resources."""
        self.logger.info("Shutting down Clients Plugin")
        self._service = None
        self._repository = None
    
    def get_api(self) -> Optional[ClientService]:
        """Return clients service API."""
        return self._service
    
    def configure(self, config: dict) -> None:
        """Configure clients plugin."""
        self.logger.info(f"Configuring Clients Plugin: {config}")


# =============================================================================
# PLUGIN REGISTRATION
# =============================================================================

def register_plugin():
    """Register the Clients plugin with the plugin manager."""
    plugin_manager = get_plugin_manager()
    plugin = ClientsPlugin()
    plugin_manager.register(plugin)
    return plugin


__all__ = [
    # Entities
    'ClientEntity',
    # Commands
    'CreateClientCommand',
    'UpdateClientCommand',
    'DeleteClientCommand',
    # Queries
    'GetClientByIdQuery',
    'GetClientByPhoneQuery',
    'SearchClientsQuery',
    'GetClientsWithOrdersQuery',
    # Repository interface
    'IClientRepository',
    # Service
    'ClientService',
    # Plugin
    'ClientsPlugin',
    'register_plugin',
]
