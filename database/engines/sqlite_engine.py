"""SQLite-реализация IDatabaseEngine.

Тонкая обёртка поверх уже существующих
database.sqlalchemy_models.create_database_engine/get_session_factory —
переиспользует их, а не изобретает подключение заново.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from database.engines.base import IDatabaseEngine

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import sessionmaker

    from database.db_config import DatabaseConfig


class SQLiteEngine(IDatabaseEngine):
    """Движок SQLite — используется по умолчанию (DB_TYPE=sqlite или не задан)."""

    def __init__(self, config: DatabaseConfig):
        self._config = config
        self._engine: Engine | None = None
        self._session_factory: sessionmaker | None = None

    @property
    def db_type(self) -> str:
        return "sqlite"

    def get_engine(self) -> Engine:
        if self._engine is None:
            from database.sqlalchemy_models import create_database_engine

            self._engine = create_database_engine(
                self._config.get_connection_string(), echo=self._config.echo
            )
        return self._engine

    def get_session_factory(self) -> sessionmaker:
        if self._session_factory is None:
            from database.sqlalchemy_models import get_session_factory

            self._session_factory = get_session_factory(self.get_engine())
        return self._session_factory

    def create_tables(self) -> None:
        from database.sqlalchemy_models import create_tables

        engine = self.get_engine()
        create_tables(engine)  # CREATE TABLE IF NOT EXISTS — не трогает уже существующие таблицы
        self._add_missing_columns(engine)

    @staticmethod
    def _add_missing_columns(engine: Engine) -> None:
        """Доводит уже существующие (legacy) таблицы до полей текущих моделей.

        Base.metadata.create_all() создаёт только отсутствующие ТАБЛИЦЫ —
        если таблица `devices`/`clients` уже существует (унаследована от
        database/db_manager.py::create_tables), новые колонки моделей
        (client_id, ready_date, email и т.п.) в неё не попадут. Тот же
        паттерн ALTER TABLE ADD COLUMN, что уже используется в
        db_manager.py::_run_migrations — только применён единообразно
        ко всем моделям.
        """
        import sqlalchemy as sa

        from database.sqlalchemy_models import Base

        _SQLITE_TYPE_MAP = {
            sa.Integer: "INTEGER",
            sa.Float: "REAL",
            sa.String: "TEXT",
            sa.Text: "TEXT",
            sa.DateTime: "TIMESTAMP",
        }

        with engine.begin() as conn:
            for table in Base.metadata.sorted_tables:
                existing = {
                    row[1]
                    for row in conn.exec_driver_sql(
                        f"PRAGMA table_info({table.name})"
                    ).fetchall()
                }
                if not existing:
                    continue  # таблица только что создана create_all — уже полная
                for column in table.columns:
                    if column.name in existing:
                        continue
                    sql_type = "TEXT"
                    for py_type, sql_name in _SQLITE_TYPE_MAP.items():
                        if isinstance(column.type, py_type):
                            sql_type = sql_name
                            break
                    conn.exec_driver_sql(
                        f"ALTER TABLE {table.name} ADD COLUMN {column.name} {sql_type}"
                    )

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None
