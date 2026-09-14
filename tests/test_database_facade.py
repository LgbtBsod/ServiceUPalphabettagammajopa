#!/usr/bin/env python3

"""Тесты для database/sqlalchemy_database.py::Database — живого facade,
на который опираются gui/, pwa/ и managers/ через core.get_db_access().

До этих тестов покрытие было только у database/repositories/ — параллельного,
никогда не подключённого к приложению слоя (см. AUDIT_REPORT_v21.md, удалён).
"""

import os
import sqlite3
import tempfile

import pytest

from database.db_config import DatabaseConfig
from database.engines.sqlite_engine import SQLiteEngine
from database.sqlalchemy_database import (
    Database,
    DuplicateDatabaseConnectionError,
    QueryError,
)


@pytest.fixture
def db():
    """Facade на временной SQLite БД — не трогает реальные данные пользователя."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = SQLiteEngine(DatabaseConfig(database=path))
    database = Database(engine)  # __init__ сам вызывает engine.create_tables()
    yield database
    engine.dispose()
    if os.path.exists(path):
        os.remove(path)


# Точная копия схемы `devices` из реального data/serviceup.db (унаследована
# от database/db_manager.py, до перехода на SQLAlchemy) — total_price/
# prepayment здесь TEXT, а не REAL, как в текущей ORM-модели
# (Device.total_price: Mapped[float]). SQLite хранит значения по affinity
# ФИЗИЧЕСКОЙ колонки, а не по тому, что думает ORM: TEXT affinity
# конвертирует даже числовые значения в текстовое представление при
# записи, так что device.total_price, прочитанный через ORM, реально
# приходит как str. create_tables() ниже — CREATE TABLE IF NOT EXISTS,
# так что уже существующая (созданная этим фикстуром) таблица не
# трогается, а только донасыщается отсутствующими колонками.
_LEGACY_DEVICES_TABLE_SQL = """
CREATE TABLE devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number TEXT UNIQUE,
    receipt_date TEXT,
    completion_date TEXT,
    device_type TEXT,
    brand TEXT,
    model TEXT,
    serial_number TEXT,
    defect TEXT,
    appearance TEXT,
    completeness TEXT,
    work_items TEXT,
    client_name TEXT,
    client_status TEXT DEFAULT 'Новый',
    phone TEXT,
    total_price TEXT,
    prepayment TEXT,
    status TEXT DEFAULT 'Диагностика',
    priority TEXT DEFAULT 'Обычный',
    engineer TEXT,
    warranty TEXT,
    notes TEXT,
    photos TEXT,
    expense TEXT DEFAULT '0',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    total_price_num REAL DEFAULT 0,
    prepayment_num REAL DEFAULT 0,
    expense_num REAL DEFAULT 0,
    client_id INTEGER,
    ready_date TEXT,
    diagnostic_cost TEXT,
    repair_cost TEXT,
    updated_at TIMESTAMP,
    created_by_id INTEGER,
    updated_by_id INTEGER,
    version_id INTEGER
)
"""


@pytest.fixture
def legacy_db():
    """Facade поверх БД с legacy-схемой `devices` (total_price/prepayment
    TEXT) — воспроизводит реальный data/serviceup.db, а не "чистую" схему,
    которую create_tables() рисует с нуля на пустом файле."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute(_LEGACY_DEVICES_TABLE_SQL)
    conn.commit()
    conn.close()

    engine = SQLiteEngine(DatabaseConfig(database=path))
    database = Database(engine)
    yield database
    engine.dispose()
    if os.path.exists(path):
        os.remove(path)


def _sample_device(**overrides) -> dict:
    data = {
        "order_number": "00001",
        "receipt_date": "2026-01-01",
        "device_type": "Ноутбук",
        "brand": "Test",
        "model": "TestModel",
        "serial_number": "SN1",
        "defect": "Не включается",
        "client_name": "Иван Иванов",
        "phone": "+7 (999) 123-45-67",
        "total_price": "1000",
        "prepayment": "0",
        "status": "Диагностика",
        "priority": "Обычный",
    }
    data.update(overrides)
    return data


class TestOrderCounter:
    def test_peek_does_not_increment(self, db):
        first_peek = db.peek_next_order_number()
        second_peek = db.peek_next_order_number()
        assert first_peek == second_peek

    def test_get_next_order_number_increments(self, db):
        first = db.get_next_order_number()
        second = db.get_next_order_number()
        assert second == first + 1

    def test_peek_matches_next_get(self, db):
        peeked = db.peek_next_order_number()
        gotten = db.get_next_order_number()
        assert peeked == gotten


class TestDeviceCRUD:
    def test_add_and_get_device(self, db):
        device_id = db.add_device(_sample_device())
        assert device_id is not None

        device = db.get_device(device_id)
        assert device is not None
        assert device["client_name"] == "Иван Иванов"
        assert device["status"] == "Диагностика"

    def test_update_device(self, db):
        device_id = db.add_device(_sample_device())
        ok = db.update_device(device_id, _sample_device(status="Готов к выдаче"))
        assert ok is True

        device = db.get_device(device_id)
        assert device["status"] == "Готов к выдаче"

    def test_delete_device(self, db):
        device_id = db.add_device(_sample_device())
        assert db.delete_device(device_id) is True
        assert db.get_device(device_id) is None

    def test_get_device_by_order_number(self, db):
        db.add_device(_sample_device(order_number="00042"))
        device = db.get_device_by_order_number("00042")
        assert device is not None
        assert device["order_number"] == "00042"

    def test_search_devices_by_client_name(self, db):
        db.add_device(_sample_device(client_name="Пётр Петров"))
        results = db.search_devices("Петров")
        assert any(d["client_name"] == "Пётр Петров" for d in results)

    def test_get_all_devices(self, db):
        db.add_device(_sample_device(order_number="00001"))
        db.add_device(_sample_device(order_number="00002"))
        devices = db.get_all_devices()
        assert len(devices) >= 2


class TestUpdateDeviceStatus:
    """Регрессия AUDIT_v25: update_device_status() (PWA PUT /status, кнопка
    "выдать") раньше не бампил version_id и не писал финзапись при выдаче —
    расходился с update_device()."""

    def test_bumps_version_on_real_change(self, db):
        device_id = db.add_device(_sample_device())
        db.update_device_status(device_id, "Готов к выдаче")
        assert db.get_device(device_id)["version"] == 2

    def test_noop_status_does_not_bump_version(self, db):
        device_id = db.add_device(_sample_device())
        db.update_device_status(device_id, "Диагностика")  # уже такой статус
        assert db.get_device(device_id)["version"] == 1

    def test_issuing_creates_finance_record(self, db):
        device_id = db.add_device(_sample_device(total_price="1500", expense="300"))
        db.update_device_status(device_id, "Выдан клиенту")

        finances = db.get_finances()
        record = next(
            (f for f in finances if f["order_number"] == "00001"), None
        )
        assert record is not None
        assert record["income"] == 1500.0
        assert record["expense"] == 300.0

    def test_reissuing_does_not_duplicate_finance_record(self, db):
        device_id = db.add_device(_sample_device(total_price="1500"))
        db.update_device_status(device_id, "Выдан клиенту")
        db.update_device_status(device_id, "Диагностика")
        db.update_device_status(device_id, "Выдан клиенту")

        finances = [f for f in db.get_finances() if f["order_number"] == "00001"]
        assert len(finances) == 1


class TestUpdateDeviceStatusWithLegacyTextTotalPrice:
    """Regression — found via a live run of the app (create an order in the
    Flet GUI, print the completion act, confirm "Выдан клиенту"): real
    databases created before the SQLAlchemy migration (see
    database/db_manager.py) declare devices.total_price/prepayment as TEXT,
    not REAL — the current ORM model maps them as Float, but SQLite stores
    by the PHYSICAL column's type affinity, not what the ORM believes.
    device.total_price therefore comes back as a plain str on such
    databases, and update_device_status()'s `income = device.total_price or
    0.0` (no parse_price_to_float, unlike the very next line for expense)
    crashed with `TypeError: unsupported operand type(s) for -: 'str' and
    'float'` in _upsert_finance_record()'s `income - expense` — silently
    caught and logged by update_device_status()'s own except-clause, so the
    UI just showed "Не удалось изменить статус" with no indication why.
    This is NOT a synthetic edge case — it reproduces on every legacy-shaped
    devices table, e.g. the tracked dev data/serviceup.db itself."""

    def test_issuing_a_device_with_legacy_text_total_price_does_not_crash(
        self, legacy_db
    ):
        device_id = legacy_db.add_device(
            _sample_device(total_price="1500", expense="300")
        )

        ok = legacy_db.update_device_status(device_id, "Выдан клиенту")

        assert ok is True, (
            "update_device_status() must succeed even when the legacy "
            "total_price column stores numbers as TEXT"
        )
        finances = legacy_db.get_finances()
        record = next(
            (f for f in finances if f["order_number"] == "00001"), None
        )
        assert record is not None
        assert record["income"] == 1500.0
        assert record["expense"] == 300.0
        assert record["profit"] == 1200.0


class TestCalculate:
    """calculate() — тяжёлые SQL-агрегации вместо питоновских циклов,
    см. AUDIT_REPORT_v21.md о 4-кратном дублировании 'просрочено > 14 дней'."""

    def test_overdue_count_excludes_recent_devices(self, db):
        db.add_device(_sample_device(order_number="00001", receipt_date="2026-01-01"))
        # threshold_days=0 — всё старше "сегодня" считается просроченным
        count = db.calculate("overdue_count", threshold_days=0)
        assert count >= 1

    def test_overdue_count_zero_for_closed_status(self, db):
        db.add_device(
            _sample_device(
                order_number="00001",
                receipt_date="2020-01-01",
                status="Выдан клиенту",
            )
        )
        count = db.calculate("overdue_count", threshold_days=0)
        assert count == 0

    def test_calculate_unknown_name_raises(self, db):
        with pytest.raises(ValueError):
            db.calculate("not_a_real_calculation")

    def test_list_calculations_matches_what_calculate_accepts(self, db):
        """Регрессия AUDIT_v25/Task P: list_calculations() и calculate()
        обязаны читать один и тот же whitelist (см. CalculateMixin.
        _calculation_handlers) — иначе управляющий код (AnalyticsService)
        не может надёжно проверить свои имена отчётов через интроспекцию."""
        names = db.list_calculations()
        assert "overdue_count" in names
        for name in names:
            db.calculate(name)  # не должно бросить ValueError "неизвестное"


class TestDeviceToRowEagerLoading:
    """Workflow-найденный N+1: device_to_row() (database/facade/shared.py)
    читает device.created_by.full_name/device.updated_by.full_name;
    Device.created_by/updated_by — обычные relationship() без lazy= (т.е.
    lazy='select' по умолчанию). Без eager load каждая строка результата с
    ещё не встреченным created_by_id/updated_by_id тянула отдельный SELECT
    к employees — классический N+1 (10 устройств от 10 разных сотрудников
    -> 11 SQL вместо 1)."""

    def _add_employees(self, db, n: int) -> list[int]:
        from database.sqlalchemy_models import Employee

        ids = []
        with db._session() as s:
            for i in range(n):
                emp = Employee(full_name=f"Сотрудник {i}", login=f"emp{i}")
                s.add(emp)
                s.flush()
                ids.append(emp.id)
            s.commit()
        return ids

    def _count_statements(self, db, fn):
        from sqlalchemy import event

        engine = db.engine.get_engine()
        count = 0

        def _before_cursor_execute(*_a, **_kw):
            nonlocal count
            count += 1

        event.listen(engine, "before_cursor_execute", _before_cursor_execute)
        try:
            return fn(), count
        finally:
            event.remove(engine, "before_cursor_execute", _before_cursor_execute)

    def test_get_all_devices_does_not_n_plus_1_on_created_by(self, db):
        emp_ids = self._add_employees(db, 5)
        for i, emp_id in enumerate(emp_ids):
            db.add_device(_sample_device(order_number=f"0000{i}", created_by_id=emp_id))

        rows, stmt_count = self._count_statements(db, db.get_all_devices)
        assert len(rows) == 5
        assert all(r["created_by_name"] for r in rows)
        # Без eager load: 1 (devices) + до 5 (по одному на каждого нового
        # created_by, т.к. updated_by совпадает с created_by в add_device()
        # и берётся из identity map) = минимум 6. selectinload сводит это к
        # базовому запросу + 1-2 батч-запросам на relationship, а не по
        # одному на строку.
        assert stmt_count <= 3, f"Похоже на N+1: выполнено {stmt_count} SQL-запросов"

    def test_get_devices_by_filters_does_not_n_plus_1_on_created_by(self, db):
        emp_ids = self._add_employees(db, 5)
        for i, emp_id in enumerate(emp_ids):
            db.add_device(_sample_device(order_number=f"1000{i}", created_by_id=emp_id))

        rows, stmt_count = self._count_statements(
            db,
            lambda: db.get_devices_by_filters(
                status_filter="Все", priority_filter="Все"
            ),
        )
        assert len(rows) == 5
        assert stmt_count <= 3, f"Похоже на N+1: выполнено {stmt_count} SQL-запросов"


class TestDictionaryQueryCache:
    """Регрессия AUDIT_v25/Task W: get_dict_values() раньше кэшировался в
    ad-hoc self._dict_cache (dict, без TTL) прямо на facade-классе — теперь
    идёт через DatabaseCore.query_cache (core.module_manager.ModuleCache,
    TTL ~1 час, см. database/db_core.py::QUERY_CACHE_TTL_SECONDS)."""

    def test_second_call_is_served_from_cache(self, db):
        db.add_dict_value("brands", "Apple")
        db.get_dict_values("brands")  # первый вызов — MISS, населяет кэш
        stats_before = db.core.query_cache.get_stats()

        db.get_dict_values("brands")  # второй — обязан быть HIT

        stats_after = db.core.query_cache.get_stats()
        assert stats_after["hits"] == stats_before["hits"] + 1

    def test_add_dict_value_invalidates_cache_for_that_type(self, db):
        db.add_dict_value("brands", "Apple")
        db.get_dict_values("brands")  # населяет кэш ["Apple"]

        db.add_dict_value("brands", "Samsung")
        values = db.get_dict_values("brands")

        assert set(values) == {"Apple", "Samsung"}

    def test_update_dict_value_invalidates_cache(self, db):
        db.add_dict_value("brands", "Appel")  # опечатка нарочно
        [item] = db.get_all_dict_items("brands")
        db.get_dict_values("brands")  # населяет кэш со старым значением

        db.update_dict_value(item["id"], "Apple")

        assert db.get_dict_values("brands") == ["Apple"]

    def test_delete_dict_value_invalidates_cache(self, db):
        db.add_dict_value("brands", "Apple")
        [item] = db.get_all_dict_items("brands")
        db.get_dict_values("brands")  # населяет кэш

        db.delete_dict_value(item["id"])

        assert db.get_dict_values("brands") == []

    def test_different_dict_types_do_not_share_cache_key(self, db):
        db.add_dict_value("brands", "Apple")
        db.add_dict_value("device_types", "Ноутбук")

        assert db.get_dict_values("brands") == ["Apple"]
        assert db.get_dict_values("device_types") == ["Ноутбук"]

    def test_query_cache_ttl_configured_to_roughly_an_hour(self, db):
        """Не проверяет реальное истечение (не хотим тест на минуты) —
        только то, что TTL действительно ~час, а не "без ограничения"."""
        from database.db_core import QUERY_CACHE_TTL_SECONDS

        assert QUERY_CACHE_TTL_SECONDS == 3600
        assert db.core.query_cache.get_stats()["default_ttl_seconds"] == 3600

    def test_refresh_query_cache_clears_everything_and_returns_count(self, db):
        db.add_dict_value("brands", "Apple")
        db.add_dict_value("device_types", "Ноутбук")
        db.get_dict_values("brands")
        db.get_dict_values("device_types")
        assert db.core.query_cache.get_stats()["size"] == 2

        cleared = db.refresh_query_cache()

        assert cleared == 2
        assert db.core.query_cache.get_stats()["size"] == 0
        # Данные по-прежнему доступны — просто перечитаны из БД заново.
        assert db.get_dict_values("brands") == ["Apple"]


class TestClients:
    def test_get_or_create_client_is_idempotent_by_phone(self, db):
        first_id = db.get_or_create_client("Иван Иванов", "+79991234567")
        second_id = db.get_or_create_client("Иван Иванов (дубль имени)", "+79991234567")
        assert first_id == second_id


class TestStructuredQueryGateway:
    """Database.query() — структурированный запрос вместо сырого SQL,
    расширение паттерна calculate(). Белый список таблиц/операторов не даёт
    обратиться к произвольным данным строкой."""

    def test_query_equality_filter(self, db):
        db.add_device(_sample_device(order_number="00001", status="Диагностика"))
        db.add_device(_sample_device(order_number="00002", status="Готов к выдаче"))

        rows = db.query("devices", filters={"status": "Диагностика"})
        assert len(rows) == 1
        assert rows[0]["order_number"] == "00001"

    def test_query_range_operator(self, db):
        db.add_device(_sample_device(order_number="00001", total_price="100"))
        db.add_device(_sample_device(order_number="00002", total_price="5000"))

        rows = db.query("devices", filters={"total_price": {"gte": 1000}})
        assert len(rows) == 1
        assert rows[0]["order_number"] == "00002"

    def test_query_order_by_and_limit(self, db):
        for i in range(5):
            db.add_device(_sample_device(order_number=f"0000{i}", total_price=str(i * 100)))

        # query() возвращает "сырой" model.to_dict() — total_price здесь float
        # колонки ORM-модели, а не отформатированная строка _device_to_row().
        rows = db.query("devices", order_by="total_price", order_desc=True, limit=2)
        assert len(rows) == 2
        assert rows[0]["total_price"] >= rows[1]["total_price"]

    def test_query_unknown_table_raises(self, db):
        with pytest.raises(QueryError):
            db.query("secret_table")

    def test_query_unknown_column_raises(self, db):
        with pytest.raises(QueryError):
            db.query("devices", filters={"not_a_real_column": 1})

    def test_query_unknown_operator_raises(self, db):
        with pytest.raises(QueryError):
            db.query("devices", filters={"total_price": {"regexp": ".*"}})

    def test_query_invalid_limit_raises(self, db):
        with pytest.raises(QueryError):
            db.query("devices", limit=-1)

    def test_get_queryable_schema_lists_columns(self, db):
        schema = db.get_queryable_schema()
        assert "devices" in schema
        assert "order_number" in schema["devices"]
        assert "clients" in schema
        assert "employees" in schema

    def test_query_in_operator(self, db):
        db.add_device(_sample_device(order_number="00001", status="Диагностика"))
        db.add_device(_sample_device(order_number="00002", status="Готов к выдаче"))
        db.add_device(_sample_device(order_number="00003", status="Отказ от ремонта"))

        rows = db.query(
            "devices", filters={"status": {"in": ["Диагностика", "Готов к выдаче"]}}
        )
        assert {r["order_number"] for r in rows} == {"00001", "00002"}

    def test_query_eq_operator_dict_form(self, db):
        """Отдельно от test_query_equality_filter — та проверяет "голый"
        скаляр (bare-scalar shortcut, filters={"status": "X"}), который НЕ
        проходит через _FILTER_OPERATORS вообще. Этот тест бьёт именно
        dict-форму {"status": {"eq": "X"}}, реально вызывающую eq-lambda."""
        db.add_device(_sample_device(order_number="00001", status="Диагностика"))
        db.add_device(_sample_device(order_number="00002", status="Готов к выдаче"))

        rows = db.query("devices", filters={"status": {"eq": "Диагностика"}})
        assert len(rows) == 1
        assert rows[0]["order_number"] == "00001"

    def test_query_ne_operator(self, db):
        db.add_device(_sample_device(order_number="00001", status="Диагностика"))
        db.add_device(_sample_device(order_number="00002", status="Готов к выдаче"))

        rows = db.query("devices", filters={"status": {"ne": "Диагностика"}})
        assert {r["order_number"] for r in rows} == {"00002"}

    def test_query_gt_operator(self, db):
        db.add_device(_sample_device(order_number="00001", total_price="100"))
        db.add_device(_sample_device(order_number="00002", total_price="200"))

        rows = db.query("devices", filters={"total_price": {"gt": 100}})
        assert {r["order_number"] for r in rows} == {"00002"}

    def test_query_lt_operator(self, db):
        db.add_device(_sample_device(order_number="00001", total_price="100"))
        db.add_device(_sample_device(order_number="00002", total_price="200"))

        rows = db.query("devices", filters={"total_price": {"lt": 200}})
        assert {r["order_number"] for r in rows} == {"00001"}

    def test_query_lte_operator(self, db):
        db.add_device(_sample_device(order_number="00001", total_price="100"))
        db.add_device(_sample_device(order_number="00002", total_price="200"))

        rows = db.query("devices", filters={"total_price": {"lte": 100}})
        assert {r["order_number"] for r in rows} == {"00001"}

    def test_query_like_operator(self, db):
        db.add_device(_sample_device(order_number="00001", client_name="Иван Иванов"))
        db.add_device(_sample_device(order_number="00002", client_name="Пётр Петров"))

        rows = db.query("devices", filters={"client_name": {"like": "иванов"}})
        assert {r["order_number"] for r in rows} == {"00001"}


class TestDuplicateConnectionGuard:
    """Ловит случайный обход ядра (второй Database() на тот же файл), а не
    гипотетическую атаку — см. Database.__init__ и обсуждение в сессии."""

    def test_second_database_on_same_path_raises(self, db):
        # db fixture уже "заняла" свой временный путь; конструируем ВТОРОЙ
        # Database с движком на тот же самый файл — должно упасть.
        same_path_engine = SQLiteEngine(
            DatabaseConfig(database=str(db.engine.get_engine().url).replace("sqlite:///", ""))
        )
        with pytest.raises(DuplicateDatabaseConnectionError):
            Database(same_path_engine)
        same_path_engine.dispose()

    def test_different_paths_do_not_collide(self, db):
        fd, other_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            other_engine = SQLiteEngine(DatabaseConfig(database=other_path))
            other_db = Database(other_engine)  # не должно упасть
            assert other_db is not None
            other_engine.dispose()
        finally:
            if os.path.exists(other_path):
                os.remove(other_path)
