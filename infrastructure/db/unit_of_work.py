"""
Unit of Work Pattern.

Управление транзакциями и атомарностью операций.
"""

from typing import Optional
from contextlib import contextmanager
import logging

from sqlalchemy.orm import Session

from core.base import LoggableMixin
from infrastructure.db.connection import DatabaseConnection


logger = logging.getLogger(__name__)


class UnitOfWork(LoggableMixin):
    """
    Unit of Work для управления транзакциями.
    
    Реализует паттерн Unit of Work для обеспечения:
    - Атомарности операций
    - Отслеживания изменений
    - Правильного commit/rollback
    """
    
    def __init__(self, db_connection: Optional[DatabaseConnection] = None):
        super().__init__()
        self._db = db_connection or DatabaseConnection()
        self._session: Optional[Session] = None
        self._is_active = False
    
    @contextmanager
    def begin(self):
        """
        Контекстный менеджер для транзакции.
        
        Пример:
            with unit_of_work.begin() as uow:
                repo = ClientRepository(uow.session)
                repo.save(client)
                # Автоматический commit в конце
        """
        session = self._db.get_session()
        self._session = session
        self._is_active = True
        
        try:
            yield self
            session.commit()
            self.logger.debug("Transaction committed")
        except Exception as e:
            session.rollback()
            self.logger.error(f"Transaction rolled back: {e}")
            raise
        finally:
            session.close()
            self._session = None
            self._is_active = False
    
    @property
    def session(self) -> Session:
        """Получает текущую сессию."""
        if self._session is None:
            raise RuntimeError("UnitOfWork not started. Use 'with unit_of_work.begin()'")
        return self._session
    
    @property
    def is_active(self) -> bool:
        """Проверяет активна ли транзакция."""
        return self._is_active
    
    def mark_for_deletion(self, entity) -> None:
        """Помечает сущность на удаление."""
        if self._session:
            self._session.delete(entity)
            self.logger.debug(f"Entity marked for deletion: {entity}")
    
    def register_new(self, entity) -> None:
        """Регистрирует новую сущность."""
        if self._session:
            self._session.add(entity)
            self.logger.debug(f"New entity registered: {entity}")
    
    def register_dirty(self, entity) -> None:
        """Регистрирует изменённую сущность."""
        # SQLAlchemy автоматически отслеживает изменения
        if self._session:
            self._session.flush()
            self.logger.debug(f"Entity changes flushed: {entity}")


# Глобальный экземпляр
_global_uow: Optional[UnitOfWork] = None


def get_unit_of_work() -> UnitOfWork:
    """Получает глобальный Unit of Work."""
    global _global_uow
    if _global_uow is None:
        _global_uow = UnitOfWork()
    return _global_uow


def reset_unit_of_work() -> None:
    """Сбрасывает глобальный Unit of Work (для тестов)."""
    global _global_uow
    _global_uow = None
