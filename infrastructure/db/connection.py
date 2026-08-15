"""Database Connection.

Управление подключением к базе данных через SQLAlchemy.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """Управление подключением к базе данных.

    Реализует singleton pattern для подключения.
    Использует WAL mode для лучшей производительности.
    """

    _instance: "DatabaseConnection" | None = None
    _engine: Engine | None = None
    _session_factory: sessionmaker[Session] | None = None

    def __new__(cls, db_path: str = ":memory:"):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str = ":memory:"):
        if self._initialized:
            return

        self._db_path = db_path
        self._initialize(db_path)
        self._initialized = True
        logger.info(f"Database connection initialized: {db_path}")

    def _initialize(self, db_path: str) -> None:
        """Инициализирует подключение к БД."""
        self._engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            future=True,
            connect_args={"timeout": 30},
        )

        # Включаем WAL mode для SQLite
        if db_path != ":memory:":
            with self._engine.connect() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL"))
                conn.execute(text("PRAGMA synchronous=NORMAL"))
                conn.commit()

        self._session_factory = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

    @property
    def engine(self):
        """Возвращает SQLAlchemy engine."""
        return self._engine

    def get_session(self) -> Session:
        """Получает новую сессию."""
        return self._session_factory()

    @contextmanager
    def session_scope(self):
        """Контекстный менеджер для сессии с автоматическим commit/rollback."""
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_tables(self, base) -> None:
        """Создает таблицы в БД."""
        from infrastructure.db.repositories import Base

        Base.metadata.create_all(self._engine)
        logger.info("Database tables created")

    def drop_tables(self, base) -> None:
        """Удаляет все таблицы из БД."""
        from infrastructure.db.repositories import Base

        Base.metadata.drop_all(self._engine)
        logger.info("Database tables dropped")


def get_db_connection(db_path: str = ":memory:") -> DatabaseConnection:
    """Получает экземпляр подключения к БД."""
    return DatabaseConnection(db_path)
