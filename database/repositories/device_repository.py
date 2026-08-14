#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Репозиторий для работы с устройствами/заказами на SQLAlchemy ORM.

Использует SQLAlchemy ORM API вместо raw SQL запросов.
Соблюдает принципы SOLID, особенно Single Responsibility Principle (SRP) и DRY.
"""

import json
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import select, func

from .base import BaseRepository
from ..repositories.sqlite_connection import SQLAlchemyConnection
from ..sqlalchemy_models import Device as DeviceModel
from ..models import Device


class DeviceRepository(BaseRepository[Device]):
    """
    Репозиторий для управления устройствами/заказами.
    
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
    
    def get(self, id: int) -> Optional[Device]:
        """
        Получение устройства по ID.
        
        Args:
            id: Идентификатор устройства.
            
        Returns:
            Объект Device или None если не найдено.
        """
        session = self._get_session()
        device_model = session.get(DeviceModel, id)
        
        if not device_model:
            return None
        
        # Преобразуем ORM модель в нашу Domain модель
        data = device_model.to_dict()
        data['work_items'] = data.pop('work_items_json', '[]')
        return Device.from_dict(data)
    
    def get_by_order_number(self, order_number: str) -> Optional[Device]:
        """
        Получение устройства по номеру заказа.
        
        Args:
            order_number: Номер заказа.
            
        Returns:
            Объект Device или None если не найдено.
        """
        session = self._get_session()
        stmt = select(DeviceModel).where(DeviceModel.order_number == order_number)
        device_model = session.scalar(stmt)
        
        if not device_model:
            return None
        
        data = device_model.to_dict()
        data['work_items'] = data.pop('work_items_json', '[]')
        return Device.from_dict(data)
    
    def get_all(self, filters: Optional[Dict[str, Any]] = None) -> List[Device]:
        """
        Получение всех устройств с фильтрацией.
        
        Args:
            filters: Словарь фильтров (status, client_name, phone, etc.).
            
        Returns:
            Список объектов Device.
        """
        session = self._get_session()
        stmt = select(DeviceModel)
        
        if filters:
            conditions = []
            for field, value in filters.items():
                if value is not None and hasattr(DeviceModel, field):
                    conditions.append(getattr(DeviceModel, field) == value)
            if conditions:
                stmt = stmt.where(*conditions)
        
        stmt = stmt.order_by(DeviceModel.id.desc())
        devices = session.scalars(stmt).all()
        
        result = []
        for device_model in devices:
            data = device_model.to_dict()
            data['work_items'] = data.pop('work_items_json', '[]')
            result.append(Device.from_dict(data))
        
        return result
    
    def create(self, data: Dict[str, Any]) -> Device:
        """
        Создание нового устройства/заказа.
        
        Args:
            data: Данные устройства.
            
        Returns:
            Созданный объект Device.
        """
        session = self._get_session()
        
        # Подготовка work_items как JSON
        work_items = data.get('work_items', '[]')
        if isinstance(work_items, list):
            work_items = json.dumps(work_items, ensure_ascii=False)
        
        # Получаем client_id из данных или создаем нового клиента
        client_id = data.get('client_id')
        if not client_id:
            # Если client_id не указан, пытаемся найти клиента по телефону
            phone = data.get('phone')
            if phone:
                from .client_repository import ClientRepository
                client_repo = ClientRepository(self._connection)
                client = client_repo.get_by_phone(phone)
                if client:
                    client_id = client['id']
        
        device_model = DeviceModel(
            order_number=data.get('order_number', ''),
            receipt_date=data.get('receipt_date', ''),
            completion_date=data.get('completion_date') or None,
            ready_date=data.get('ready_date') or None,
            device_type=data.get('device_type', ''),
            brand=data.get('brand', ''),
            model=data.get('model', ''),
            serial_number=data.get('serial_number') or None,
            defect=data.get('defect', ''),
            appearance=data.get('appearance', ''),
            completeness=data.get('completeness', ''),
            work_items=work_items,
            client_name=data.get('client_name') or None,
            client_status=data.get('client_status', 'Новый'),
            phone=data.get('phone') or None,
            total_price=float(data.get('total_price', 0) or 0),
            prepayment=float(data.get('prepayment', 0) or 0),
            status=data.get('status', 'Диагностика'),
            priority=data.get('priority', 'Обычный'),
            engineer=data.get('engineer') or None,
            warranty=data.get('warranty') or None,
            notes=data.get('notes') or None,
            photos=data.get('photos') or None
        )
        
        session.add(device_model)
        session.flush()
        
        created_model = session.get(DeviceModel, device_model.id)
        if not created_model:
            raise RuntimeError("Не удалось получить созданное устройство")
        
        result_data = created_model.to_dict()
        return Device.from_dict(result_data)
    
    def update(self, id: int, data: Dict[str, Any]) -> Optional[Device]:
        """
        Обновление устройства.
        
        Args:
            id: Идентификатор устройства.
            data: Новые данные.
            
        Returns:
            Обновленный объект Device или None если не найдено.
        """
        session = self._get_session()
        device_model = session.get(DeviceModel, id)
        
        if not device_model:
            return None
        
        # Обработка work_items - модель уже использует work_items напрямую
        if 'work_items' in data:
            work_items = data['work_items']
            if isinstance(work_items, list):
                data['work_items'] = json.dumps(work_items, ensure_ascii=False)
        
        # Преобразование числовых полей
        if 'total_price' in data:
            data['total_price'] = float(data['total_price'] or 0)
        if 'prepayment' in data:
            data['prepayment'] = float(data['prepayment'] or 0)
        
        device_model.update_from_dict(data)
        session.flush()
        
        updated_model = session.get(DeviceModel, id)
        if not updated_model:
            return None
        
        result_data = updated_model.to_dict()
        return Device.from_dict(result_data)
    
    def delete(self, id: int) -> bool:
        """
        Удаление устройства.
        
        Args:
            id: Идентификатор устройства.
            
        Returns:
            True если удалено, False если не найдено.
        """
        session = self._get_session()
        device_model = session.get(DeviceModel, id)
        
        if not device_model:
            return False
        
        session.delete(device_model)
        session.flush()
        return True
    
    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Подсчет устройств с фильтрацией.
        
        Args:
            filters: Словарь фильтров.
            
        Returns:
            Количество записей.
        """
        session = self._get_session()
        stmt = select(func.count()).select_from(DeviceModel)
        
        if filters:
            conditions = []
            for field, value in filters.items():
                if value is not None and hasattr(DeviceModel, field):
                    conditions.append(getattr(DeviceModel, field) == value)
            if conditions:
                stmt = stmt.where(*conditions)
        
        result = session.scalar(stmt)
        return result or 0
    
    def exists(self, id: int) -> bool:
        """
        Проверка существования устройства.
        
        Args:
            id: Идентификатор устройства.
            
        Returns:
            True если существует, False иначе.
        """
        session = self._get_session()
        device_model = session.get(DeviceModel, id)
        return device_model is not None
    
    def search(self, query_str: str) -> List[Device]:
        """
        Поиск устройств по строке запроса.
        
        Ищет в полях: order_number, client_name, phone, brand, model.
        
        Args:
            query_str: Строка поиска.
            
        Returns:
            Список найденных устройств.
        """
        session = self._get_session()
        search_pattern = f"%{query_str}%"
        
        # Поиск по всем доступным полям включая client_name и phone
        stmt = select(DeviceModel).where(
            (DeviceModel.order_number.like(search_pattern)) |
            (DeviceModel.client_name.like(search_pattern)) |
            (DeviceModel.phone.like(search_pattern)) |
            (DeviceModel.brand.like(search_pattern)) |
            (DeviceModel.model.like(search_pattern))
        ).order_by(DeviceModel.id.desc())
        
        devices = session.scalars(stmt).all()
        
        result = []
        for device_model in devices:
            data = device_model.to_dict()
            data['work_items'] = data.pop('work_items_json', '[]')
            result.append(Device.from_dict(data))
        
        return result
    
    def get_work_items(self, device_id: int) -> List[Dict[str, Any]]:
        """
        Получение списка работ для устройства.
        
        Args:
            device_id: Идентификатор устройства.
            
        Returns:
            Список работ в формате словарей.
        """
        session = self._get_session()
        device_model = session.get(DeviceModel, device_id)
        
        if not device_model:
            return []
        
        return device_model.get_work_items()
    
    def update_work_items(self, device_id: int, work_items: List[Dict[str, Any]]) -> Optional[Device]:
        """
        Обновление списка работ для устройства.
        
        Args:
            device_id: Идентификатор устройства.
            work_items: Список работ.
            
        Returns:
            Обновленный объект Device.
        """
        return self.update(device_id, {'work_items': work_items})
