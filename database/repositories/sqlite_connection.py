#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SQLite реализация подключения к базе данных.

Использует стандартную библиотеку sqlite3.
В будущем может быть заменена на SQLAlchemy для лучшей абстракции.
"""

import sqlite3
from typing import Any, List, Optional
from contextlib import contextmanager

from .base import DatabaseConnection


class SQLiteConnection(DatabaseConnection):
    """
    Подключение к SQLite базе данных.
    
    Реализует интерфейс DatabaseConnection для работы с SQLite.
    """
    
    def __init__(self, db_path: str, timeout: float = 10.0):
        """
        Инициализация подключения.
        
        Args:
            db_path: Путь к файлу базы данных.
            timeout: Таймаут ожидания блокировки в секундах.
        """
        self.db_path = db_path
        self.timeout = timeout
        self._conn: Optional[sqlite3.Connection] = None
    
    def connect(self) -> sqlite3.Connection:
        """
        Установление подключения к БД.
        
        Returns:
            Объект подключения sqlite3.
        """
        if self._conn is not None:
            return self._conn
        
        try:
            self._conn = sqlite3.connect(self.db_path, timeout=self.timeout)
            self._conn.row_factory = sqlite3.Row
            
            # Оптимизация производительности
            self._execute_pragma('journal_mode=WAL')
            self._execute_pragma('synchronous=NORMAL')
            self._execute_pragma('cache_size=-6400')  # ~6MB
            self._execute_pragma('foreign_keys=ON')
            
            return self._conn
        except sqlite3.Error as e:
            raise RuntimeError(f"Не удалось подключиться к SQLite ({self.db_path}): {e}") from e
    
    def _execute_pragma(self, pragma: str) -> None:
        """Выполнение PRAGMA команды."""
        if self._conn:
            self._conn.execute(f'PRAGMA {pragma}')
    
    def disconnect(self) -> None:
        """Закрытие подключения к БД."""
        if self._conn:
            self._conn.close()
            self._conn = None
    
    @contextmanager
    def transaction(self):
        """
        Контекстный менеджер для транзакций.
        
        Пример использования:
            with db.transaction():
                db.execute(...)
        """
        if not self._conn:
            raise RuntimeError("Подключение к БД не установлено")
        
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
    
    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """
        Выполнение SQL запроса.
        
        Args:
            query: SQL запрос.
            params: Параметры запроса.
            
        Returns:
            Курсор с результатами.
        """
        if not self._conn:
            raise RuntimeError("Подключение к БД не установлено")
        
        cursor = self._conn.cursor()
        cursor.execute(query, params)
        return cursor
    
    def executemany(self, query: str, params_list: List[tuple]) -> sqlite3.Cursor:
        """
        Выполнение SQL запроса с несколькими наборами параметров.
        
        Args:
            query: SQL запрос.
            params_list: Список наборов параметров.
            
        Returns:
            Курсор с результатами.
        """
        if not self._conn:
            raise RuntimeError("Подключение к БД не установлено")
        
        cursor = self._conn.cursor()
        cursor.executemany(query, params_list)
        return cursor
    
    def commit(self) -> None:
        """Фиксация транзакции."""
        if self._conn:
            self._conn.commit()
    
    def rollback(self) -> None:
        """Откат транзакции."""
        if self._conn:
            self._conn.rollback()
    
    def begin_transaction(self) -> None:
        """Начало транзакции (неявно происходит при первом запросе)."""
        pass  # SQLite автоматически начинает транзакцию
    
    @property
    def is_connected(self) -> bool:
        """Проверка активности подключения."""
        return self._conn is not None
    
    @property
    def connection(self) -> Optional[sqlite3.Connection]:
        """Получение объекта подключения."""
        return self._conn
