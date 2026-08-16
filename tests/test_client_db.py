#!/usr/bin/env python3

"""Тесты для database/client_db.py::ClientDatabaseManager — теперь работает
ИСКЛЮЧИТЕЛЬНО через основную БД, без dual-write в отдельные .db-файлы на
клиента, см. AUDIT_REPORT_v21.md ("одна БД, разные таблицы")."""

import os
import tempfile

import pytest

from database.client_db import ClientDatabaseManager
from database.db_config import DatabaseConfig
from database.engines.sqlite_engine import SQLiteEngine
from database.sqlalchemy_database import Database


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = SQLiteEngine(DatabaseConfig(database=path))
    database = Database(engine)
    yield database
    engine.dispose()
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def client_db(db) -> ClientDatabaseManager:
    return ClientDatabaseManager(main_db=db)


def _sample_device(**overrides) -> dict:
    data = {
        "order_number": "00001",
        "receipt_date": "2026-01-01",
        "device_type": "Ноутбук",
        "client_name": "Иван Иванов",
        "phone": "+79991234567",
        "total_price": "1000",
        "status": "Диагностика",
    }
    data.update(overrides)
    return data


class TestClientDatabaseManager:
    def test_add_repair_creates_client_and_history(self, db, client_db):
        ok = client_db.add_repair_to_client_history(
            "Иван Иванов", "+79991234567", _sample_device()
        )
        assert ok is True

        history = client_db.get_client_history("Иван Иванов", "+79991234567")
        assert len(history) == 1
        assert history[0]["order_number"] == "00001"

    def test_add_repair_without_name_or_phone_fails_gracefully(self, client_db):
        assert client_db.add_repair_to_client_history("", "", _sample_device()) is False

    def test_update_repair_upserts_same_order(self, db, client_db):
        client_db.add_repair_to_client_history(
            "Иван Иванов", "+79991234567", _sample_device(status="Диагностика")
        )
        client_db.update_repair_in_history(
            "Иван Иванов",
            "+79991234567",
            "00001",
            _sample_device(status="Готов к выдаче"),
        )
        history = client_db.get_client_history("Иван Иванов", "+79991234567")
        # Апдейт, а не вторая запись
        assert len(history) == 1
        assert history[0]["status"] == "Готов к выдаче"

    def test_get_client_stats_reflects_history(self, db, client_db):
        client_db.add_repair_to_client_history(
            "Иван Иванов",
            "+79991234567",
            _sample_device(order_number="00001", status="Выдан клиенту", total_price="1000"),
        )
        stats = client_db.get_client_stats("Иван Иванов", "+79991234567")
        assert stats["total_orders"] >= 1

    def test_get_client_stats_unknown_client_returns_empty_defaults(self, client_db):
        stats = client_db.get_client_stats("Нет Такого", "+70000000000")
        assert stats["total_orders"] == 0

    def test_no_main_db_reference_degrades_gracefully(self):
        orphan = ClientDatabaseManager(main_db=None)
        assert orphan.add_repair_to_client_history("A", "B", _sample_device()) is False
        assert orphan.get_client_history("A", "B") == []
        assert orphan.get_client_stats("A", "B")["total_orders"] == 0

    def test_no_separate_client_db_files_are_created(self, db, client_db, tmp_path):
        """Регрессия dual-write: раньше add_repair_to_client_history создавал
        файл в CLIENTS_DB_DIR — теперь пишет только в основную БД."""
        from config import CLIENTS_DB_DIR

        before = set(os.listdir(CLIENTS_DB_DIR)) if os.path.exists(CLIENTS_DB_DIR) else set()
        client_db.add_repair_to_client_history(
            "Уникальный Клиент Для Теста", "+79995554433", _sample_device()
        )
        after = set(os.listdir(CLIENTS_DB_DIR)) if os.path.exists(CLIENTS_DB_DIR) else set()
        assert after == before
