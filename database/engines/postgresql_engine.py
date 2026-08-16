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
        self._add_missing_columns(self.get_engine())

    @staticmethod
    def _add_missing_columns(engine: Engine) -> None:
        """Postgres-аналог SQLiteEngine._add_missing_columns() —
        create_all() создаёт только отсутствующие ТАБЛИЦЫ, никогда не
        добавляет колонки в уже существующие. Без этого шага любая новая
        колонка модели (например Device.version_id/record_locks в этой
        сессии) тихо не долетала бы до уже развёрнутой Postgres-базы, и
        первый же INSERT/UPDATE падал бы ProgrammingError'ом "column does
        not exist" на каждом сохранении, см. AUDIT_REPORT_v25.md.

        Не проверялось против реального сервера PostgreSQL (в этом
        окружении его нет) — синтаксис information_schema.columns/ALTER
        TABLE ADD COLUMN стандартный (SQL:2003), но перед боевым
        использованием стоит прогнать вручную на тестовой Postgres-базе.
        """
        import sqlalchemy as sa

        from database.sqlalchemy_models import Base

        _PG_TYPE_MAP = {
            sa.Integer: "INTEGER",
            sa.Float: "DOUBLE PRECISION",
            sa.Boolean: "BOOLEAN",
            sa.DateTime: "TIMESTAMP WITH TIME ZONE",
            sa.String: "VARCHAR",
            sa.Text: "TEXT",
        }

        with engine.begin() as conn:
            for table in Base.metadata.sorted_tables:
                # Как и в SQLite-версии: имена таблиц/колонок берутся из
                # доверенной Base.metadata (не из пользовательского ввода),
                # поэтому f-string здесь безопасен — тот же подход, что и
                # в SQLiteEngine._add_missing_columns.
                existing = {
                    row[0]
                    for row in conn.exec_driver_sql(
                        "SELECT column_name FROM information_schema.columns "
                        f"WHERE table_name = '{table.name}'"
                    ).fetchall()
                }
                if not existing:
                    continue  # таблица только что создана create_all() — уже полная
                for column in table.columns:
                    if column.name in existing:
                        continue
                    sql_type = "TEXT"
                    for py_type, sql_name in _PG_TYPE_MAP.items():
                        if isinstance(column.type, py_type):
                            sql_type = sql_name
                            break
                    conn.exec_driver_sql(
                        f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {sql_type}'
                    )

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None
