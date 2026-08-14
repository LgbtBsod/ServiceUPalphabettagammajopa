#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SQLAlchemy реализация подключения к базе данных.

Использует SQLAlchemy ORM для абстракции над СУБД.
Заменяет ручные SQL запросы на типобезопасный API.
Поддерживает SQLite, PostgreSQL, MySQL через настройки.
"""

from typing import Any, Optional, Union
from contextlib import contextmanager
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy import text

from .base import DatabaseConnection


class SQLAlchemyConnection(DatabaseConnection):
    """
    Подключение к базе данных через SQLAlchemy.
    
    Реализует интерфейс DatabaseConnection для работы с SQLAlchemy ORM.
    Поддерживает различные СУБД через строку подключения.
    
    Пример использования:
        # SQLite
        conn = SQLAlchemyConnection("sqlite:///database.db")
        
        # PostgreSQL
        conn = SQLAlchemyConnection("postgresql://user:pass@localhost/dbname")
        
        # MySQL
        conn = SQLAlchemyConnection("mysql://user:pass@localhost/dbname")
    """
    
    def __init__(self, connection_string_or_engine: Union[str, Engine], session_factory: Optional[sessionmaker] = None):
        """
        Инициализация подключения.
        
        Args:
            connection_string_or_engine: Строка подключения SQLAlchemy или готовый Engine.
            session_factory: Фабрика сессий (опционально).
        """
        if isinstance(connection_string_or_engine, str):
            self._engine = create_engine(connection_string_or_engine)
        else:
            self._engine = connection_string_or_engine
        
        self._session_factory = session_factory
        self._session: Optional[Session] = None
        self._owns_session = False
    
    @property
    def engine(self) -> Engine:
        """Получение SQLAlchemy движка."""
        return self._engine
    
    def connect(self) -> Session:
        """
        Установление подключения к БД.
        
        Returns:
            Объект сессии SQLAlchemy.
        """
        if self._session is not None:
            return self._session
        
        try:
            if self._session_factory:
                self._session = self._session_factory()
            else:
                self._session_factory = sessionmaker(bind=self._engine)
                self._session = self._session_factory()
            
            self._owns_session = True
            return self._session
        except Exception as e:
            raise RuntimeError(f"Не удалось подключиться к БД: {e}") from e
    
    def disconnect(self) -> None:
        """Закрытие подключения к БД."""
        if self._session and self._owns_session:
            try:
                self._session.close()
            except Exception:
                pass
            finally:
                self._session = None
    
    @contextmanager
    def transaction(self):
        """
        Контекстный менеджер для транзакций.
        
        Пример использования:
            with db.transaction():
                session.add(model)
        """
        if not self._session:
            raise RuntimeError("Подключение к БД не установлено")
        
        try:
            yield self._session
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
    
    def execute(self, query: str, params: tuple = ()) -> Any:
        """
        Выполнение SQL запроса (для обратной совместимости).
        
        Args:
            query: SQL запрос с именованными параметрами (:param_name).
            params: Параметры запроса (словарь или кортеж).
            
        Returns:
            Результат выполнения.
        """
        if not self._session:
            raise RuntimeError("Подключение к БД не установлено")
        
        from sqlalchemy import text
        # SQLAlchemy text() требует именованные параметры в виде словаря
        if params:
            if isinstance(params, (list, tuple)):
                # Преобразуем позиционные параметры в именованные
                # Заменяем ? на :param_N
                named_query = query
                param_dict = {}
                for i, val in enumerate(params):
                    placeholder = f":param_{i}"
                    named_query = named_query.replace('?', placeholder, 1)
                    param_dict[f"param_{i}"] = val
                result = self._session.execute(text(named_query), param_dict)
            else:
                result = self._session.execute(text(query), params)
        else:
            result = self._session.execute(text(query))
        return result
    
    def executemany(self, query: str, params_list: list[tuple]) -> Any:
        """
        Выполнение SQL запроса с несколькими наборами параметров.
        
        Args:
            query: SQL запрос.
            params_list: Список наборов параметров.
            
        Returns:
            Результат выполнения.
        """
        if not self._session:
            raise RuntimeError("Подключение к БД не установлено")
        
        from sqlalchemy import text
        result = self._session.execute(text(query), params_list)
        return result
    
    def commit(self) -> None:
        """Фиксация транзакции."""
        if self._session:
            self._session.commit()
    
    def rollback(self) -> None:
        """Откат транзакции."""
        if self._session:
            self._session.rollback()
    
    def begin_transaction(self) -> None:
        """Начало транзакции (неявно происходит при первом запросе)."""
        pass  # SQLAlchemy управляет транзакциями автоматически
    
    @property
    def is_connected(self) -> bool:
        """Проверка активности подключения."""
        return self._session is not None
    
    @property
    def session(self) -> Optional[Session]:
        """Получение объекта сессии."""
        return self._session
    
    def get_session(self) -> Session:
        """
        Получение текущей сессии или создание новой.
        
        Returns:
            Сессия SQLAlchemy.
        """
        if not self._session:
            return self.connect()
        return self._session
