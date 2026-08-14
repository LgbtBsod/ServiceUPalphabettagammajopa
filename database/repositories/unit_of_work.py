#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit of Work паттерн для управления транзакциями.

Реализует паттерн Unit of Work для координации изменений между
несколькими репозиториями в рамках одной транзакции.
Соблюдает принципы SOLID и Clean Code.
"""

from typing import Optional, Any
from contextlib import contextmanager

from .base import DatabaseConnection
from .device_repository import DeviceRepository
from .client_repository import ClientRepository


class UnitOfWork:
    """
    Unit of Work для координации транзакций между репозиториями.
    
    Пример использования:
        with UnitOfWork(connection) as uow:
            device = uow.devices.create(device_data)
            client = uow.clients.create(client_data)
            # Оба изменения будут закоммичены или откачены вместе
    """
    
    def __init__(self, connection: DatabaseConnection):
        """
        Инициализация Unit of Work.
        
        Args:
            connection: Подключение к базе данных.
        """
        self._connection = connection
        self._devices: Optional[DeviceRepository] = None
        self._clients: Optional[ClientRepository] = None
    
    @property
    def devices(self) -> DeviceRepository:
        """Ленивая инициализация репозитория устройств."""
        if self._devices is None:
            self._devices = DeviceRepository(self._connection)
        return self._devices
    
    @property
    def clients(self) -> ClientRepository:
        """Ленивая инициализация репозитория клиентов."""
        if self._clients is None:
            self._clients = ClientRepository(self._connection)
        return self._clients
    
    def __enter__(self) -> 'UnitOfWork':
        """Начало транзакции."""
        self._connection.begin_transaction()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Завершение транзакции.
        
        При возникновении исключения происходит откат, иначе фиксация.
        """
        if exc_type is not None:
            self._connection.rollback()
        else:
            self._connection.commit()
    
    @contextmanager
    def transaction(self):
        """
        Контекстный менеджер для явного управления транзакцией.
        
        Пример использования:
            with uow.transaction():
                uow.devices.create(data1)
                uow.clients.create(data2)
        """
        try:
            yield self
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
    
    def commit(self) -> None:
        """Фиксация всех изменений."""
        self._connection.commit()
    
    def rollback(self) -> None:
        """Откат всех изменений."""
        self._connection.rollback()
