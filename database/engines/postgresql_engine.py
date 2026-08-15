"""PostgreSQL-реализация IDatabaseEngine.

Активируется через DB_TYPE=postgresql (+ DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/
DB_NAME в .env — см. database.db_config.DatabaseConfig.from_env()).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from database.engines.base import IDatabaseEngine

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import sessionmaker

    from database.db_config import DatabaseConfig


class PostgreSQLEngine(IDatabaseEngine):
    """Движок PostgreSQL — для многопользовательских/серверных развёртываний."""

    def __init__(self, config: DatabaseConfig):
        self._config = config
        self._engine: Engine | None = None
        self._session_factory: sessionmaker | None = None

    @property
    def db_type(self) -> str:
        return "postgresql"

    def get_engine(self) -> Engine:
        if self._engine is None:
            from sqlalchemy import create_engine

            # QueuePool (по умолчанию в SQLAlchemy для серверных СУБД) —
            # в отличие от SQLite здесь не нужен StaticPool/check_same_thread.
            self._engine = create_engine(
                self._config.get_connection_string(),
                echo=self._config.echo,
                pool_size=self._config.pool_size,
                pool_pre_ping=True,
            )
        return self._engine

    def get_session_factory(self) -> sessionmaker:
        if self._session_factory is None:
            from database.sqlalchemy_models import get_session_factory

            self._session_factory = get_session_factory(self.get_engine())
        return self._session_factory

    def create_tables(self) -> None:
        from database.sqlalchemy_models import create_tables

        create_tables(self.get_engine())

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None
