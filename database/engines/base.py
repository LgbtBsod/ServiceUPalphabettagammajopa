"""Абстракция движка БД (IDatabaseEngine).

DIP: остальной код (database/sqlalchemy_database.py, Kernel DI) зависит
только от этого интерфейса, а не от конкретной СУБД.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session, sessionmaker


class IDatabaseEngine(ABC):
    """Контракт движка БД — независим от конкретной СУБД."""

    @abstractmethod
    def get_engine(self) -> Engine:
        """Возвращает SQLAlchemy Engine (создаёт при первом обращении)."""

    @abstractmethod
    def get_session_factory(self) -> sessionmaker:
        """Возвращает фабрику сессий, привязанную к этому движку."""

    def get_session(self) -> Session:
        """Удобный шорткат: новая сессия из фабрики этого движка."""
        return self.get_session_factory()()

    @abstractmethod
    def create_tables(self) -> None:
        """Создаёт все таблицы (database.sqlalchemy_models.Base.metadata)."""

    @abstractmethod
    def dispose(self) -> None:
        """Освобождает ресурсы движка (пул соединений и т.п.)."""

    @property
    @abstractmethod
    def db_type(self) -> str:
        """Строковый идентификатор СУБД ('sqlite' | 'postgresql')."""
