#!/usr/bin/env python3

"""Unit of Work паттерн для управления транзакциями на SQLAlchemy.

Реализует паттерн Unit of Work для координации изменений между
несколькими репозиториями в рамках одной транзакции.
Соблюдает принципы SOLID и Clean Code.
"""

from contextlib import contextmanager
from typing import Self

from .client_repository import ClientRepository
from .device_repository import DeviceRepository
from .sqlite_connection import SQLAlchemyConnection


class UnitOfWork:
    """Unit of Work для координации транзакций между репозиториями.

    Пример использования:
        with UnitOfWork(connection) as uow:
            device = uow.devices.create(device_data)
            client = uow.clients.create(client_data)
            # Оба изменения будут закоммичены или откачены вместе
    """

    def __init__(self, connection: SQLAlchemyConnection):
        """Инициализация Unit of Work.

        Args:
            connection: Подключение к базе данных через SQLAlchemy.
        """
        self._connection = connection
        self._devices: DeviceRepository | None = None
        self._clients: ClientRepository | None = None

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

    def __enter__(self) -> Self:
        """Начало транзакции."""
        self._connection.connect()  # Убеждаемся что сессия создана
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Завершение транзакции.

        При возникновении исключения происходит откат, иначе фиксация.
        """
        session = self._connection.session
        if session:
            if exc_type is not None:
                session.rollback()
            else:
                try:
                    session.commit()
                except Exception:
                    session.rollback()
                    raise

    @contextmanager
    def transaction(self):
        """Контекстный менеджер для явного управления транзакцией.

        Пример использования:
            with uow.transaction():
                uow.devices.create(data1)
                uow.clients.create(data2)
        """
        session = self._connection.get_session()
        try:
            yield self
            session.commit()
        except Exception:
            session.rollback()
            raise

    def commit(self) -> None:
        """Фиксация всех изменений."""
        session = self._connection.session
        if session:
            session.commit()

    def rollback(self) -> None:
        """Откат всех изменений."""
        session = self._connection.session
        if session:
            session.rollback()
