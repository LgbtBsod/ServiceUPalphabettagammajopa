#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Репозиторий для работы с клиентами.

Реализует паттерн Repository для отделения бизнес-логики от доступа к данным.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

from .base import BaseRepository
from ..db_config import DatabaseConfig
from .sqlite_connection import SQLiteConnection


class ClientRepository(BaseRepository[Dict[str, Any]]):
    """
    Репозиторий для управления клиентами.
    
    Все SQL запросы инкапсулированы в этом классе.
    """
    
    def __init__(self, connection: SQLiteConnection):
        """
        Инициализация репозитория.
        
        Args:
            connection: Подключение к базе данных.
        """
        self._conn = connection
    
    def get(self, id: int) -> Optional[Dict[str, Any]]:
        """Получение клиента по ID."""
        cursor = self._conn.execute(
            "SELECT * FROM clients WHERE id = ?",
            (id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """Получение клиента по телефону."""
        cursor = self._conn.execute(
            "SELECT * FROM clients WHERE phone = ?",
            (phone,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_all(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Получение всех клиентов с фильтрацией."""
        query = "SELECT * FROM clients"
        params = []
        conditions = []
        
        if filters:
            for field, value in filters.items():
                if value is not None:
                    conditions.append(f"{field} = ?")
                    params.append(value)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY name"
        
        cursor = self._conn.execute(query, tuple(params))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Создание нового клиента."""
        columns = ['name', 'phone', 'status']
        placeholders = ', '.join(['?' for _ in columns])
        column_names = ', '.join(columns)
        
        values = [
            data.get('name') or data.get('full_name', ''),
            data.get('phone', ''),
            data.get('status', 'Новый')
        ]
        
        cursor = self._conn.execute(
            f"INSERT INTO clients ({column_names}) VALUES ({placeholders})",
            tuple(values)
        )
        self._conn.commit()
        
        return self.get(cursor.lastrowid) or {}
    
    def update(self, id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Обновление клиента."""
        if not self.exists(id):
            return None
        
        set_clauses = []
        params = []
        
        for field, value in data.items():
            set_clauses.append(f"{field} = ?")
            params.append(value)
        
        params.append(id)
        
        query = f"UPDATE clients SET {', '.join(set_clauses)} WHERE id = ?"
        self._conn.execute(query, tuple(params))
        self._conn.commit()
        
        return self.get(id)
    
    def delete(self, id: int) -> bool:
        """Удаление клиента."""
        if not self.exists(id):
            return False
        
        self._conn.execute("DELETE FROM clients WHERE id = ?", (id,))
        self._conn.commit()
        return True
    
    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Подсчет клиентов."""
        query = "SELECT COUNT(*) FROM clients"
        params = []
        conditions = []
        
        if filters:
            for field, value in filters.items():
                if value is not None:
                    conditions.append(f"{field} = ?")
                    params.append(value)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        cursor = self._conn.execute(query, tuple(params))
        result = cursor.fetchone()
        return result[0] if result else 0
    
    def exists(self, id: int) -> bool:
        """Проверка существования клиента."""
        cursor = self._conn.execute(
            "SELECT 1 FROM clients WHERE id = ?",
            (id,)
        )
        return cursor.fetchone() is not None
    
    def search(self, query_str: str) -> List[Dict[str, Any]]:
        """Поиск клиентов по имени или телефону."""
        search_pattern = f"%{query_str}%"
        cursor = self._conn.execute(
            """
            SELECT * FROM clients 
            WHERE name LIKE ? OR phone LIKE ?
            ORDER BY name
            """,
            (search_pattern, search_pattern)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    def update_stats(self, client_id: int, total_orders: int, 
                     completed_orders: int, total_spent: float,
                     last_order_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
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
        data = {
            'total_orders': total_orders,
            'completed_orders': completed_orders,
            'total_spent': total_spent
        }
        
        if last_order_date:
            data['last_order_date'] = last_order_date
        
        return self.update(client_id, data)
