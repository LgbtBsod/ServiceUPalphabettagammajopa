#!/usr/bin/env python3

"""Тесты для plugins/orders — третьего плагина, первого шага поэтапного
переноса Device за интерфейс (см. plugins/orders/__init__.py).
SqlAlchemyOrderRepository — тонкий адаптер поверх уже протестированного
Database facade, поэтому эти тесты проверяют делегирование через интерфейс
(тот же результат, что и напрямую через Database), а не заново всю
бизнес-логику Device — она уже покрыта test_device_events.py,
test_device_field_consistency.py и др."""

import os
import tempfile

import pytest

import gui  # noqa: F401 — обход циклического импорта managers/__init__.py
from core.kernel import get_core, reset_core
from database.db_config import DatabaseConfig
from database.engines.sqlite_engine import SQLiteEngine
from database.sqlalchemy_database import Database
from plugins.orders import IOrderRepository
from plugins.orders.repository import SqlAlchemyOrderRepository


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
def repository(db) -> SqlAlchemyOrderRepository:
    return SqlAlchemyOrderRepository(db)


class TestSqlAlchemyOrderRepositoryDelegation:
    def test_add_and_get_device_matches_facade(self, repository, db):
        device_id = repository.add_device({"order_number": "1", "client_name": "Иван"})
        assert device_id is not None
        assert repository.get_device(device_id) == db.get_device(device_id)

    def test_get_next_order_number_increments_through_interface(self, repository):
        first = repository.get_next_order_number()
        second = repository.get_next_order_number()
        assert second == first + 1

    def test_peek_order_number_does_not_increment(self, repository):
        peeked = repository.peek_next_order_number()
        assert repository.peek_next_order_number() == peeked

    def test_update_device_status_through_interface(self, repository):
        device_id = repository.add_device({"order_number": "2", "status": "Диагностика"})
        assert repository.update_device_status(device_id, "Готов к выдаче") is True
        assert repository.get_device(device_id)["status"] == "Готов к выдаче"

    def test_search_and_filters_through_interface(self, repository):
        repository.add_device(
            {
                "order_number": "3",
                "client_name": "Петров",
                "status": "Диагностика",
                "priority": "Обычный",
            }
        )
        found = repository.search_devices("Петров")
        assert len(found) == 1
        filtered = repository.get_devices_by_filters(
            status_filter="Диагностика", priority_filter="Обычный"
        )
        assert len(filtered) == 1

    def test_delete_device_through_interface(self, repository):
        device_id = repository.add_device({"order_number": "4"})
        assert repository.delete_device(device_id) is True
        assert repository.get_device(device_id) is None

    def test_statistics_through_interface(self, repository):
        repository.add_device({"order_number": "5"})
        stats = repository.get_statistics()
        assert stats["total"] == 1
        assert "in_repair" in stats
        assert "ready" in stats
        assert "total_income" in stats

    def test_get_device_by_order_number_and_id(self, repository):
        device_id = repository.add_device({"order_number": "unique-6"})
        assert repository.get_device_id_by_order_number("unique-6") == device_id
        found = repository.get_device_by_order_number("unique-6")
        assert found is not None
        assert found["id"] == device_id

    def test_get_all_devices_excludes_completed_when_requested(self, repository):
        active_id = repository.add_device({"order_number": "7", "status": "Диагностика"})
        repository.add_device({"order_number": "8", "status": "Выдан клиенту"})
        active_only = repository.get_all_devices(include_completed=False)
        ids = {row["id"] for row in active_only}
        assert active_id in ids
        assert len(active_only) == 1


class TestOrdersPluginDiscoveryIntegration:
    """Как test_plugins_employees.py::TestPluginDiscoveryIntegration — но для
    orders: подтверждает, что core.initialize() -> discover('plugins', ...)
    реально грузит OrdersPlugin, а не только существует как класс на
    бумаге."""

    def test_discover_loads_orders_plugin(self, db):
        reset_core()
        core = get_core()
        core.initialize()
        try:
            core.register_service(IOrderRepository, SqlAlchemyOrderRepository(db))

            loaded = core.services.plugin_manager.discover("plugins", context=core)

            assert "orders" in loaded
            api = core.get_module_api("orders")
            assert isinstance(api, IOrderRepository)

            device_id = core.call_module_method(
                "orders", "add_device", {"order_number": "42"}
            )
            assert device_id is not None
        finally:
            reset_core()
