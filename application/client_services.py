"""
Client Application Services - Use Cases для управления клиентами.

Следует принципам:
- SRP: каждый метод решает одну задачу
- DRY: переиспользование общей логики
- Multi-threading: асинхронные операции
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Any, Optional, Protocol
from concurrent.futures import ThreadPoolExecutor

from shared.kernel import Repository, UnitOfWork

logger = logging.getLogger(__name__)


class UnitOfWorkFactory(Protocol):
    """Протокол фабрики Unit of Work."""
    def __call__(self) -> UnitOfWork: ...


@dataclass(slots=True)
class ClientSearchResult:
    """Результат поиска клиентов."""
    clients: List[Dict[str, Any]]
    total_count: int
    page: int = 1
    page_size: int = 20


@dataclass(slots=True)
class ClientStats:
    """Статистика по клиенту."""
    total_orders: int
    total_spent: float
    last_order_date: Optional[str]
    average_order_value: float


class ClientAppService:
    """
    Сервис приложения для управления клиентами.
    
    Координирует работу доменных сервисов и репозиториев.
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        max_workers: int = 2,
    ):
        self._uow_factory = uow_factory
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def get_client_by_id(self, client_id: int) -> Optional[Dict[str, Any]]:
        """Получение клиента по ID (Query)."""
        with self._uow_factory() as uow:
            return uow.clients.get_by_id(client_id)

    def search_clients(
        self,
        query: Optional[str] = None,
        phone: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ClientSearchResult:
        """
        Поиск клиентов с фильтрацией и пагинацией (Query).
        """
        with self._uow_factory() as uow:
            clients, total = uow.clients.search(
                query=query,
                phone=phone,
                offset=(page - 1) * page_size,
                limit=page_size,
            )
            
            return ClientSearchResult(
                clients=clients,
                total_count=total,
                page=page,
                page_size=page_size,
            )

    def get_client_stats(self, client_id: int) -> Optional[ClientStats]:
        """
        Получение статистики по клиенту (Query).
        
        Включает:
        - Количество заказов
        - Общая сумма покупок
        - Дата последнего заказа
        - Средний чек
        """
        with self._uow_factory() as uow:
            stats_data = uow.clients.get_stats(client_id)
            
            if not stats_data:
                return None
            
            return ClientStats(
                total_orders=stats_data.get('total_orders', 0),
                total_spent=float(stats_data.get('total_spent', 0)),
                last_order_date=stats_data.get('last_order_date'),
                average_order_value=float(stats_data.get('average_order_value', 0)),
            )

    def create_or_update_client(self, client_data: Dict[str, Any]) -> int:
        """
        Создание или обновление клиента (Command).
        
        Если клиент с таким телефоном существует - обновляет данные.
        Иначе создает нового.
        
        Args:
            client_data: Данные клиента (phone, full_name, email, etc.)
            
        Returns:
            ID клиента.
        """
        phone = client_data.get('phone')
        if not phone:
            raise ValueError("Телефон клиента обязателен")
        
        with self._uow_factory() as uow:
            # Поиск существующего клиента
            existing = uow.clients.find_by_phone(phone)
            
            if existing:
                # Обновление
                client_data['id'] = existing['id']
                client_data['updated_at'] = datetime.now().isoformat()
                uow.clients.update(client_data)
                logger.info(f"Клиент {existing['id']} обновлен")
                return existing['id']
            else:
                # Создание
                client_data['created_at'] = datetime.now().isoformat()
                client_data['updated_at'] = client_data['created_at']
                created = uow.clients.add(client_data)
                logger.info(f"Клиент создан: {created.get('id')}")
                return created.get('id')

    def merge_clients(self, source_id: int, target_id: int) -> bool:
        """
        Объединение двух записей клиентов (Command).
        
        Переносит все заказы от source к target, затем удаляет source.
        
        Args:
            source_id: ID клиента, которого нужно удалить.
            target_id: ID клиента, к которому присоединить.
            
        Returns:
            True если успешно.
        """
        try:
            with self._uow_factory() as uow:
                # Перенос заказов
                uow.clients.transfer_orders(source_id, target_id)
                
                # Удаление дубликата
                uow.clients.delete(source_id)
                
                logger.info(f"Клиенты объединены: {source_id} -> {target_id}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка объединения клиентов: {e}", exc_info=True)
            return False

    def shutdown(self) -> None:
        """Корректное завершение работы сервиса."""
        self._executor.shutdown(wait=True)
