#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Репозиторий базовый (интерфейс).

Определяет абстрактный интерфейс для всех репозиториев.
Реализует принцип Dependency Inversion Principle (DIP) из SOLID.
"""

from abc import ABC, abstractmethod
from typing import TypeVar, Generic, List, Optional, Any, Dict
from datetime import datetime

T = TypeVar('T')


class BaseRepository(ABC, Generic[T]):
    """
    Абстрактный базовый класс репозитория.
    
    Все репозитории должны наследовать этот класс и реализовать
    методы CRUD (Create, Read, Update, Delete).
    """
    
    @abstractmethod
    def get(self, id: int) -> Optional[T]:
        """
        Получение записи по ID.
        
        Args:
            id: Идентификатор записи.
            
        Returns:
            Объект модели или None если не найдено.
        """
        pass
    
    @abstractmethod
    def get_all(self, filters: Optional[Dict[str, Any]] = None) -> List[T]:
        """
        Получение всех записей с опциональной фильтрацией.
        
        Args:
            filters: Словарь фильтров.
            
        Returns:
            Список объектов моделей.
        """
        pass
    
    @abstractmethod
    def create(self, data: Dict[str, Any]) -> T:
        """
        Создание новой записи.
        
        Args:
            data: Данные для создания.
            
        Returns:
            Созданный объект модели.
        """
        pass
    
    @abstractmethod
    def update(self, id: int, data: Dict[str, Any]) -> Optional[T]:
        """
        Обновление записи.
        
        Args:
            id: Идентификатор записи.
            data: Новые данные.
            
        Returns:
            Обновленный объект модели или None если не найдено.
        """
        pass
    
    @abstractmethod
    def delete(self, id: int) -> bool:
        """
        Удаление записи.
        
        Args:
            id: Идентификатор записи.
            
        Returns:
            True если удалено, False если не найдено.
        """
        pass
    
    @abstractmethod
    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Подсчет записей с опциональной фильтрацией.
        
        Args:
            filters: Словарь фильтров.
            
        Returns:
            Количество записей.
        """
        pass
    
    @abstractmethod
    def exists(self, id: int) -> bool:
        """
        Проверка существования записи.
        
        Args:
            id: Идентификатор записи.
            
        Returns:
            True если существует, False иначе.
        """
        pass


class DatabaseConnection(ABC):
    """
    Абстрактный класс подключения к базе данных.
    
    Позволяет переключаться между различными СУБД (SQLite, PostgreSQL, MySQL)
    без изменения кода репозиториев.
    """
    
    @abstractmethod
    def connect(self) -> Any:
        """Установление подключения к БД."""
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Закрытие подключения к БД."""
        pass
    
    @abstractmethod
    def execute(self, query: str, params: tuple = ()) -> Any:
        """
        Выполнение SQL запроса.
        
        Args:
            query: SQL запрос.
            params: Параметры запроса.
            
        Returns:
            Результат выполнения.
        """
        pass
    
    @abstractmethod
    def executemany(self, query: str, params_list: List[tuple]) -> Any:
        """
        Выполнение SQL запроса с несколькими наборами параметров.
        
        Args:
            query: SQL запрос.
            params_list: Список наборов параметров.
            
        Returns:
            Результат выполнения.
        """
        pass
    
    @abstractmethod
    def commit(self) -> None:
        """Фиксация транзакции."""
        pass
    
    @abstractmethod
    def rollback(self) -> None:
        """Откат транзакции."""
        pass
    
    @abstractmethod
    def begin_transaction(self) -> None:
        """Начало транзакции."""
        pass
    
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Проверка активности подключения."""
        pass
