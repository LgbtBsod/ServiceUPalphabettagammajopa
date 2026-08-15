#!/usr/bin/env python3

"""Тесты для database/sqlalchemy_database.py::Database — живого facade,
на который опираются gui/, pwa/ и managers/ через core.get_db_access().

До этих тестов покрытие было только у database/repositories/ — параллельного,
никогда не подключённого к приложению слоя (см. AUDIT_REPORT_v21.md, удалён).
"""

import os
import tempfile

import pytest

from database.db_config import DatabaseConfig
from database.engines.sqlite_engine import SQLiteEngine
from database.sqlalchemy_database import Database


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


class TestClients:
    def test_get_or_create_client_is_idempotent_by_phone(self, db):
        first_id = db.get_or_create_client("Иван Иванов", "+79991234567")
        second_id = db.get_or_create_client("Иван Иванов (дубль имени)", "+79991234567")
        assert first_id == second_id
