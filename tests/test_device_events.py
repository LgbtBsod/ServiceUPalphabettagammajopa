#!/usr/bin/env python3

"""Тесты для domain/events.py::DeviceStatusChangedEvent — первый реальный
потребитель core/events/event_bus.py (см. AUDIT_REPORT_v25.md: EventBus был
полностью построен и зарегистрирован в DI, но ни один код нигде его не
publish()/subscribe()). Database.update_device()/update_device_status()
публикуют событие; managers.integrations.IntegrationManager.
on_device_status_changed() — подписчик, вызывающий notify_order_ready()
только на генуинный переход в "Готов к выдаче"."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

import gui  # noqa: F401 — обход циклического импорта managers/__init__.py
from core.kernel import get_core, reset_core
from database.db_config import DatabaseConfig
from database.engines.sqlite_engine import SQLiteEngine
from database.sqlalchemy_database import Database
from domain.constants import STATUS_READY
from domain.events import DeviceStatusChangedEvent
from managers.integrations import IntegrationManager


@pytest.fixture
def db():
    """Database созданный НАПРЯМУЮ, без core.initialize() — тот же
    fixture, что и в остальных тестах фасада. Основной контракт этого
    файла: публикация событий не должна падать/мешать, когда ядро не
    инициализировано (см. TestPublishWithoutCore)."""
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
        "client_name": "Иван Иванов",
        "phone": "+79991234567",
        "total_price": "1000",
        "status": "Диагностика",
    }
    data.update(overrides)
    return data


class TestPublishWithoutCore:
    """Database() в этих тестах создан напрямую (как и во всех остальных
    facade-тестах) — core.initialize() не вызывался. Публикация события
    должна тихо no-op'нуть, а не бросить исключение."""

    def test_update_device_status_change_does_not_raise(self, db):
        device_id = db.add_device(_sample_device())
        assert db.update_device(device_id, _sample_device(status="Готов к выдаче")) is True

    def test_update_device_status_quick_path_does_not_raise(self, db):
        device_id = db.add_device(_sample_device())
        assert db.update_device_status(device_id, "Готов к выдаче") is True


class TestEventPublishedThroughRealKernel:
    """Сквозной путь: core.initialize() -> core.register_module('db_access', ...)
    -> Database.update_device()/update_device_status() -> core.publish(...)
    -> подписчик получает событие. Ровно то, что происходит в реальном
    приложении (bootstrap.py)."""

    def test_update_device_publishes_event_on_real_status_change(self, db):
        reset_core()
        core = get_core()
        core.initialize()
        received = []
        try:
            core.register_module("db_access", db, Database, api=db)
            core.subscribe(DeviceStatusChangedEvent, received.append)

            device_id = db.add_device(_sample_device(status="Диагностика"))
            db.update_device(device_id, _sample_device(status="Готов к выдаче"))

            assert len(received) == 1
            event = received[0]
            assert event.device_id == device_id
            assert event.old_status == "Диагностика"
            assert event.new_status == "Готов к выдаче"
            assert event.device_data["client_name"] == "Иван Иванов"
        finally:
            reset_core()

    def test_noop_status_resubmit_does_not_publish(self, db):
        reset_core()
        core = get_core()
        core.initialize()
        received = []
        try:
            core.register_module("db_access", db, Database, api=db)
            core.subscribe(DeviceStatusChangedEvent, received.append)

            device_id = db.add_device(_sample_device(status="Диагностика"))
            db.update_device(device_id, _sample_device(status="Диагностика"))  # тот же статус

            assert received == []
        finally:
            reset_core()

    def test_update_device_status_quick_path_publishes_event(self, db):
        reset_core()
        core = get_core()
        core.initialize()
        received = []
        try:
            core.register_module("db_access", db, Database, api=db)
            core.subscribe(DeviceStatusChangedEvent, received.append)

            device_id = db.add_device(_sample_device(status="Диагностика"))
            db.update_device_status(device_id, "Готов к выдаче")

            assert len(received) == 1
            assert received[0].new_status == "Готов к выдаче"
        finally:
            reset_core()


class TestIntegrationManagerSubscriber:
    """IntegrationManager.on_device_status_changed() — реальный подписчик,
    зарегистрированный в bootstrap.py."""

    def _event(self, old_status: str, new_status: str) -> DeviceStatusChangedEvent:
        return DeviceStatusChangedEvent(
            event_type="DeviceStatusChangedEvent",
            device_id=1,
            old_status=old_status,
            new_status=new_status,
            device_data={
                "client_name": "Иван Иванов",
                "phone": "+79991234567",
                "order_number": "00001",
            },
        )

    def test_notifies_on_genuine_transition_to_ready(self):
        mgr = IntegrationManager(settings=MagicMock())
        with patch.object(mgr, "notify_order_ready") as mock_notify:
            mgr.on_device_status_changed(self._event("Диагностика", STATUS_READY))
            mock_notify.assert_called_once()

    def test_does_not_notify_on_other_transitions(self):
        mgr = IntegrationManager(settings=MagicMock())
        with patch.object(mgr, "notify_order_ready") as mock_notify:
            mgr.on_device_status_changed(self._event("Диагностика", "В ремонте"))
            mock_notify.assert_not_called()

    def test_does_not_renotify_when_already_ready(self):
        """Ресейв формы уже готового заказа (статус не менялся) не должен
        слать повторное уведомление."""
        mgr = IntegrationManager(settings=MagicMock())
        with patch.object(mgr, "notify_order_ready") as mock_notify:
            mgr.on_device_status_changed(self._event(STATUS_READY, STATUS_READY))
            mock_notify.assert_not_called()

    def test_handler_exception_does_not_propagate(self):
        """EventBus сам ловит исключения обработчиков (см.
        core/events/event_bus.py::publish), но обработчик тоже не должен
        падать наружу при сбое notify_order_ready — на всякий случай."""
        mgr = IntegrationManager(settings=MagicMock())
        with patch.object(mgr, "notify_order_ready", side_effect=RuntimeError("boom")):
            mgr.on_device_status_changed(self._event("Диагностика", STATUS_READY))  # не бросает
