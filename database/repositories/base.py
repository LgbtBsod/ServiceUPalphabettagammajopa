#!/usr/bin/env python3

"""Репозиторий базовый (интерфейс).

Определяет абстрактный интерфейс для всех репозиториев.
Реализует принцип Dependency Inversion Principle (DIP) из SOLID.
"""

from abc import ABC, abstractmethod
from typing import Any, TypeVar

T = TypeVar("T")


class BaseRepository[T](ABC):
    """Абстрактный базовый класс репозитория.

    Все репозитории должны наследовать этот класс и реализовать
    методы CRUD (Create, Read, Update, Delete).
    """

    @abstractmethod
    def get(self, id: int) -> T | None:
        """Получение записи по ID.

        Args:
            id: Идентификатор записи.

        Returns:
            Объект модели или None если не найдено.
        """

    @abstractmethod
    def get_all(self, filters: dict[str, Any] | None = None) -> list[T]:
        """Получение всех записей с опциональной фильтрацией.

        Args:
            filters: Словарь фильтров.

        Returns:
            Список объектов моделей.
        """

    @abstractmethod
    def create(self, data: dict[str, Any]) -> T:
        """Создание новой записи.

        Args:
            data: Данные для создания.

        Returns:
            Созданный объект модели.
        """

    @abstractmethod
    def update(self, id: int, data: dict[str, Any]) -> T | None:
        """Обновление записи.

        Args:
            id: Идентификатор записи.
            data: Новые данные.

        Returns:
            Обновленный объект модели или None если не найдено.
        """

    @abstractmethod
    def delete(self, id: int) -> bool:
        """Удаление записи.

        Args:
            id: Идентификатор записи.

        Returns:
            True если удалено, False если не найдено.
        """

    @abstractmethod
    def count(self, filters: dict[str, Any] | None = None) -> int:
        """Подсчет записей с опциональной фильтрацией.

        Args:
            filters: Словарь фильтров.

        Returns:
            Количество записей.
        """

    @abstractmethod
    def exists(self, id: int) -> bool:
        """Проверка существования записи.

        Args:
            id: Идентификатор записи.

        Returns:
            True если существует, False иначе.
        """


class DatabaseConnection(ABC):
    """Абстрактный класс подключения к базе данных.

    Позволяет переключаться между различными СУБД (SQLite, PostgreSQL, MySQL)
    без изменения кода репозиториев.
    """

    @abstractmethod
    def connect(self) -> Any:
        """Установление подключения к БД."""

    @abstractmethod
    def disconnect(self) -> None:
        """Закрытие подключения к БД."""

    @abstractmethod
    def execute(self, query: str, params: tuple = ()) -> Any:
        """Выполнение SQL запроса.

        Args:
            query: SQL запрос.
            params: Параметры запроса.

        Returns:
            Результат выполнения.
        """

    @abstractmethod
    def executemany(self, query: str, params_list: list[tuple]) -> Any:
        """Выполнение SQL запроса с несколькими наборами параметров.

        Args:
            query: SQL запрос.
            params_list: Список наборов параметров.

        Returns:
            Результат выполнения.
        """

    @abstractmethod
    def commit(self) -> None:
        """Фиксация транзакции."""

    @abstractmethod
    def rollback(self) -> None:
        """Откат транзакции."""

    @abstractmethod
    def begin_transaction(self) -> None:
        """Начало транзакции."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Проверка активности подключения."""
