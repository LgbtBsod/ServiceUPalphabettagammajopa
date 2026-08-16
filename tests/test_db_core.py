#!/usr/bin/env python3

"""Тесты для database/db_core.py::DatabaseCore — "ядро БД" (движок, сессии,
connection-guard, кэш запросов), выделенное из database.sqlalchemy_database
.Database, см. AUDIT_REPORT_v25.md, Task W.

database/sqlalchemy_database.py::TestDuplicateConnectionGuard уже покрывает
guard сквозь публичный API Database(); эти тесты бьют DatabaseCore напрямую
— независимо от того, что facade-класс сверху не меняет поведение."""

import os
import tempfile

import pytest

from database.db_config import DatabaseConfig
from database.db_core import (
    QUERY_CACHE_TTL_SECONDS,
    DatabaseCore,
    DuplicateDatabaseConnectionError,
)
from database.engines.sqlite_engine import SQLiteEngine


@pytest.fixture
def engine():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    eng = SQLiteEngine(DatabaseConfig(database=path))
    yield eng
    eng.dispose()
    if os.path.exists(path):
        os.remove(path)


class TestDatabaseCoreLifecycle:
    def test_creates_tables_on_construction(self, engine):
        core = DatabaseCore(engine)
        # session() работоспособна сразу после конструирования — таблицы уже есть.
        with core.session() as s:
            assert s is not None

    def test_engine_property_exposes_underlying_engine(self, engine):
        core = DatabaseCore(engine)
        assert core.engine is engine

    def test_second_core_on_same_path_raises(self, engine):
        DatabaseCore(engine)
        same_path_engine = SQLiteEngine(
            DatabaseConfig(database=str(engine.get_engine().url).replace("sqlite:///", ""))
        )
        with pytest.raises(DuplicateDatabaseConnectionError):
            DatabaseCore(same_path_engine)
        same_path_engine.dispose()


class TestDatabaseCoreQueryCache:
    def test_cache_starts_empty_with_configured_ttl(self, engine):
        core = DatabaseCore(engine)
        stats = core.query_cache.get_stats()
        assert stats["size"] == 0
        assert stats["default_ttl_seconds"] == QUERY_CACHE_TTL_SECONDS == 3600

    def test_set_then_get_round_trips(self, engine):
        core = DatabaseCore(engine)
        core.query_cache.set("k", ["a", "b"])
        assert core.query_cache.get("k") == ["a", "b"]

    def test_refresh_query_cache_clears_and_reports_count(self, engine):
        core = DatabaseCore(engine)
        core.query_cache.set("dict_values:brands", ["Apple"])
        core.query_cache.set("dict_values:device_types", ["Ноутбук"])

        cleared = core.refresh_query_cache()

        assert cleared == 2
        assert core.query_cache.get_stats()["size"] == 0

    def test_refresh_query_cache_on_empty_cache_returns_zero(self, engine):
        core = DatabaseCore(engine)
        assert core.refresh_query_cache() == 0

    def test_each_core_instance_has_its_own_cache(self, engine):
        """Кэш — атрибут инстанса DatabaseCore, не модульный/классовый
        singleton — два разных DatabaseCore (например, два теста подряд, или
        Database() на разных временных БД) не должны видеть записи друг друга."""
        fd, other_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            core_a = DatabaseCore(engine)
            other_engine = SQLiteEngine(DatabaseConfig(database=other_path))
            core_b = DatabaseCore(other_engine)

            core_a.query_cache.set("k", "from-a")

            assert core_b.query_cache.get("k") is None
            other_engine.dispose()
        finally:
            if os.path.exists(other_path):
                os.remove(other_path)
