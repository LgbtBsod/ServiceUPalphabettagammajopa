"""Dashboard Metrics Data Transfer Object"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any

@dataclass(slots=True)
class DashboardMetrics:
    """
    Aggregated metrics for dashboard display.
    
    Attributes:
        total_orders_today: Number of orders created today
        total_revenue_today: Revenue generated today
        orders_in_progress: Currently active orders
        ready_orders: Orders ready for pickup
        revenue_by_status: Revenue breakdown by order status
        top_clients: List of top clients by revenue
        period_start: Start of the reporting period
        period_end: End of the reporting period
    """
    total_orders_today: int = 0
    total_revenue_today: float = 0.0
    orders_in_progress: int = 0
    ready_orders: int = 0
    revenue_by_status: Dict[str, float] = field(default_factory=dict)
    top_clients: List[Dict[str, Any]] = field(default_factory=list)
    period_start: datetime = field(default_factory=datetime.now)
    period_end: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'total_orders_today': self.total_orders_today,
            'total_revenue_today': self.total_revenue_today,
            'orders_in_progress': self.orders_in_progress,
            'ready_orders': self.ready_orders,
            'revenue_by_status': self.revenue_by_status,
            'top_clients': self.top_clients,
            'period_start': self.period_start.isoformat(),
            'period_end': self.period_end.isoformat(),
        }
