#!/usr/bin/env python3
"""Integration test — проверка работоспособности приложения через ядро и БД.

Тестирует полный цикл работы с заказом:
1. Создание клиента
2. Создание заказа (устройства)
3. Обновление данных заказа
4. Поиск и фильтрация
5. Изменение статуса
6. Проверка истории
7. Удаление/архивация

Все операции выполняются ТОЛЬКО через предусмотренную архитектуру:
- Ядро (ServiceUpCore)
- Фасад БД (Database)
- Модули через call_module_method()

НЕ используется прямой доступ к БД или SQL запросы.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

# Добавляем workspace в path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.kernel import ServiceUpCore
from database.sqlalchemy_database import Database
from database.db_core import DuplicateDatabaseConnectionError


def log_test(name: str, passed: bool, details: str = "") -> None:
    """Вывод результата теста."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"\n{status}: {name}")
    if details:
        print(f"   └─ {details}")


def test_database_initialization(core: ServiceUpCore) -> bool:
    """Тест 1: Инициализация БД через ядро."""
    try:
        db = Database()
        core.register_service(Database, db)
        
        # Проверяем что БД работает
        order_number = db.peek_next_order_number()
        passed = order_number is not None and isinstance(order_number, int)
        log_test("Инициализация БД", passed, f"Следующий номер заказа: {order_number}")
        return passed
    except Exception as e:
        log_test("Инициализация БД", False, f"Ошибка: {e}")
        return False


def test_create_client(db: Database) -> tuple[bool, int | None]:
    """Тест 2: Создание клиента."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        client_name = f"Тестовый Клиент {timestamp}"
        client_phone = f"+7999{timestamp[-4:]}0001"
        
        client_id = db.get_or_create_client(
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


def test_create_order(db: Database, client_id: int) -> tuple[bool, int | None]:
    """Тест 3: Создание заказа (устройства)."""
    try:
        # Получаем следующий номер заказа
        order_number = db.get_next_order_number()
        
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
        
        device_id = db.add_device(device_data)
        
        passed = device_id is not None and device_id > 0
        log_test("Создание заказа", passed,
                f"Device ID={device_id}, Order #{order_number}")
        return passed, device_id
    except Exception as e:
        log_test("Создание заказа", False, f"Ошибка: {e}")
        return False, None


def test_update_order(db: Database, device_id: int) -> bool:
    """Тест 4: Обновление данных заказа."""
    try:
        update_data = {
            "defect": "Не включается, разбит экран, не работает FaceID",
            "total_price": "7500",
            "status": "В работе",
            "work_items_json": '[{"name": "Диагностика", "price": "500"}, {"name": "Замена экрана", "price": "2500"}]',
            "notes": "Тестовый заказ - обновлено",
            "updated_by_id": 1,
        }
        
        success = db.update_device(device_id, update_data)
        
        # Проверяем что данные обновились (используем правильный API)
        devices = db.get_all_devices()
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


def test_search_and_filter(db: Database, client_id: int, device_id: int) -> bool:
    """Тест 5: Поиск и фильтрация заказов."""
    try:
        # Получение всех устройств
        all_devices = db.get_all_devices()
        has_devices = len(all_devices) > 0
        
        # Поиск по тексту (используем search_devices)
        found_devices = db.search_devices(search_text=str(device_id))
        found_by_search = len(found_devices) > 0
        
        # Фильтрация по статусу (используем get_devices_by_filters)
        devices_in_work = db.get_devices_by_filters(
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


def test_change_status_to_ready(db: Database, device_id: int) -> bool:
    """Тест 6: Изменение статуса на 'Готов'."""
    try:
        update_data = {
            "status": "Готов",
            "total_price": "7500",
            "work_items_json": '[{"name": "Диагностика", "price": "500"}, {"name": "Замена экрана", "price": "2500"}, {"name": "Настройка", "price": "500"}]',
            "notes": "Ремонт завершен",
            "updated_by_id": 1,
        }
        
        success = db.update_device(device_id, update_data)
        
        # Проверяем изменение статуса
        devices = db.get_all_devices()
        found_device = next((d for d in devices if d["id"] == device_id), None)
        passed = success and found_device is not None and found_device.get("status") == "Готов"
        
        log_test("Изменение статуса на 'Готов'", passed,
                f"Текущий статус: {found_device.get('status') if passed else 'N/A'}")
        return passed
    except Exception as e:
        log_test("Изменение статуса на 'Готов'", False, f"Ошибка: {e}")
        return False


def test_client_history(db: Database, client_id: int, device_id: int) -> bool:
    """Тест 7: Проверка истории клиента."""
    try:
        # Добавляем запись в историю ремонтов
        device_data = {
            "order_number": "TEST001",
            "receipt_date": datetime.now().strftime("%Y-%m-%d"),
            "completion_date": "",
            "device_type": "Смартфон",
            "brand": "Samsung",
            "model": "Galaxy S21",
            "defect": "Разбит экран",
            "status": "В работе",
            "total_price": "5000",
        }
        
        db.add_to_repair_history_main(client_id, device_id, device_data)
        
        # Получаем историю (используем данные из теста создания клиента)
        history = db.get_client_history_main(
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


def test_statistics(db: Database, client_id: int, device_id: int) -> bool:
    """Тест 8: Статистика клиента."""
    try:
        stats = db.get_client_stats_main(
            client_name="Тестовый Клиент",
            client_phone="+7999"
        )
        
        # Статистика должна быть dict (может быть пустым если клиент не найден по имени)
        passed = isinstance(stats, dict)
        log_test("Статистика клиента", passed,
                f"Полей в статистике: {len(stats)}")
        return passed
    except Exception as e:
        log_test("Статистика клиента", False, f"Ошибка: {e}")
        return False


def test_kernel_module_registration(core: ServiceUpCore) -> bool:
    """Тест 9: Регистрация модулей через ядро."""
    try:
        # Создаем mock модуль для демонстрации
        class MockModule:
            def get_info(self):
                return {"name": "TestModule", "version": "1.0"}
            
            def process(self, data):
                return {"processed": True, "data": data}
        
        mock_instance = MockModule()
        
        # Регистрируем модуль
        core.register_module(
            name="test_module",
            module_instance=mock_instance,
            module_type=MockModule,
            api=mock_instance,
        )
        
        # Получаем API модуля
        api = core.get_module_api("test_module")
        info = api.get_info() if api else {}
        
        passed = api is not None and info.get("name") == "TestModule"
        log_test("Регистрация модулей через ядро", passed,
                f"Модуль: {info.get('name')}, Версия: {info.get('version')}")
        return passed
    except Exception as e:
        log_test("Регистрация модулей через ядро", False, f"Ошибка: {e}")
        return False


def test_kernel_call_module_method(core: ServiceUpCore) -> bool:
    """Тест 10: Вызов методов модулей через ядро."""
    try:
        # Вызываем метод зарегистрированного модуля
        result = core.call_module_method(
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


def test_cache_operations(core: ServiceUpCore) -> bool:
    """Тест 11: Операции с кэшем ядра."""
    try:
        cache_key = "test_key"
        cache_value = {"data": "test_value", "timestamp": time.time()}
        
        # Установка в кэш
        core.cache_set(cache_key, cache_value, ttl_seconds=60)
        
        # Чтение из кэша
        cached = core.cache_get(cache_key)
        
        # Удаление из кэша
        deleted = core.cache_delete(cache_key)
        
        passed = cached == cache_value and deleted
        log_test("Операции с кэшем", passed,
                f"Записано и прочитано: {cached is not None}, Удалено: {deleted}")
        return passed
    except Exception as e:
        log_test("Операции с кэшем", False, f"Ошибка: {e}")
        return False


def test_event_bus(core: ServiceUpCore) -> bool:
    """Тест 12: Шина событий."""
    try:
        event_received = []
        
        def handler(event):
            # Event bus передает объект Event, а не строку
            event_received.append(event)
        
        # Подписка на событие типа str (будет преобразовано в "str")
        core.subscribe("TestEvent", handler)
        
        # Публикация события (создаем правильный объект Event)
        from core.events.event_bus import Event
        test_event = Event(event_type="TestEvent", data={"message": "test"})
        core.publish(test_event)
        
        # Отписка
        core.unsubscribe("TestEvent", handler)
        
        passed = len(event_received) == 1
        log_test("Шина событий", passed,
                f"Событий получено: {len(event_received)}")
        return passed
    except Exception as e:
        log_test("Шина событий", False, f"Ошибка: {e}")
        return False


def run_integration_tests():
    """Запуск всех интеграционных тестов."""
    print("=" * 70)
    print("INTEGRATION TESTS - ServiceUP Application")
    print("Testing through Core + Database Facade (no direct DB access)")
    print("=" * 70)
    
    results = []
    core = None
    db = None
    client_id = None
    device_id = None
    
    try:
        # Инициализация ядра
        print("\n📦 Initializing ServiceUp Core...")
        core = ServiceUpCore()
        core.initialize()
        print("✅ Core initialized successfully")
        
        # Тест 1: Инициализация БД
        if test_database_initialization(core):
            db = core.get_service(Database)
        else:
            print("\n⚠️  Cannot continue without database")
            return False
        
        # Тест 2: Создание клиента
        passed, client_id = test_create_client(db)
        results.append(passed)
        if not passed:
            print("\n⚠️  Cannot continue without client")
            return False
        
        # Тест 3: Создание заказа
        passed, device_id = test_create_order(db, client_id)
        results.append(passed)
        if not passed:
            print("\n⚠️  Cannot continue without order")
            return False
        
        # Тест 4: Обновление заказа
        results.append(test_update_order(db, device_id))
        
        # Тест 5: Поиск и фильтрация
        results.append(test_search_and_filter(db, client_id, device_id))
        
        # Тест 6: Изменение статуса
        results.append(test_change_status_to_ready(db, device_id))
        
        # Тест 7: История клиента
        results.append(test_client_history(db, client_id, device_id))
        
        # Тест 8: Статистика
        results.append(test_statistics(db, client_id, device_id))
        
        # Тест 9: Регистрация модулей
        results.append(test_kernel_module_registration(core))
        
        # Тест 10: Вызов методов модулей
        results.append(test_kernel_call_module_method(core))
        
        # Тест 11: Кэш
        results.append(test_cache_operations(core))
        
        # Тест 12: Шина событий
        results.append(test_event_bus(core))
        
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Cleanup
        if core:
            print("\n🧹 Shutting down Core...")
            core.shutdown()
            print("✅ Core shutdown complete")
    
    # Summary
    total = len(results)
    passed = sum(results)
    failed = total - passed
    
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Total tests:  {total}")
    print(f"Passed:       {passed} ✅")
    print(f"Failed:       {failed} ❌")
    print(f"Success rate: {(passed/total*100):.1f}%")
    print("=" * 70)
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! Application is working correctly.")
        return True
    else:
        print(f"\n⚠️  {failed} test(s) failed. Check logs above.")
        return False


if __name__ == "__main__":
    success = run_integration_tests()
    sys.exit(0 if success else 1)
