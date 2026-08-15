#!/usr/bin/env python3

"""SSOT Database Manager - Единая точка управления базой данных

Принципы:
- SSOT (Single Source of Truth): Все данные в одной БД
- Singleton: Единственный экземпляр подключения
- Repository Pattern: Доступ через репозитории
- Unit of Work: Транзакционная целостность
"""

import logging
import sqlite3
from contextlib import contextmanager
from typing import Self

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from config.settings import settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Менеджер базы данных (Singleton).

    Обеспечивает:
    - Единое подключение ко всем данным (SSOT)
    - Поддержку SQLite/PostgreSQL/MSSQL
    - Пул соединений для производительности
    - Транзакционную целостность (Unit of Work)
    """

    _instance: DatabaseManager | None = None
    _engine: Engine | None = None
    _session_factory: scoped_session | None = None
    _connection: sqlite3.Connection | None = None

    def __new__(cls, *args, **kwargs) -> Self:
        """Singleton паттерн."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, database_url: str | None = None):
        """Инициализация подключения."""
        if hasattr(self, "_initialized") and self._initialized:
            return

        self.database_url = database_url or settings.database.url
        self._initialize()
        self._initialized = True

    def _initialize(self) -> None:
        """Инициализация подключений."""
        logger.info(f"Инициализация DatabaseManager: {self.database_url}")

        # SQLAlchemy engine для ORM
        self._engine = create_engine(
            self.database_url,
            pool_pre_ping=True,  # Проверка соединения перед использованием
            pool_size=20,  # Размер пула для высокой нагрузки
            max_overflow=10,  # Дополнительные соединения при пиках
            echo=settings.database.debug_sql,  # Логирование SQL в debug режиме
        )

        # Session factory
        self._session_factory = scoped_session(
            sessionmaker(bind=self._engine, autocommit=False, autoflush=False)
        )

        # SQLite connection для legacy операций (если SQLite)
        if self.database_url.startswith("sqlite"):
            db_path = self.database_url.replace("sqlite:///", "")
            self._connection = sqlite3.connect(
                db_path,
                timeout=30,  # Увеличенный таймаут для конкурентного доступа
                check_same_thread=False,  # Разрешить использование из разных потоков
            )
            self._connection.row_factory = sqlite3.Row

            # Оптимизация SQLite
            self._apply_sqlite_optimizations()

        logger.info("✅ DatabaseManager инициализирован")

    def _apply_sqlite_optimizations(self) -> None:
        """Применение оптимизаций SQLite для производительности."""
        if not self._connection:
            return

        optimizations = [
            "PRAGMA journal_mode=WAL",  # Параллельные чтение/запись
            "PRAGMA synchronous=NORMAL",  # Баланс скорость/надёжность
            "PRAGMA cache_size=-6400",  # 6MB кэш страниц
            "PRAGMA temp_store=MEMORY",  # Временные таблицы в памяти
            "PRAGMA mmap_size=268435456",  # Memory-mapped I/O (256MB)
            "PRAGMA foreign_keys=ON",  # Внешние ключи
        ]

        try:
            for pragma in optimizations:
                self._connection.execute(pragma)
            self._connection.commit()
            logger.debug("Применены оптимизации SQLite")
        except sqlite3.Error as e:
            logger.warning(f"Не удалось применить оптимизацию SQLite: {e}")

    @property
    def session(self) -> Session:
        """Получение сессии SQLAlchemy."""
        if not self._session_factory:
            raise RuntimeError("DatabaseManager не инициализирован")
        return self._session_factory()

    @property
    def connection(self) -> sqlite3.Connection:
        """Получение raw SQLite подключения."""
        if not self._connection:
            raise RuntimeError("SQLite подключение недоступно")
        return self._connection

    @contextmanager
    def transaction(self):
        """Контекстный менеджер для транзакций (Unit of Work).

        Использование:
            with db_manager.transaction():
                repo.add(entity)
                repo.update(other_entity)
        """
        session = self.session
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Транзакция откатана: {e}", exc_info=True)
            raise
        finally:
            session.close()

    def create_tables(self, base: type) -> None:
        """Создание всех таблиц в БД."""
        logger.info("Создание таблиц в БД...")
        base.metadata.create_all(bind=self._engine)
        logger.info("✅ Таблицы созданы")

    def drop_tables(self, base: type) -> None:
        """Удаление всех таблиц (для тестов)."""
        logger.warning("Удаление всех таблиц из БД!")
        base.metadata.drop_all(bind=self._engine)

    @contextmanager
    def get_repository(self, repository_class: type):
        """Получение репозитория в контексте транзакции.

        Пример:
            with db_manager.get_repository(ClientRepository) as repo:
                clients = repo.get_all()
        """
        session = self.session
        repo = repository_class(session)
        try:
            yield repo
        finally:
            session.close()

    def execute_query(self, query: str, params: tuple = ()) -> list:
        """Выполнение raw SQL запроса (для сложных случаев)."""
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, params)
            self.connection.commit()
            return cursor.fetchall()
        except sqlite3.Error as e:
            logger.exception(f"Ошибка SQL запроса: {e}")
            raise

    def close(self) -> None:
        """Закрытие подключений (при shutdown приложения)."""
        logger.info("Закрытие DatabaseManager...")

        if self._session_factory:
            self._session_factory.remove()

        if self._connection:
            self._connection.close()

        if self._engine:
            self._engine.dispose()

        logger.info("✅ DatabaseManager закрыт")


# Singleton instance
db_manager = DatabaseManager()


def get_db_manager() -> DatabaseManager:
    """Получение экземпляра DatabaseManager (DI friendly)."""
    return db_manager
