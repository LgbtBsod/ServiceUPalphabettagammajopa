"""
Domain services - бизнес-сервисы предметной области.

Сервисы содержат бизнес-логику, которая не принадлежит конкретной сущности.
"""

from .order_service import OrderService
from .client_service import ClientService
from .notification_service import NotificationService

__all__ = [
    'OrderService',
    'ClientService',
    'NotificationService',
]
