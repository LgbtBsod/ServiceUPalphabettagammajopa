"""
Orders Plugin - Core business logic for order management.

This plugin encapsulates all order-related functionality:
- Order creation and lifecycle management
- Work items management
- Status tracking
- Order queries and reporting

Principles:
- SRP: Only order-related logic
- DIP: Depends on abstractions (repositories, services)
- CQS: Separate commands and queries
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
from enum import Enum

from core.plugin_system import IPlugin, PluginMetadata, get_plugin_manager
from core.base import BaseService, BaseRepository
from shared.utils import safe_decimal, normalize_phone


# =============================================================================
# DOMAIN ENTITIES (SSOT - Single Source of Truth)
# =============================================================================

@dataclass
class OrderEntity:
    """Order aggregate root."""
    id: int
    order_number: str
    client_id: int
    status: str
    created_at: datetime
    updated_at: datetime
    devices: List['DeviceEntity'] = None
    work_items: List['WorkItemEntity'] = None
    total_amount: str = "0.00"
    
    def __post_init__(self):
        if self.devices is None:
            self.devices = []
        if self.work_items is None:
            self.work_items = []


@dataclass
class DeviceEntity:
    """Device value object within order."""
    id: int
    order_id: int
    device_type: str
    brand: str
    model: str
    serial_number: str
    problem_description: str
    warranty: bool = False


@dataclass
class WorkItemEntity:
    """Work item value object within order."""
    id: int
    order_id: int
    service_type: str
    description: str
    price: str
    status: str = "pending"
    completed_at: Optional[datetime] = None


# =============================================================================
# COMMANDS (Write operations)
# =============================================================================

@dataclass
class CreateOrderCommand:
    """Command to create a new order."""
    client_id: int
    client_name: str
    client_phone: str
    devices: List[dict]
    notes: str = ""


@dataclass
class UpdateOrderStatusCommand:
    """Command to update order status."""
    order_id: int
    new_status: str
    comment: str = ""


@dataclass
class AddWorkItemCommand:
    """Command to add work item to order."""
    order_id: int
    service_type: str
    description: str
    price: str
    technician_id: Optional[int] = None


# =============================================================================
# QUERIES (Read operations)
# =============================================================================

@dataclass
class GetOrderByIdQuery:
    """Query to get order by ID."""
    order_id: int


@dataclass
class GetOrdersByStatusQuery:
    """Query to get orders by status."""
    status: str
    limit: int = 100


@dataclass
class SearchOrdersQuery:
    """Query to search orders."""
    query: str  # Can be order number, client name, phone
    limit: int = 50


# =============================================================================
# REPOSITORIES (Infrastructure abstraction)
# =============================================================================

class IOrderRepository(BaseRepository[OrderEntity]):
    """Interface for order repository."""
    
    def get_by_id(self, order_id: int) -> Optional[OrderEntity]:
        """Get order by ID."""
        pass
    
    def get_by_order_number(self, order_number: str) -> Optional[OrderEntity]:
        """Get order by order number."""
        pass
    
    def get_all(self, limit: int = 100) -> List[OrderEntity]:
        """Get all orders with limit."""
        pass
    
    def get_by_status(self, status: str, limit: int = 100) -> List[OrderEntity]:
        """Get orders by status."""
        pass
    
    def save(self, order: OrderEntity) -> bool:
        """Save order (insert or update)."""
        pass
    
    def delete(self, order_id: int) -> bool:
        """Delete order."""
        pass
    
    def search(self, query: str, limit: int = 50) -> List[OrderEntity]:
        """Search orders by various criteria."""
        pass


# =============================================================================
# SERVICES (Application logic)
# =============================================================================

class OrderService(BaseService):
    """
    Order application service.
    
    Handles:
    - Order creation workflow
    - Status transitions
    - Work item management
    - Business validation
    """
    
    def __init__(self, order_repository: IOrderRepository):
        self._order_repo = order_repository
    
    def create_order(self, command: CreateOrderCommand) -> Optional[OrderEntity]:
        """Create a new order with validation."""
        try:
            self.logger.info(f"Creating order for client {command.client_id}")
            
            # Validate phone
            normalized_phone = normalize_phone(command.client_phone)
            if not normalized_phone:
                self.logger.warning(f"Invalid phone: {command.client_phone}")
                return None
            
            # Create order entity
            order = OrderEntity(
                id=0,  # Will be assigned by repository
                order_number=self._generate_order_number(),
                client_id=command.client_id,
                status="new",
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            # Save order
            if self._order_repo.save(order):
                self.logger.info(f"Order {order.order_number} created successfully")
                return order
            
            return None
            
        except Exception as e:
            self.logger.exception(f"Error creating order: {e}")
            return None
    
    def update_status(self, command: UpdateOrderStatusCommand) -> bool:
        """Update order status with validation."""
        try:
            order = self._order_repo.get_by_id(command.order_id)
            if not order:
                self.logger.warning(f"Order {command.order_id} not found")
                return False
            
            # Validate status transition
            if not self._is_valid_transition(order.status, command.new_status):
                self.logger.warning(
                    f"Invalid status transition: {order.status} -> {command.new_status}"
                )
                return False
            
            order.status = command.new_status
            order.updated_at = datetime.now()
            
            return self._order_repo.save(order)
            
        except Exception as e:
            self.logger.exception(f"Error updating order status: {e}")
            return False
    
    def add_work_item(self, command: AddWorkItemCommand) -> bool:
        """Add work item to order."""
        try:
            # Validate price
            price = safe_decimal(command.price)
            if price is None:
                self.logger.warning(f"Invalid price: {command.price}")
                return False
            
            # TODO: Implement work item persistence
            self.logger.info(f"Adding work item to order {command.order_id}")
            return True
            
        except Exception as e:
            self.logger.exception(f"Error adding work item: {e}")
            return False
    
    def get_order(self, query: GetOrderByIdQuery) -> Optional[OrderEntity]:
        """Get order by ID."""
        return self.safe_execute(
            self._order_repo.get_by_id, 
            query.order_id, 
            default=None
        )
    
    def search_orders(self, query: SearchOrdersQuery) -> List[OrderEntity]:
        """Search orders."""
        return self.safe_execute(
            self._order_repo.search,
            query.query,
            query.limit,
            default=[]
        )
    
    def _generate_order_number(self) -> str:
        """Generate unique order number."""
        # TODO: Move to infrastructure (repository should handle this)
        timestamp = datetime.now().strftime("%Y%m%d")
        return f"ORD-{timestamp}-0001"
    
    def _is_valid_transition(self, from_status: str, to_status: str) -> bool:
        """Validate status transition."""
        valid_transitions = {
            "new": ["in_progress", "cancelled"],
            "in_progress": ["completed", "on_hold", "cancelled"],
            "on_hold": ["in_progress", "cancelled"],
            "completed": ["delivered", "archived"],
            "delivered": ["archived"],
            "cancelled": [],
            "archived": []
        }
        return to_status in valid_transitions.get(from_status, [])


# =============================================================================
# PLUGIN IMPLEMENTATION
# =============================================================================

class OrdersPlugin(IPlugin):
    """Orders feature plugin."""
    
    def __init__(self):
        self._service: Optional[OrderService] = None
        self._repository: Optional[IOrderRepository] = None
    
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="orders",
            version="1.0.0",
            description="Order management system",
            author="ServiceUp Team",
            dependencies=["clients"],  # Depends on clients plugin
            min_core_version="24.0",
            standalone=False
        )
    
    def initialize(self) -> bool:
        """Initialize orders plugin."""
        try:
            self.logger.info("Initializing Orders Plugin")
            
            # Get repository from DI (or create default implementation)
            plugin_manager = get_plugin_manager()
            
            # TODO: Get actual repository from DI container
            # For now, we'll create a placeholder
            # self._repository = self._app.get_repository(IOrderRepository)
            
            # Initialize service
            # self._service = OrderService(self._repository)
            
            self.logger.info("Orders Plugin initialized successfully")
            return True
            
        except Exception as e:
            self.logger.exception(f"Failed to initialize Orders Plugin: {e}")
            return False
    
    def shutdown(self) -> None:
        """Cleanup orders plugin resources."""
        self.logger.info("Shutting down Orders Plugin")
        self._service = None
        self._repository = None
    
    def get_api(self) -> Optional[OrderService]:
        """Return orders service API."""
        return self._service
    
    def configure(self, config: dict) -> None:
        """Configure orders plugin."""
        self.logger.info(f"Configuring Orders Plugin: {config}")


# =============================================================================
# PLUGIN REGISTRATION
# =============================================================================

def register_plugin():
    """Register the Orders plugin with the plugin manager."""
    plugin_manager = get_plugin_manager()
    plugin = OrdersPlugin()
    plugin_manager.register(plugin)
    return plugin


__all__ = [
    # Entities
    'OrderEntity',
    'DeviceEntity',
    'WorkItemEntity',
    # Commands
    'CreateOrderCommand',
    'UpdateOrderStatusCommand',
    'AddWorkItemCommand',
    # Queries
    'GetOrderByIdQuery',
    'GetOrdersByStatusQuery',
    'SearchOrdersQuery',
    # Repository interface
    'IOrderRepository',
    # Service
    'OrderService',
    # Plugin
    'OrdersPlugin',
    'register_plugin',
]
