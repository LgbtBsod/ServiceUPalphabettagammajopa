"""Domain services - бизнес-сервисы предметной области.

Сервисы содержат бизнес-логику, которая не принадлежит конкретной сущности.
"""

from .client_service import ClientService
from .notification_service import NotificationService
from .order_service import OrderService

__all__ = [
    "ClientService",
    "NotificationService",
    "OrderService",
]
