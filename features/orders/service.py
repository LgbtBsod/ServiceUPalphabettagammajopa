"""
Сервис заказов - бизнес-логика.
Application слой - оркестрирует работу репозитория.

Принципы:
- SRP: Отвечает только за бизнес-логику заказов
- DIP: Зависит от абстракции IOrderRepository, а не реализации
- DRY: Не дублирует логику CRUD, использует репозиторий
"""
from typing import Optional, Any
from datetime import datetime

from core.contracts import IOrderRepository, OrderDTO, kernel
from shared.kernel import OrderStatus, Priority


class OrderService:
    """
    Сервис для управления заказами.
    
    Содержит бизнес-логику:
    - Валидация статусов
    - Расчет статистики
    - Генерация номеров заказов
    - Бизнес-правила переходов статусов
    
    Доступ к данным осуществляется через ядро (kernel).
    """
    
    def __init__(self, repository: Optional[IOrderRepository] = None):
        """
        Инициализация сервиса.
        
        Args:
            repository: Репозиторий для работы с данными.
                       Если не указан, берется из kernel.
        """
        self._repository = repository
    
    @property
    def repository(self) -> IOrderRepository:
        """Получение репозитория из DI или переданного."""
        if self._repository is not None:
            return self._repository
        return kernel.orders
    
    def get_order(self, order_id: int) -> Optional[OrderDTO]:
        """Получить заказ по ID."""
        return self.repository.get_by_id(order_id)
    
    def get_all_orders(self, filters: Optional[dict[str, Any]] = None) -> list[OrderDTO]:
        """Получить все заказы с фильтрацией."""
        return self.repository.get_all(filters)
    
    def create_order(
        self,
        client_id: Optional[int] = None,
        complaint: str = "",
        priority: str = Priority.NORMAL,
        diagnosis: Optional[str] = None,
    ) -> OrderDTO:
        """
        Создать новый заказ.
        
        Args:
            client_id: ID клиента (опционально).
            complaint: Жалоба клиента.
            priority: Приоритет заказа.
            diagnosis: Первоначальная диагностика.
            
        Returns:
            DTO созданного заказа.
        """
        # Генерация номера заказа
        order_number = self._generate_order_number()
        
        dto = OrderDTO(
            order_number=order_number,
            client_id=client_id,
            status=OrderStatus.DIAGNOSTICS,
            priority=priority,
            total_amount=0.0,
            metadata={
                'complaint': complaint,
                'diagnosis': diagnosis or '',
                'work_items': [],
                'parts_used': [],
            }
        )
        
        return self.repository.save(dto)
    
    def update_order_status(self, order_id: int, new_status: str) -> OrderDTO:
        """
        Обновить статус заказа с проверкой бизнес-правил.
        
        Args:
            order_id: ID заказа.
            new_status: Новый статус.
            
        Returns:
            DTO обновленного заказа.
            
        Raises:
            ValueError: Если переход статуса недопустим.
        """
        order = self.get_order(order_id)
        
        if order is None:
            raise ValueError(f"Order {order_id} not found")
        
        # Проверка допустимости перехода
        if not self._is_valid_status_transition(order.status, new_status):
            raise ValueError(
                f"Invalid status transition from {order.status} to {new_status}"
            )
        
        order.status = new_status
        
        # Автоматическая установка даты завершения
        if new_status in [OrderStatus.ISSUED, OrderStatus.READY]:
            order.metadata['completed_at'] = datetime.now().isoformat()
        
        return self.repository.save(order)
    
    def add_work_to_order(
        self,
        order_id: int,
        work_name: str,
        price: float,
        quantity: int = 1,
        description: str = "",
    ) -> OrderDTO:
        """
        Добавить работу к заказу.
        
        Args:
            order_id: ID заказа.
            work_name: Название работы.
            price: Стоимость за единицу.
            quantity: Количество.
            description: Описание работы.
            
        Returns:
            DTO обновленного заказа.
        """
        order = self.get_order(order_id)
        
        if order is None:
            raise ValueError(f"Order {order_id} not found")
        
        work_items = order.metadata.get('work_items', [])
        work_items.append({
            'name': work_name,
            'price': price,
            'quantity': quantity,
            'description': description,
            'total': price * quantity,
        })
        
        order.metadata['work_items'] = work_items
        order.total_amount = self._calculate_total(order)
        
        return self.repository.save(order)
    
    def add_part_to_order(
        self,
        order_id: int,
        part_name: str,
        price: float,
        quantity: int = 1,
        sku: str = "",
    ) -> OrderDTO:
        """
        Добавить запчасть к заказу.
        
        Args:
            order_id: ID заказа.
            part_name: Название запчасти.
            price: Стоимость за единицу.
            quantity: Количество.
            sku: Артикул запчасти.
            
        Returns:
            DTO обновленного заказа.
        """
        order = self.get_order(order_id)
        
        if order is None:
            raise ValueError(f"Order {order_id} not found")
        
        parts = order.metadata.get('parts_used', [])
        parts.append({
            'name': part_name,
            'price': price,
            'quantity': quantity,
            'sku': sku,
            'total': price * quantity,
        })
        
        order.metadata['parts_used'] = parts
        order.total_amount = self._calculate_total(order)
        
        return self.repository.save(order)
    
    def delete_order(self, order_id: int) -> bool:
        """
        Удалить заказ.
        
        Args:
            order_id: ID заказа для удаления.
            
        Returns:
            True если удалено, False если не найдено.
        """
        order = self.get_order(order_id)
        
        if order is None:
            return False
        
        # Нельзя удалить заказ в работе
        if order.status not in [OrderStatus.CANCELLED, OrderStatus.REFUSED]:
            # Можно удалить только если нет работ и запчастей
            has_works = len(order.metadata.get('work_items', [])) > 0
            has_parts = len(order.metadata.get('parts_used', [])) > 0
            
            if has_works or has_parts:
                raise ValueError(
                    "Cannot delete order with works or parts. "
                    "Cancel the order first."
                )
        
        return self.repository.delete(order_id)
    
    def get_statistics(self) -> dict[str, Any]:
        """
        Получить статистику по заказам.
        
        Returns:
            Словарь со статистикой.
        """
        all_orders = self.repository.get_all()
        
        stats = {
            'total_count': len(all_orders),
            'by_status': {},
            'by_priority': {},
            'total_revenue': 0.0,
            'average_order_value': 0.0,
        }
        
        for order in all_orders:
            # По статусам
            status = order.status
            stats['by_status'][status] = stats['by_status'].get(status, 0) + 1
            
            # По приоритетам
            priority = order.priority
            stats['by_priority'][priority] = stats['by_priority'].get(priority, 0) + 1
            
            # Выручка
            stats['total_revenue'] += order.total_amount
        
        if stats['total_count'] > 0:
            stats['average_order_value'] = stats['total_revenue'] / stats['total_count']
        
        return stats
    
    def _generate_order_number(self) -> str:
        """Генерация уникального номера заказа."""
        now = datetime.now()
        return f"ORD-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}"
    
    def _calculate_total(self, order: OrderDTO) -> float:
        """Расчет общей стоимости заказа."""
        total = 0.0
        
        # Работы
        for work in order.metadata.get('work_items', []):
            total += work.get('total', work.get('price', 0) * work.get('quantity', 1))
        
        # Запчасти
        for part in order.metadata.get('parts_used', []):
            total += part.get('total', part.get('price', 0) * part.get('quantity', 1))
        
        return total
    
    def _is_valid_status_transition(self, from_status: str, to_status: str) -> bool:
        """
        Проверка допустимости перехода между статусами.
        
        Бизнес-правила:
        - Из "Отменен" или "Выдан" нельзя перейти ни в какой другой статус
        - Из "Диагностика" можно перейти в любой статус кроме "Выдан"
        """
        # Конечные статусы
        terminal_statuses = [OrderStatus.ISSUED, OrderStatus.CANCELLED, OrderStatus.REFUSED]
        
        if from_status in terminal_statuses:
            return from_status == to_status
        
        # Разрешенные переходы
        allowed_transitions = {
            OrderStatus.DIAGNOSTICS: [
                OrderStatus.WAITING_PARTS,
                OrderStatus.IN_PROGRESS,
                OrderStatus.CANCELLED,
                OrderStatus.REFUSED,
            ],
            OrderStatus.WAITING_PARTS: [
                OrderStatus.IN_PROGRESS,
                OrderStatus.CANCELLED,
                OrderStatus.REFUSED,
            ],
            OrderStatus.IN_PROGRESS: [
                OrderStatus.READY,
                OrderStatus.CANCELLED,
                OrderStatus.REFUSED,
            ],
            OrderStatus.READY: [
                OrderStatus.ISSUED,
                OrderStatus.CANCELLED,
            ],
        }
        
        return to_status in allowed_transitions.get(from_status, [])
