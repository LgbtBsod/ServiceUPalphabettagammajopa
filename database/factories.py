#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Фабрики для создания объектов базы данных.

Соблюдает принцип Factory Method из GoF паттернов.
Централизует создание подключений, репозиториев и Unit of Work.
"""

from typing import Optional
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from .db_config import DatabaseConfig, get_db_config
from .sqlalchemy_models import create_database_engine, get_session_factory, Base
from .repositories.sqlite_connection import SQLAlchemyConnection
from .repositories.unit_of_work import UnitOfWork


class DatabaseFactory:
    """
    Фабрика для создания компонентов базы данных.
    
    Реализует абстракцию над созданием БД, позволяя легко переключаться
    между различными СУБД без изменения клиентского кода.
    """
    
    def __init__(self, config: Optional[DatabaseConfig] = None):
        """
        Инициализация фабрики.
        
        Args:
            config: Конфигурация БД. Если не указана, используется конфигурация по умолчанию.
        """
        self._config = config or get_db_config()
        self._engine: Optional[Engine] = None
        self._session_factory: Optional[sessionmaker] = None
    
    @property
    def config(self) -> DatabaseConfig:
        """Получение конфигурации БД."""
        return self._config
    
    @property
    def engine(self) -> Engine:
        """
        Получение SQLAlchemy движка (ленивая инициализация).
        
        Returns:
            SQLAlchemy Engine.
        """
        if self._engine is None:
            self._engine = create_database_engine(
                self._config.get_connection_string(),
                echo=self._config.echo
            )
        return self._engine
    
    @property
    def session_factory(self) -> sessionmaker:
        """
        Получение фабрики сессий (ленивая инициализация).
        
        Returns:
            SQLAlchemy sessionmaker.
        """
        if self._session_factory is None:
            self._session_factory = get_session_factory(self.engine)
        return self._session_factory
    
    def create_connection(self) -> SQLAlchemyConnection:
        """
        Создание подключения к базе данных.
        
        Returns:
            SQLAlchemyConnection для использования в репозиториях.
        """
        return SQLAlchemyConnection(
            engine=self.engine,
            session_factory=self.session_factory
        )
    
    def create_unit_of_work(self) -> UnitOfWork:
        """
        Создание Unit of Work для транзакций.
        
        Returns:
            UnitOfWork для координации изменений между репозиториями.
        """
        connection = self.create_connection()
        return UnitOfWork(connection)
    
    def create_tables(self) -> None:
        """Создание всех таблиц в базе данных."""
        Base.metadata.create_all(self.engine)
    
    def drop_tables(self) -> None:
        """Удаление всех таблиц из базы данных."""
        Base.metadata.drop_all(self.engine)
    
    def dispose(self) -> None:
        """Освобождение ресурсов движка БД."""
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None


# Глобальный экземпляр фабрики (Singleton)
_database_factory: Optional[DatabaseFactory] = None


def get_database_factory(config: Optional[DatabaseConfig] = None) -> DatabaseFactory:
    """
    Получение глобального экземпляра фабрики БД.
    
    Args:
        config: Опциональная конфигурация для переопределения.
        
    Returns:
        DatabaseFactory экземпляр.
    """
    global _database_factory
    
    if _database_factory is None:
        _database_factory = DatabaseFactory(config)
    elif config is not None:
        # Если передана новая конфигурация, пересоздаем фабрику
        _database_factory.dispose()
        _database_factory = DatabaseFactory(config)
    
    return _database_factory


def reset_database_factory() -> None:
    """Сброс глобальной фабрики (для тестов)."""
    global _database_factory
    if _database_factory is not None:
        _database_factory.dispose()
        _database_factory = None
