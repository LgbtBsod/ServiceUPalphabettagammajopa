#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Репозиторий для работы с устройствами/заказами.

Реализует паттерн Repository для отделения бизнес-логики от доступа к данным.
Соблюдает принципы SOLID, особенно Single Responsibility Principle (SRP).
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime

from .base import BaseRepository
from ..models import Device
from ..db_config import DatabaseConfig
from .sqlite_connection import SQLiteConnection


class DeviceRepository(BaseRepository[Device]):
    """
    Репозиторий для управления устройствами/заказами.
    
    Все SQL запросы инкапсулированы в этом классе.
    Для смены БД достаточно изменить реализацию подключения.
    """
    
    def __init__(self, connection: SQLiteConnection):
        """
        Инициализация репозитория.
        
        Args:
            connection: Подключение к базе данных.
        """
        self._conn = connection
    
    def get(self, id: int) -> Optional[Device]:
        """
        Получение устройства по ID.
        
        Args:
            id: Идентификатор устройства.
            
        Returns:
            Объект Device или None если не найдено.
        """
        cursor = self._conn.execute(
            "SELECT * FROM devices WHERE id = ?",
            (id,)
        )
        row = cursor.fetchone()
        return Device.from_dict(dict(row)) if row else None
    
    def get_by_order_number(self, order_number: str) -> Optional[Device]:
        """
        Получение устройства по номеру заказа.
        
        Args:
            order_number: Номер заказа.
            
        Returns:
            Объект Device или None если не найдено.
        """
        cursor = self._conn.execute(
            "SELECT * FROM devices WHERE order_number = ?",
            (order_number,)
        )
        row = cursor.fetchone()
        return Device.from_dict(dict(row)) if row else None
    
    def get_all(self, filters: Optional[Dict[str, Any]] = None) -> List[Device]:
        """
        Получение всех устройств с фильтрацией.
        
        Args:
            filters: Словарь фильтров (status, client_name, phone, etc.).
            
        Returns:
            Список объектов Device.
        """
        query = "SELECT * FROM devices"
        params = []
        conditions = []
        
        if filters:
            for field, value in filters.items():
                if value is not None:
                    conditions.append(f"{field} = ?")
                    params.append(value)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY id DESC"
        
        cursor = self._conn.execute(query, tuple(params))
        rows = cursor.fetchall()
        return [Device.from_dict(dict(row)) for row in rows]
    
    def create(self, data: Dict[str, Any]) -> Device:
        """
        Создание нового устройства/заказа.
        
        Args:
            data: Данные устройства.
            
        Returns:
            Созданный объект Device.
        """
        columns = [
            'order_number', 'receipt_date', 'completion_date', 'device_type',
            'brand', 'model', 'serial_number', 'defect', 'appearance',
            'completeness', 'work_items', 'client_name', 'client_status',
            'phone', 'total_price', 'prepayment', 'status', 'priority',
            'engineer', 'warranty', 'notes', 'photos', 'expense'
        ]
        
        placeholders = ', '.join(['?' for _ in columns])
        column_names = ', '.join(columns)
        
        values = [data.get(col, '') for col in columns]
        
        cursor = self._conn.execute(
            f"INSERT INTO devices ({column_names}) VALUES ({placeholders})",
            tuple(values)
        )
        self._conn.commit()
        
        # Получаем созданную запись
        return self.get(cursor.lastrowid)
    
    def update(self, id: int, data: Dict[str, Any]) -> Optional[Device]:
        """
        Обновление устройства.
        
        Args:
            id: Идентификатор устройства.
            data: Новые данные.
            
        Returns:
            Обновленный объект Device или None если не найдено.
        """
        if not self.exists(id):
            return None
        
        set_clauses = []
        params = []
        
        for field, value in data.items():
            set_clauses.append(f"{field} = ?")
            params.append(value)
        
        params.append(id)
        
        query = f"UPDATE devices SET {', '.join(set_clauses)} WHERE id = ?"
        self._conn.execute(query, tuple(params))
        self._conn.commit()
        
        return self.get(id)
    
    def delete(self, id: int) -> bool:
        """
        Удаление устройства.
        
        Args:
            id: Идентификатор устройства.
            
        Returns:
            True если удалено, False если не найдено.
        """
        if not self.exists(id):
            return False
        
        self._conn.execute("DELETE FROM devices WHERE id = ?", (id,))
        self._conn.commit()
        return True
    
    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Подсчет устройств с фильтрацией.
        
        Args:
            filters: Словарь фильтров.
            
        Returns:
            Количество записей.
        """
        query = "SELECT COUNT(*) FROM devices"
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
        """
        Проверка существования устройства.
        
        Args:
            id: Идентификатор устройства.
            
        Returns:
            True если существует, False иначе.
        """
        cursor = self._conn.execute(
            "SELECT 1 FROM devices WHERE id = ?",
            (id,)
        )
        return cursor.fetchone() is not None
    
    def search(self, query_str: str) -> List[Device]:
        """
        Поиск устройств по строке запроса.
        
        Ищет в полях: order_number, client_name, phone, brand, model.
        
        Args:
            query_str: Строка поиска.
            
        Returns:
            Список найденных устройств.
        """
        search_pattern = f"%{query_str}%"
        cursor = self._conn.execute(
            """
            SELECT * FROM devices 
            WHERE order_number LIKE ? 
               OR client_name LIKE ? 
               OR phone LIKE ? 
               OR brand LIKE ? 
               OR model LIKE ?
            ORDER BY id DESC
            """,
            (search_pattern,) * 5
        )
        rows = cursor.fetchall()
        return [Device.from_dict(dict(row)) for row in rows]
    
    def get_work_items(self, device_id: int) -> List[Dict[str, Any]]:
        """
        Получение списка работ для устройства.
        
        Args:
            device_id: Идентификатор устройства.
            
        Returns:
            Список работ в формате словарей.
        """
        device = self.get(device_id)
        if not device or not device.work_items:
            return []
        
        try:
            return json.loads(device.work_items)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def update_work_items(self, device_id: int, work_items: List[Dict[str, Any]]) -> Optional[Device]:
        """
        Обновление списка работ для устройства.
        
        Args:
            device_id: Идентификатор устройства.
            work_items: Список работ.
            
        Returns:
            Обновленный объект Device.
        """
        work_items_json = json.dumps(work_items, ensure_ascii=False)
        return self.update(device_id, {'work_items': work_items_json})
