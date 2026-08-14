"""
Feature: Orders Module
Модуль управления заказами.

Архитектура:
- models.py: SQLAlchemy модели (Infrastructure)
- repository.py: Реализация репозитория (Infrastructure) 
- service.py: Бизнес-логика (Application)
- api.py: REST API контроллер (Presentation - Web)
- gui.py: GUI компоненты (Presentation - Desktop)

Принципы:
- SRP: Каждый класс отвечает за одну задачу
- DIP: Сервис зависит от абстракции IOrderRepository
- DRY: Логика не дублируется между слоями
- SSOT: Данные запрашиваются через ядро (kernel)
"""
from features.orders.service import OrderService
from features.orders.repository import SQLAlchemyOrderRepository
from features.orders.models import RepairOrder

__all__ = [
    'OrderService',
    'SQLAlchemyOrderRepository',
    'RepairOrder',
]