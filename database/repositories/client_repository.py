#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Репозиторий для работы с клиентами на SQLAlchemy ORM.

Использует SQLAlchemy ORM API вместо raw SQL запросов.
Соблюдает принципы SOLID, DRY и Clean Code.
"""

from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import select, func

from .base import BaseRepository
from ..repositories.sqlite_connection import SQLAlchemyConnection
from ..sqlalchemy_models import Client


class ClientRepository(BaseRepository[Dict[str, Any]]):
    """
    Репозиторий для управления клиентами.
    
    Все SQL запросы инкапсулированы в этом классе.
    Использует SQLAlchemy ORM для типобезопасности и защиты от SQL инъекций.
    """
    
    def __init__(self, connection: SQLAlchemyConnection):
        """
        Инициализация репозитория.
        
        Args:
            connection: Подключение к базе данных через SQLAlchemy.
        """
        self._connection = connection
    
    def _get_session(self) -> Session:
        """Получение текущей сессии."""
        return self._connection.get_session()
    
    def get(self, id: int) -> Optional[Dict[str, Any]]:
        """Получение клиента по ID."""
        session = self._get_session()
        client = session.get(Client, id)
        return client.to_dict() if client else None
    
    def get_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """Получение клиента по телефону."""
        session = self._get_session()
        stmt = select(Client).where(Client.phone == phone)
        client = session.scalar(stmt)
        return client.to_dict() if client else None
    
    def get_all(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Получение всех клиентов с фильтрацией."""
        session = self._get_session()
        stmt = select(Client)
        
        if filters:
            conditions = []
            for field, value in filters.items():
                if value is not None and hasattr(Client, field):
                    conditions.append(getattr(Client, field) == value)
            if conditions:
                stmt = stmt.where(*conditions)
        
        stmt = stmt.order_by(Client.name)
        clients = session.scalars(stmt).all()
        return [client.to_dict() for client in clients]
    
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Создание нового клиента."""
        session = self._get_session()
        
        client = Client(
            name=data.get('name') or data.get('full_name', ''),
            phone=data.get('phone', ''),
            status=data.get('status', 'Новый')
        )
        
        session.add(client)
        session.flush()  # Получаем ID
        
        created_client = session.get(Client, client.id)
        return created_client.to_dict() if created_client else {}
    
    def update(self, id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Обновление клиента."""
        session = self._get_session()
        client = session.get(Client, id)
        
        if not client:
            return None
        
        client.update_from_dict(data)
        session.flush()
        
        updated_client = session.get(Client, id)
        return updated_client.to_dict() if updated_client else None
    
    def delete(self, id: int) -> bool:
        """Удаление клиента."""
        session = self._get_session()
        client = session.get(Client, id)
        
        if not client:
            return False
        
        session.delete(client)
        session.flush()
        return True
    
    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Подсчет клиентов."""
        session = self._get_session()
        stmt = select(func.count()).select_from(Client)
        
        if filters:
            conditions = []
            for field, value in filters.items():
                if value is not None and hasattr(Client, field):
                    conditions.append(getattr(Client, field) == value)
            if conditions:
                stmt = stmt.where(*conditions)
        
        result = session.scalar(stmt)
        return result or 0
    
    def exists(self, id: int) -> bool:
        """Проверка существования клиента."""
        session = self._get_session()
        client = session.get(Client, id)
        return client is not None
    
    def search(self, query_str: str) -> List[Dict[str, Any]]:
        """Поиск клиентов по имени или телефону."""
        session = self._get_session()
        search_pattern = f"%{query_str}%"
        
        stmt = select(Client).where(
            (Client.name.like(search_pattern)) | 
            (Client.phone.like(search_pattern))
        ).order_by(Client.name)
        
        clients = session.scalars(stmt).all()
        return [client.to_dict() for client in clients]
    
    def update_stats(
        self,
        client_id: int,
        total_orders: int,
        completed_orders: int,
        total_spent: float,
        last_order_date: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Обновление статистики клиента.
        
        Args:
            client_id: ID клиента.
            total_orders: Общее количество заказов.
            completed_orders: Количество завершенных заказов.
            total_spent: Общая сумма потраченных средств.
            last_order_date: Дата последнего заказа.
            
        Returns:
            Обновленные данные клиента.
        """
        session = self._get_session()
        client = session.get(Client, client_id)
        
        if not client:
            return None
        
        client.update_stats(
            total_orders=total_orders,
            completed_orders=completed_orders,
            total_spent=total_spent,
            last_order_date=last_order_date
        )
        
        session.flush()
        updated_client = session.get(Client, client_id)
        return updated_client.to_dict() if updated_client else None
