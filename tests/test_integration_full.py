#!/usr/bin/env python3
"""Integration test — проверка работоспособности приложения через ядро и БД.

Раньше каждый тест сам try/except'ил всё и возвращал bool/tuple вместо assert
— pytest не проваливает тест на "return False" (только предупреждает про
PytestReturnNotNoneWarning), поэтому 4 из 12 тестов реально были сломаны
(add_device() падал на FOREIGN KEY constraint failed из-за created_by_id=1
на пустой БД без такого сотрудника) и годами показывали зелёным. Теперь —
assert (пусть пилот проваливается) и без created_by_id/updated_by_id в
тестовых данных (это необязательный аудиторский FK, не предмет теста).
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from core.kernel import ServiceUpCore, reset_core


@pytest.fixture(scope="function")
def core_instance():
    """Создаёт и инициализирует ядро для каждого теста."""
    from bootstrap import initialize_kernel

    reset_core()
    core = initialize_kernel()
    yield core
    core.shutdown()
    reset_core()


@pytest.fixture(scope="function")
def db(core_instance: ServiceUpCore):
    """Получает экземпляр БД из ядра для каждого теста."""
    db_instance = core_instance.get_db_access()
    if db_instance is None:
        raise RuntimeError("DB Access module not registered in core")
    yield db_instance


@pytest.fixture(scope="function")
def isolated_db():
    """Создаёт изолированный экземпляр БД (свой временный файл) для тестов,
    которым не нужно ядро целиком — только БД."""
    from database.db_config import DatabaseConfig, DatabaseType
    from database.engines.sqlite_engine import SQLiteEngine
    from database.sqlalchemy_database import Database

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name

    config = DatabaseConfig(db_type=DatabaseType.SQLITE, database=tmp_path)
    engine = SQLiteEngine(config)
    db = Database(engine)
    try:
        yield db
    finally:
        db.close()
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@pytest.fixture(scope="function")
def client_id(db) -> int:
    """Создаёт тестового клиента и возвращает его ID."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return db.get_or_create_client(
        name=f"Тестовый Клиент {timestamp}",
        phone=f"+7999{timestamp[-6:]}0001",
        status="Новый",
    )


def _device_payload(isolated_db, **overrides) -> dict:
    """Базовые поля заказа + произвольные переопределения.

    Без created_by_id/updated_by_id: FK на employees.id, которого на чистой
    isolated_db нет — INSERT падал бы FOREIGN KEY constraint failed. Оба поля
    nullable, аудиторский трейл не входит в предмет этих тестов.
    """
    order_number = isolated_db.get_next_order_number()
    payload = {
        "order_number": str(order_number),
        "receipt_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "completion_date": "",
        "device_type": "Смартфон",
        "brand": "Apple",
        "model": "iPhone 13",
        "serial_number": f"SN{order_number}TEST",
        "defect": "Не включается, разбит экран",
        "appearance": "Царапины на корпусе",
        "completeness": "Только телефон",
        "work_items_json": '[{"name": "Диагностика", "price": "500"}]',
        "client_name": f"Клиент {order_number}",
        "client_status": "Новый",
        "phone": f"+7999{order_number}0000",
        "total_price": "5000",
        "prepayment": "1000",
        "status": "Диагностика",
        "priority": "Обычный",
        "engineer": "Тестировщик",
        "warranty": "30 дней",
        "notes": "Тестовый заказ",
        "photos": "[]",
        "expense": "0",
    }
    payload.update(overrides)
    return payload


def test_database_initialization(core_instance: ServiceUpCore) -> None:
    """Ядро отдаёт доступ к БД, и счётчик номеров заказов инициализирован."""
    db = core_instance.get_db_access()
    order_number = db.peek_next_order_number()
    assert isinstance(order_number, int)


def test_create_client(isolated_db) -> None:
    """Создание клиента возвращает валидный положительный ID."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    client_id = isolated_db.get_or_create_client(
        name=f"Тестовый Клиент {timestamp}",
        phone=f"+7999{timestamp[-6:]}0001",
        status="Новый",
    )
    assert client_id is not None and client_id > 0


def test_create_order(isolated_db, client_id: int) -> None:
    """Создание заказа (устройства) возвращает валидный ID."""
    order_number = isolated_db.get_next_order_number()
    device_data = _device_payload(isolated_db, order_number=str(order_number))
    device_id = isolated_db.add_device(device_data)
    assert device_id is not None and device_id > 0


def test_update_order(isolated_db, client_id: int) -> None:
    """Обновление заказа реально меняет статус и цену в БД."""
    device_id = isolated_db.add_device(_device_payload(isolated_db))

    update_data = {
        "defect": "Не включается, разбит экран, не работает FaceID",
        "total_price": "7500",
        "status": "В работе",
        "work_items_json": (
            '[{"name": "Диагностика", "price": "500"}, '
            '{"name": "Замена экрана", "price": "2500"}]'
        ),
        "notes": "Тестовый заказ - обновлено",
    }
    assert isolated_db.update_device(device_id, update_data)

    devices = isolated_db.get_all_devices()
    found_device = next((d for d in devices if d["id"] == device_id), None)
    assert found_device is not None
    assert found_device.get("status") == "В работе"
    assert found_device.get("total_price") == "7500"


def test_search_and_filter(isolated_db, client_id: int) -> None:
    """Поиск по тексту и фильтр по статусу находят только что созданный заказ."""
    device_id = isolated_db.add_device(_device_payload(isolated_db, status="В работе"))

    all_devices = isolated_db.get_all_devices()
    assert len(all_devices) > 0

    found_devices = isolated_db.search_devices(search_text=str(device_id))
    assert len(found_devices) > 0

    devices_in_work = isolated_db.get_devices_by_filters(
        status_filter="В работе",
        priority_filter="Все",
        include_completed=True,
    )
    assert len(devices_in_work) > 0


def test_change_status_to_ready(isolated_db, client_id: int) -> None:
    """Смена статуса на 'Готов' сохраняется в БД."""
    device_id = isolated_db.add_device(_device_payload(isolated_db, status="Диагностика"))

    update_data = {
        "status": "Готов",
        "total_price": "7500",
        "work_items_json": (
            '[{"name": "Диагностика", "price": "500"}, '
            '{"name": "Замена экрана", "price": "2500"}]'
        ),
        "notes": "Ремонт завершен",
    }
    assert isolated_db.update_device(device_id, update_data)

    devices = isolated_db.get_all_devices()
    found_device = next((d for d in devices if d["id"] == device_id), None)
    assert found_device is not None
    assert found_device.get("status") == "Готов"


def test_client_history(isolated_db, client_id: int) -> None:
    """История клиента доступна как список (пусть и с учётом текущей
    реализации сопоставления — см. отдельный аудит clients_mixin)."""
    device_data = _device_payload(
        isolated_db,
        receipt_date=datetime.now().strftime("%Y-%m-%d"),
        brand="Samsung",
        model="Galaxy S21",
        defect="Разбит экран",
        status="В работе",
    )
    device_id = isolated_db.add_device(device_data)
    assert device_id is not None

    isolated_db.add_to_repair_history_main(client_id, device_id, device_data)

    history = isolated_db.get_client_history_main(
        client_name="Тестовый Клиент", client_phone="+7999"
    )
    assert isinstance(history, list)


def test_statistics(isolated_db, client_id: int) -> None:
    """Статистика клиента возвращается как словарь."""
    stats = isolated_db.get_client_stats_main(
        client_name="Тестовый Клиент", client_phone="+7999"
    )
    assert isinstance(stats, dict)


def test_kernel_module_registration(core_instance: ServiceUpCore) -> None:
    """Модуль, зарегистрированный вручную, доступен через API ядра."""

    class MockModule:
        def get_info(self):
            return {"name": "TestModule", "version": "1.0"}

    mock_instance = MockModule()
    core_instance.register_module(
        name="test_module",
        module_instance=mock_instance,
        module_type=MockModule,
        api=mock_instance,
    )

    api = core_instance.get_module_api("test_module")
    assert api is not None
    assert api.get_info()["name"] == "TestModule"


def test_kernel_call_module_method(core_instance: ServiceUpCore) -> None:
    """call_module_method вызывает метод модуля и возвращает его результат.

    Раньше зависел от test_kernel_module_registration, зарегистрировавшего
    "test_module" в СВОЁМ экземпляре core_instance — но core_instance
    function-scoped (новый на каждый тест), так что "test_module" в этом
    тесте никогда не существовал; call_module_method падал, исключение
    глоталось try/except, тест "проходил" с passed=False. Регистрируем
    модуль здесь же, самостоятельно.
    """

    class MockModule:
        def process(self, data):
            return {"processed": True, "data": data}

    core_instance.register_module(
        name="test_module",
        module_instance=MockModule(),
        module_type=MockModule,
        api=MockModule(),
    )

    result = core_instance.call_module_method("test_module", "process", {"test": "data"})
    assert result is not None
    assert result.get("processed") is True
    assert result.get("data") == {"test": "data"}


def test_cache_operations(core_instance: ServiceUpCore) -> None:
    """set/get/delete кэша ядра работают согласованно."""
    cache_key = "test_key"
    cache_value = {"data": "test_value", "timestamp": time.time()}

    core_instance.cache_set(cache_key, cache_value, ttl_seconds=60)
    assert core_instance.cache_get(cache_key) == cache_value
    assert core_instance.cache_delete(cache_key) is True
    assert core_instance.cache_get(cache_key) is None


def test_event_bus(core_instance: ServiceUpCore) -> None:
    """publish() доставляет событие ровно одному подписанному обработчику."""
    from core.events.event_bus import Event

    event_received = []

    def handler(event):
        event_received.append(event)

    core_instance.subscribe("TestEvent", handler)
    core_instance.publish(Event(event_type="TestEvent", data={"message": "test"}))
    core_instance.unsubscribe("TestEvent", handler)

    assert len(event_received) == 1
