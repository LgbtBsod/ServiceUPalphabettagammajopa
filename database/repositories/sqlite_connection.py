#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SQLAlchemy реализация подключения к базе данных.

Использует SQLAlchemy ORM для абстракции над СУБД.
Заменяет ручные SQL запросы на типобезопасный API.
"""

from typing import Any, Optional
from contextlib import contextmanager
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.engine import Engine

from .base import DatabaseConnection


class SQLAlchemyConnection(DatabaseConnection):
    """
    Подключение к базе данных через SQLAlchemy.
    
    Реализует интерфейс DatabaseConnection для работы с SQLAlchemy ORM.
    """
    
    def __init__(self, engine: Engine, session_factory: Optional[sessionmaker] = None):
        """
        Инициализация подключения.
        
        Args:
            engine: SQLAlchemy движок.
            session_factory: Фабрика сессий (опционально).
        """
        self._engine = engine
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
            query: SQL запрос.
            params: Параметры запроса.
            
        Returns:
            Результат выполнения.
        """
        if not self._session:
            raise RuntimeError("Подключение к БД не установлено")
        
        from sqlalchemy import text
        result = self._session.execute(text(query), params if params else {})
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
