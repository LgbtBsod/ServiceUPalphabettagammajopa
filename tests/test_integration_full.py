#!/usr/bin/env python3
"""Integration test — проверка работоспособности приложения через ядро и БД."""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from core.kernel import ServiceUpCore, get_core, reset_core


@pytest.fixture(scope="function")
def core_instance():
    """Создает и инициализирует ядро для каждого теста."""
    from bootstrap import initialize_kernel
    
    # Сбрасываем глобальное ядро перед каждым тестом
    reset_core()
    
    # Инициализируем новое ядро через bootstrap
    core = initialize_kernel()
    yield core
    core.shutdown()
    
    # Сбрасываем после теста
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
    """Создает изолированный экземпляр БД для тестов, требующих отдельное соединение."""
    from database.sqlalchemy_database import Database
    from database.db_config import DatabaseConfig, DatabaseType
    from database.engines.sqlite_engine import SQLiteEngine
    import tempfile
    import os
    
    # Создаем временную БД для изоляции теста
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        config = DatabaseConfig(db_type=DatabaseType.SQLITE, database=tmp_path)
        engine = SQLiteEngine(config)
        db = Database(engine)
        yield db
    finally:
        db.close()
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def log_test(name: str, passed: bool, details: str = "") -> None:
    """Вывод результата теста."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"\n{status}: {name}")
    if details:
        print(f"   └─ {details}")


@pytest.fixture(scope="function")
def client_id(db) -> int:
    """Создает тестового клиента и возвращает его ID."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    client_name = f"Тестовый Клиент {timestamp}"
    client_phone = f"+7999{timestamp[-6:]}0001"
    
    cid = db.get_or_create_client(
        name=client_name,
        phone=client_phone,
        status="Новый"
    )
    return cid


def test_database_initialization(core_instance: ServiceUpCore) -> bool:
    """Тест 1: Инициализация БД через ядро."""
    try:
        db = core_instance.get_db_access()
        order_number = db.peek_next_order_number()
        passed = order_number is not None and isinstance(order_number, int)
        log_test("Инициализация БД", passed, f"Следующий номер заказа: {order_number}")
        return passed
    except Exception as e:
        log_test("Инициализация БД", False, f"Ошибка: {e}")
        return False


def test_create_client(isolated_db) -> tuple[bool, int | None]:
    """Тест 2: Создание клиента."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        client_name = f"Тестовый Клиент {timestamp}"
        client_phone = f"+7999{timestamp[-6:]}0001"
        
        client_id = isolated_db.get_or_create_client(
            name=client_name,
            phone=client_phone,
            status="Новый"
        )
        
        passed = client_id is not None and client_id > 0
        log_test("Создание клиента", passed, 
                f"ID={client_id}, Name={client_name}, Phone={client_phone}")
        return passed, client_id
    except Exception as e:
        log_test("Создание клиента", False, f"Ошибка: {e}")
        return False, None


def test_create_order(isolated_db, client_id: int) -> tuple[bool, int | None]:
    """Тест 3: Создание заказа (устройства)."""
    try:
        order_number = isolated_db.get_next_order_number()
        
        device_data = {
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
            "created_by_id": 1,
        }
        
        device_id = isolated_db.add_device(device_data)
        
        passed = device_id is not None and device_id > 0
        log_test("Создание заказа", passed,
                f"Device ID={device_id}, Order #{order_number}")
        return passed, device_id
    except Exception as e:
        log_test("Создание заказа", False, f"Ошибка: {e}")
        return False, None


def test_update_order(isolated_db, client_id: int) -> bool:
    """Тест 4: Обновление данных заказа."""
    try:
        # Сначала создаем заказ
        order_number = isolated_db.get_next_order_number()
        device_data = {
            "order_number": str(order_number),
            "receipt_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "completion_date": "",
            "device_type": "Смартфон",
            "brand": "Apple",
            "model": "iPhone 13",
            "serial_number": f"SN{order_number}TEST",
            "defect": "Не включается",
            "appearance": "Царапины",
            "completeness": "Только телефон",
            "work_items_json": '[]',
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
            "created_by_id": 1,
        }
        device_id = isolated_db.add_device(device_data)
        
        # Теперь обновляем
        update_data = {
            "defect": "Не включается, разбит экран, не работает FaceID",
            "total_price": "7500",
            "status": "В работе",
            "work_items_json": '[{"name": "Диагностика", "price": "500"}, {"name": "Замена экрана", "price": "2500"}]',
            "notes": "Тестовый заказ - обновлено",
            "updated_by_id": 1,
        }
        
        success = isolated_db.update_device(device_id, update_data)
        devices = isolated_db.get_all_devices()
        found_device = next((d for d in devices if d["id"] == device_id), None)
        passed = success and found_device is not None
        
        if passed:
            log_test("Обновление заказа", True,
                    f"Status={found_device.get('status')}, Price={found_device.get('total_price')}")
        else:
            log_test("Обновление заказа", False, "Данные не обновились")
        
        return passed
    except Exception as e:
        log_test("Обновление заказа", False, f"Ошибка: {e}")
        return False


def test_search_and_filter(isolated_db, client_id: int) -> bool:
    """Тест 5: Поиск и фильтрация заказов."""
    try:
        # Создаем заказ для поиска
        order_number = isolated_db.get_next_order_number()
        device_data = {
            "order_number": str(order_number),
            "receipt_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "completion_date": "",
            "device_type": "Смартфон",
            "brand": "Apple",
            "model": "iPhone 13",
            "serial_number": f"SN{order_number}TEST",
            "defect": "Не включается",
            "status": "В работе",
            "total_price": "5000",
            "prepayment": "1000",
            "priority": "Обычный",
            "engineer": "Тестировщик",
            "warranty": "30 дней",
            "notes": "Тестовый заказ",
            "photos": "[]",
            "expense": "0",
            "created_by_id": 1,
        }
        device_id = isolated_db.add_device(device_data)
        
        all_devices = isolated_db.get_all_devices()
        has_devices = len(all_devices) > 0
        
        found_devices = isolated_db.search_devices(search_text=str(device_id))
        found_by_search = len(found_devices) > 0
        
        devices_in_work = isolated_db.get_devices_by_filters(
            status_filter="В работе",
            priority_filter="Все",
            include_completed=True,
        )
        found_by_status = len(devices_in_work) > 0
        
        passed = found_by_search and found_by_status and has_devices
        log_test("Поиск и фильтрация", passed,
                f"Найдено по поиску: {found_by_search}, По статусу: {found_by_status}, Всего: {len(all_devices)}")
        return passed
    except Exception as e:
        log_test("Поиск и фильтрация", False, f"Ошибка: {e}")
        return False


def test_change_status_to_ready(isolated_db, client_id: int) -> bool:
    """Тест 6: Изменение статуса на 'Готов'."""
    try:
        # Создаем заказ
        order_number = isolated_db.get_next_order_number()
        device_data = {
            "order_number": str(order_number),
            "receipt_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "completion_date": "",
            "device_type": "Смартфон",
            "brand": "Apple",
            "model": "iPhone 13",
            "serial_number": f"SN{order_number}TEST",
            "defect": "Не включается",
            "status": "Диагностика",
            "total_price": "5000",
            "prepayment": "1000",
            "priority": "Обычный",
            "engineer": "Тестировщик",
            "warranty": "30 дней",
            "notes": "Тестовый заказ",
            "photos": "[]",
            "expense": "0",
            "created_by_id": 1,
        }
        device_id = isolated_db.add_device(device_data)
        
        # Меняем статус на Готов
        update_data = {
            "status": "Готов",
            "total_price": "7500",
            "work_items_json": '[{"name": "Диагностика", "price": "500"}, {"name": "Замена экрана", "price": "2500"}]',
            "notes": "Ремонт завершен",
            "updated_by_id": 1,
        }
        
        success = isolated_db.update_device(device_id, update_data)
        devices = isolated_db.get_all_devices()
        found_device = next((d for d in devices if d["id"] == device_id), None)
        passed = success and found_device is not None and found_device.get("status") == "Готов"
        
        log_test("Изменение статуса на 'Готов'", passed,
                f"Текущий статус: {found_device.get('status') if passed else 'N/A'}")
        return passed
    except Exception as e:
        log_test("Изменение статуса на 'Готов'", False, f"Ошибка: {e}")
        return False


def test_client_history(isolated_db, client_id: int) -> bool:
    """Тест 7: Проверка истории клиента."""
    try:
        # Создаем заказ
        order_number = isolated_db.get_next_order_number()
        device_data = {
            "order_number": str(order_number),
            "receipt_date": datetime.now().strftime("%Y-%m-%d"),
            "completion_date": "",
            "device_type": "Смартфон",
            "brand": "Samsung",
            "model": "Galaxy S21",
            "defect": "Разбит экран",
            "status": "В работе",
            "total_price": "5000",
        }
        device_id = isolated_db.add_device(device_data)
        
        isolated_db.add_to_repair_history_main(client_id, device_id, device_data)
        
        history = isolated_db.get_client_history_main(
            client_name="Тестовый Клиент",
            client_phone="+7999"
        )
        
        passed = isinstance(history, list)
        log_test("История клиента", passed,
                f"Записей в истории: {len(history)}")
        return passed
    except Exception as e:
        log_test("История клиента", False, f"Ошибка: {e}")
        return False


def test_statistics(isolated_db, client_id: int) -> bool:
    """Тест 8: Статистика клиента."""
    try:
        stats = isolated_db.get_client_stats_main(
            client_name="Тестовый Клиент",
            client_phone="+7999"
        )
        
        passed = isinstance(stats, dict)
        log_test("Статистика клиента", passed,
                f"Полей в статистике: {len(stats)}")
        return passed
    except Exception as e:
        log_test("Статистика клиента", False, f"Ошибка: {e}")
        return False


def test_kernel_module_registration(core_instance: ServiceUpCore) -> bool:
    """Тест 9: Регистрация модулей через ядро."""
    try:
        class MockModule:
            def get_info(self):
                return {"name": "TestModule", "version": "1.0"}
            
            def process(self, data):
                return {"processed": True, "data": data}
        
        mock_instance = MockModule()
        
        core_instance.register_module(
            name="test_module",
            module_instance=mock_instance,
            module_type=MockModule,
            api=mock_instance,
        )
        
        api = core_instance.get_module_api("test_module")
        info = api.get_info() if api else {}
        
        passed = api is not None and info.get("name") == "TestModule"
        log_test("Регистрация модулей через ядро", passed,
                f"Модуль: {info.get('name')}, Версия: {info.get('version')}")
        return passed
    except Exception as e:
        log_test("Регистрация модулей через ядро", False, f"Ошибка: {e}")
        return False


def test_kernel_call_module_method(core_instance: ServiceUpCore) -> bool:
    """Тест 10: Вызов методов модулей через ядро."""
    try:
        result = core_instance.call_module_method(
            "test_module",
            "process",
            {"test": "data"},
        )
        
        passed = result is not None and result.get("processed") is True
        log_test("Вызов методов через ядро", passed,
                f"Результат: {result}")
        return passed
    except Exception as e:
        log_test("Вызов методов через ядро", False, f"Ошибка: {e}")
        return False


def test_cache_operations(core_instance: ServiceUpCore) -> bool:
    """Тест 11: Операции с кэшем ядра."""
    try:
        cache_key = "test_key"
        cache_value = {"data": "test_value", "timestamp": time.time()}
        
        core_instance.cache_set(cache_key, cache_value, ttl_seconds=60)
        cached = core_instance.cache_get(cache_key)
        deleted = core_instance.cache_delete(cache_key)
        
        passed = cached == cache_value and deleted
        log_test("Операции с кэшем", passed,
                f"Записано и прочитано: {cached is not None}, Удалено: {deleted}")
        return passed
    except Exception as e:
        log_test("Операции с кэшем", False, f"Ошибка: {e}")
        return False


def test_event_bus(core_instance: ServiceUpCore) -> bool:
    """Тест 12: Шина событий."""
    try:
        event_received = []
        
        def handler(event):
            event_received.append(event)
        
        core_instance.subscribe("TestEvent", handler)
        
        from core.events.event_bus import Event
        test_event = Event(event_type="TestEvent", data={"message": "test"})
        core_instance.publish(test_event)
        
        core_instance.unsubscribe("TestEvent", handler)
        
        passed = len(event_received) == 1
        log_test("Шина событий", passed,
                f"Событий получено: {len(event_received)}")
        return passed
    except Exception as e:
        log_test("Шина событий", False, f"Ошибка: {e}")
        return False
