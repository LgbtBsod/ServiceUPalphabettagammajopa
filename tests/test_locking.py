#!/usr/bin/env python3

"""Тесты для database/sqlalchemy_database.py::Database — пессимистичные
блокировки (acquire_lock/refresh_lock/release_lock/get_lock) и оптимистичная
блокировка (update_device()'s _expected_version/version_id)."""

import os
import tempfile
import time

import pytest

from database.db_config import DatabaseConfig
from database.engines.sqlite_engine import SQLiteEngine
from database.sqlalchemy_database import Database, OptimisticLockError


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


def _sample_device(**overrides) -> dict:
    data = {
        "order_number": "00001",
        "receipt_date": "2026-01-01",
        "device_type": "Ноутбук",
        "brand": "Test",
        "model": "TestModel",
        "client_name": "Иван Иванов",
        "phone": "+79991234567",
        "total_price": "1000",
        "status": "Диагностика",
    }
    data.update(overrides)
    return data


class TestPessimisticLock:
    def test_acquire_when_free_succeeds(self, db):
        result = db.acquire_lock("device", 1, "emp:1", "Иван Иванов", ttl_seconds=300)
        assert result["ok"] is True
        assert result["holder_key"] == "emp:1"

    def test_acquire_by_same_holder_is_idempotent(self, db):
        db.acquire_lock("device", 1, "emp:1", "Иван Иванов", ttl_seconds=300)
        result = db.acquire_lock("device", 1, "emp:1", "Иван Иванов", ttl_seconds=300)
        assert result["ok"] is True

    def test_acquire_by_other_holder_fails_while_fresh(self, db):
        db.acquire_lock("device", 1, "emp:1", "Иван Иванов", ttl_seconds=300)
        result = db.acquire_lock("device", 1, "emp:2", "Пётр Петров", ttl_seconds=300)
        assert result["ok"] is False
        assert result["holder_key"] == "emp:1"
        assert result["holder_label"] == "Иван Иванов"

    def test_acquire_steals_stale_lock(self, db):
        # ttl_seconds=0 -> любая блокировка мгновенно "протухшая"
        db.acquire_lock("device", 1, "emp:1", "Иван Иванов", ttl_seconds=0)
        time.sleep(0.01)
        result = db.acquire_lock("device", 1, "emp:2", "Пётр Петров", ttl_seconds=0)
        assert result["ok"] is True
        assert result["holder_key"] == "emp:2"

    def test_refresh_updates_heartbeat_for_own_lock(self, db):
        db.acquire_lock("device", 1, "emp:1", "Иван Иванов", ttl_seconds=300)
        assert db.refresh_lock("device", 1, "emp:1") is True

    def test_refresh_fails_for_non_holder(self, db):
        db.acquire_lock("device", 1, "emp:1", "Иван Иванов", ttl_seconds=300)
        assert db.refresh_lock("device", 1, "emp:2") is False

    def test_release_removes_own_lock(self, db):
        db.acquire_lock("device", 1, "emp:1", "Иван Иванов", ttl_seconds=300)
        db.release_lock("device", 1, "emp:1")
        assert db.get_lock("device", 1) is None

    def test_release_does_not_remove_others_lock(self, db):
        db.acquire_lock("device", 1, "emp:1", "Иван Иванов", ttl_seconds=300)
        db.release_lock("device", 1, "emp:2")  # чужой holder_key — no-op
        assert db.get_lock("device", 1) is not None

    def test_get_lock_returns_none_when_free(self, db):
        assert db.get_lock("device", 1) is None

    def test_locks_are_scoped_per_object_id(self, db):
        db.acquire_lock("device", 1, "emp:1", "Иван Иванов", ttl_seconds=300)
        result = db.acquire_lock("device", 2, "emp:2", "Пётр Петров", ttl_seconds=300)
        assert result["ok"] is True


class TestOptimisticLock:
    def test_new_device_starts_at_version_1(self, db):
        device_id = db.add_device(_sample_device())
        device = db.get_device(device_id)
        assert device["version"] == 1

    def test_update_bumps_version_on_real_change(self, db):
        device_id = db.add_device(_sample_device())
        db.update_device(device_id, _sample_device(status="Готов к выдаче"))
        device = db.get_device(device_id)
        assert device["version"] == 2

    def test_noop_update_does_not_bump_version(self, db):
        device_id = db.add_device(_sample_device())
        db.update_device(device_id, _sample_device())  # те же данные — no-op
        device = db.get_device(device_id)
        assert device["version"] == 1

    def test_update_with_correct_expected_version_succeeds(self, db):
        device_id = db.add_device(_sample_device())
        payload = _sample_device(status="Готов к выдаче")
        payload["_expected_version"] = 1
        assert db.update_device(device_id, payload) is True

    def test_update_with_stale_expected_version_raises(self, db):
        device_id = db.add_device(_sample_device())
        # Кто-то другой уже сохранил -> версия в БД теперь 2
        db.update_device(device_id, _sample_device(status="Готов к выдаче"))

        payload = _sample_device(notes="моя правка")
        payload["_expected_version"] = 1  # то, что "я" прочитал при открытии формы
        with pytest.raises(OptimisticLockError):
            db.update_device(device_id, payload)

    def test_update_without_expected_version_skips_check(self, db):
        """Обратная совместимость: старый вызывающий код, не знающий про
        версии, не должен внезапно начать падать."""
        device_id = db.add_device(_sample_device())
        db.update_device(device_id, _sample_device(status="Готов к выдаче"))
        # НЕ передаём _expected_version вообще
        assert db.update_device(device_id, _sample_device(notes="ещё правка")) is True

    def test_noop_update_with_stale_expected_version_does_not_raise(self, db):
        """Ресейв без реальных изменений — не конфликт, даже если версия
        успела уйти вперёд (см. update_device() docstring)."""
        device_id = db.add_device(_sample_device())
        db.update_device(device_id, _sample_device(status="Готов к выдаче"))  # version -> 2

        payload = _sample_device(status="Готов к выдаче")  # совпадает с текущим состоянием
        payload["_expected_version"] = 1
        assert db.update_device(device_id, payload) is True
