#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ServiceUP v15.0 - Расширенные тесты
Роль: Chief Core Business Tester
Использует pytest для запуска всех тестов проекта
"""

import sys
import os
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

# Добавляем корень проекта в path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestConfig(unittest.TestCase):
    """Тесты модуля конфигурации"""
    
    def test_config_import_no_side_effects(self):
        """Проверка импорта config без side effects"""
        # Важно: импорт не должен создавать директории
        import config
        self.assertTrue(hasattr(config, 'APP_VERSION'))
        self.assertTrue(hasattr(config, 'BASE_DIR'))
        self.assertTrue(hasattr(config, 'DB_PATH'))
        self.assertTrue(hasattr(config, 'ensure_directories'))
    
    def test_app_version_format(self):
        """Проверка формата версии приложения"""
        import config
        version = config.APP_VERSION
        self.assertIsInstance(version, str)
        self.assertTrue(len(version) > 0)
        # Версия должна содержать цифры и точки
        self.assertRegex(version, r'^[\d.]+$')
    
    def test_ensure_directories_creates_all(self):
        """Проверка создания всех директорий"""
        from config import ensure_directories, BACKUP_DIR, EXPORT_DIR, PHOTOS_DIR, THUMBNAILS_DIR, CLIENTS_DB_DIR, REPORTS_DIR, TEMPLATES_DIR
        
        ensure_directories()
        
        for directory in [BACKUP_DIR, EXPORT_DIR, PHOTOS_DIR, THUMBNAILS_DIR, CLIENTS_DB_DIR, REPORTS_DIR, TEMPLATES_DIR]:
            self.assertTrue(os.path.isdir(directory), f"Директория {directory} не создана")
    
    def test_paths_are_absolute(self):
        """Проверка что все пути абсолютные"""
        import config
        paths_to_check = ['BASE_DIR', 'DB_PATH', 'CONFIG_PATH', 'BACKUP_DIR', 'EXPORT_DIR', 'PHOTOS_DIR']
        for path_name in paths_to_check:
            path_value = getattr(config, path_name)
            self.assertTrue(os.path.isabs(path_value), f"{path_name} должен быть абсолютным путем")


class TestBootstrap(unittest.TestCase):
    """Тесты модуля bootstrap"""
    
    def test_bootstrap_import(self):
        """Проверка импорта bootstrap"""
        import bootstrap
        self.assertTrue(hasattr(bootstrap, 'check_dependencies'))
        self.assertTrue(hasattr(bootstrap, 'ensure_directories'))
    
    def test_check_dependencies_returns_bool(self):
        """check_dependencies должен возвращать bool"""
        from bootstrap import check_dependencies
        result = check_dependencies()
        self.assertIsInstance(result, bool)
    
    def test_ensure_directories_delegates(self):
        """ensure_directories должен делегировать вызов в config"""
        from bootstrap import ensure_directories
        # Функция должна выполняться без ошибок
        ensure_directories()


class TestConstants(unittest.TestCase):
    """Тесты констант"""
    
    def test_statuses_not_empty(self):
        """Статусы не должны быть пустыми"""
        from utils.constants import STATUSES
        self.assertGreater(len(STATUSES), 0)
        self.assertIsInstance(STATUSES, list)
    
    def test_priorities_not_empty(self):
        """Приоритеты не должны быть пустыми"""
        from utils.constants import PRIORITIES
        self.assertGreater(len(PRIORITIES), 0)
        self.assertIsInstance(PRIORITIES, list)
    
    def test_dictionary_types_structure(self):
        """Словари должны иметь правильную структуру"""
        from utils.constants import DICTIONARY_TYPES
        self.assertIsInstance(DICTIONARY_TYPES, dict)
        required_keys = {'name', 'icon', 'default_values'}
        for dict_type, config in DICTIONARY_TYPES.items():
            self.assertIsInstance(dict_type, str)
            self.assertIsInstance(config, dict)
            self.assertTrue(required_keys.issubset(config.keys()), 
                          f"Словарь {dict_type} должен содержать ключи {required_keys}")
            self.assertIsInstance(config['default_values'], list)
    
    def test_default_settings_structure(self):
        """Настройки по умолчанию должны иметь правильную структуру"""
        from utils.constants import DEFAULT_SETTINGS
        self.assertIsInstance(DEFAULT_SETTINGS, dict)
        self.assertIn('theme', DEFAULT_SETTINGS)
        self.assertIn('pwa', DEFAULT_SETTINGS)
        self.assertIsInstance(DEFAULT_SETTINGS['pwa'], dict)


class TestFormatters(unittest.TestCase):
    """Тесты утилит форматирования"""
    
    def setUp(self):
        from utils.formatters import format_price, format_phone, normalize_phone_digits, normalize_phone, parse_price_to_float
        self.format_price = format_price
        self.format_phone = format_phone
        self.normalize_phone_digits = normalize_phone_digits
        self.normalize_phone = normalize_phone
        self.parse_price_to_float = parse_price_to_float
    
    def test_format_price_basic(self):
        """Базовое форматирование цены"""
        result = self.format_price(1000)
        self.assertIn("₽", result)
    
    def test_format_price_zero(self):
        """Форматирование нулевой цены"""
        result = self.format_price(0)
        self.assertIn("0", result)
        self.assertIn("₽", result)
    
    def test_format_price_none(self):
        """Форматирование None цены"""
        result = self.format_price(None)
        self.assertEqual(result, "0 ₽")
    
    def test_format_price_string_with_comma(self):
        """Форматирование строковой цены с запятой"""
        result = self.format_price("1000,50")
        self.assertIn("₽", result)
    
    def test_format_phone_russian_mobile(self):
        """Форматирование российского мобильного"""
        result = self.format_phone("+79991234567")
        self.assertIn("+7", result)
        self.assertIn("(", result)
        self.assertIn(")", result)
    
    def test_format_phone_eight_start(self):
        """Форматирование телефона начиная с 8"""
        result = self.format_phone("89991234567")
        # format_phone сохраняет первую цифру, но форматирует номер
        self.assertIn("(", result)
        self.assertIn(")", result)
    
    def test_format_phone_empty(self):
        """Форматирование пустого телефона"""
        result = self.format_phone("")
        self.assertEqual(result, "")
    
    def test_normalize_phone_digits_removes_non_digits(self):
        """Нормализация удаляет нецифровые символы"""
        result = self.normalize_phone_digits("+7 (999) 123-45-67")
        self.assertEqual(result, "79991234567")
    
    def test_normalize_phone_standard_format(self):
        """Нормализация к стандартному формату"""
        result = self.normalize_phone("89991234567")
        self.assertEqual(result, "+7 (999) 123-45-67")
    
    def test_parse_price_to_float_basic(self):
        """Базовое преобразование цены в float"""
        result = self.parse_price_to_float("1000,50")
        self.assertAlmostEqual(result, 1000.50, places=2)
    
    def test_parse_price_to_float_with_spaces(self):
        """Преобразование цены с пробелами"""
        result = self.parse_price_to_float("1 000,50 ₽")
        self.assertAlmostEqual(result, 1000.50, places=2)
    
    def test_parse_price_to_float_zero(self):
        """Преобразование нуля"""
        result = self.parse_price_to_float("")
        self.assertEqual(result, 0.0)
    
    def test_parse_price_to_float_none(self):
        """Преобразование None"""
        result = self.parse_price_to_float(None)
        self.assertEqual(result, 0.0)


class TestValidators(unittest.TestCase):
    """Тесты валидаторов"""
    
    def setUp(self):
        from utils.validators import validate_phone, validate_price, validate_required, validate_email, validate_positive_number
        self.validate_phone = validate_phone
        self.validate_price = validate_price
        self.validate_required = validate_required
        self.validate_email = validate_email
        self.validate_positive_number = validate_positive_number
    
    def test_validate_phone_valid_russian(self):
        """Валидация корректного российского телефона"""
        self.assertTrue(self.validate_phone("+79991234567"))
        self.assertTrue(self.validate_phone("89991234567"))
        self.assertTrue(self.validate_phone("+7 (999) 123-45-67"))
    
    def test_validate_phone_invalid_short(self):
        """Валидация слишком короткого номера"""
        self.assertFalse(self.validate_phone("123"))
        self.assertFalse(self.validate_phone("abc"))
    
    def test_validate_phone_invalid_letters(self):
        """Валидация номера с буквами"""
        self.assertFalse(self.validate_phone("abcdefghij"))
    
    def test_validate_phone_empty(self):
        """Валидация пустого номера"""
        self.assertFalse(self.validate_phone(""))
        self.assertFalse(self.validate_phone(None))
    
    def test_validate_phone_international(self):
        """Валидация международных номеров (если phonenumbers доступен)"""
        # Американский номер
        self.assertTrue(self.validate_phone("+14155552671"))
        # Британский номер
        self.assertTrue(self.validate_phone("+442079460112"))
    
    def test_validate_price_valid_integer(self):
        """Валидация целочисленной цены"""
        self.assertTrue(self.validate_price("1000"))
        self.assertTrue(self.validate_price(1000))
    
    def test_validate_price_valid_decimal(self):
        """Валидация дробной цены"""
        self.assertTrue(self.validate_price("1000.50"))
        self.assertTrue(self.validate_price("1000,50"))
    
    def test_validate_price_empty_allowed(self):
        """Пустая цена допустима"""
        self.assertTrue(self.validate_price(""))
        self.assertTrue(self.validate_price(None))
    
    def test_validate_price_invalid_letters(self):
        """Невалидная цена с буквами"""
        self.assertFalse(self.validate_price("abc"))
    
    def test_validate_required_non_empty(self):
        """Валидация непустого значения"""
        self.assertTrue(self.validate_required("test"))
        self.assertTrue(self.validate_required(123))
    
    def test_validate_required_empty(self):
        """Валидация пустого значения"""
        self.assertFalse(self.validate_required(""))
        self.assertFalse(self.validate_required(None))
        self.assertFalse(self.validate_required("   "))
    
    def test_validate_email_valid(self):
        """Валидация корректного email"""
        self.assertTrue(self.validate_email("test@example.com"))
        self.assertTrue(self.validate_email("user.name+tag@domain.co.uk"))
    
    def test_validate_email_invalid(self):
        """Валидация некорректного email"""
        self.assertFalse(self.validate_email("invalid"))
        self.assertFalse(self.validate_email("@example.com"))
        self.assertFalse(self.validate_email("test@"))
        self.assertFalse(self.validate_email(""))
    
    def test_validate_positive_number_valid(self):
        """Валидация положительного числа"""
        self.assertTrue(self.validate_positive_number(100))
        self.assertTrue(self.validate_positive_number(0.5))
        self.assertTrue(self.validate_positive_number("100,5"))
    
    def test_validate_positive_number_invalid(self):
        """Валидация отрицательного числа"""
        self.assertFalse(self.validate_positive_number(-100))
        self.assertFalse(self.validate_positive_number("-50"))
        self.assertFalse(self.validate_positive_number(None))
    
    def test_validate_positive_number_allow_zero(self):
        """Валидация нуля с allow_zero=True"""
        self.assertFalse(self.validate_positive_number(0))
        self.assertTrue(self.validate_positive_number(0, allow_zero=True))


class TestModels(unittest.TestCase):
    """Тесты моделей данных"""
    
    def test_work_item_creation(self):
        """Создание WorkItem"""
        from database.models import WorkItem
        item = WorkItem(description="Тест", price="1000", quantity=2)
        self.assertEqual(item.description, "Тест")
        self.assertEqual(item.price, "1000")
        self.assertEqual(item.quantity, 2)
    
    def test_work_item_total_price(self):
        """Расчет общей стоимости работы"""
        from database.models import WorkItem
        item = WorkItem(description="Тест", price="1000,50", quantity=2)
        total = item.total_price()
        self.assertAlmostEqual(total, 2001.0, places=1)
    
    def test_work_item_to_dict(self):
        """Преобразование WorkItem в словарь"""
        from database.models import WorkItem
        item = WorkItem(description="Тест", price="1000", quantity=1)
        data = item.to_dict()
        self.assertIsInstance(data, dict)
        self.assertIn('description', data)
        self.assertIn('price', data)
        self.assertIn('quantity', data)
    
    def test_work_item_from_dict(self):
        """Создание WorkItem из словаря"""
        from database.models import WorkItem
        data = {'description': 'Тест', 'price': '1000', 'quantity': 2}
        item = WorkItem.from_dict(data)
        self.assertEqual(item.description, 'Тест')
        self.assertEqual(item.quantity, 2)
    
    def test_device_creation(self):
        """Создание Device"""
        from database.models import Device
        device = Device(order_number="00001", client_name="Иванов", phone="+79991234567")
        self.assertEqual(device.order_number, "00001")
        self.assertEqual(device.client_name, "Иванов")
    
    def test_device_to_dict(self):
        """Преобразование Device в словарь"""
        from database.models import Device
        device = Device(order_number="00001")
        data = device.to_dict()
        self.assertIsInstance(data, dict)
        self.assertIn('order_number', data)
        self.assertIn('phone', data)
    
    def test_work_items_manager_add(self):
        """Добавление работ в менеджер"""
        from database.models import WorkItemsManager, WorkItem
        manager = WorkItemsManager()
        item = WorkItem(description="Тест", price="1000")
        manager.add_item(item)
        self.assertEqual(len(manager.items), 1)
    
    def test_work_items_manager_total(self):
        """Расчет общей суммы работ"""
        from database.models import WorkItemsManager, WorkItem
        manager = WorkItemsManager()
        manager.add_item(WorkItem(description="Тест 1", price="1000", quantity=1))
        manager.add_item(WorkItem(description="Тест 2", price="500", quantity=2))
        total = manager.get_total_price()
        self.assertAlmostEqual(total, 2000.0, places=1)
    
    def test_work_items_manager_to_json(self):
        """Преобразование менеджера работ в JSON"""
        from database.models import WorkItemsManager, WorkItem
        manager = WorkItemsManager()
        manager.add_item(WorkItem(description="Тест", price="1000"))
        json_str = manager.to_json()
        self.assertIsInstance(json_str, str)
        self.assertIn("Тест", json_str)
    
    def test_work_items_manager_from_json(self):
        """Загрузка работ из JSON"""
        from database.models import WorkItemsManager
        import json
        manager = WorkItemsManager()
        json_data = json.dumps([{'description': 'Тест', 'price': '1000', 'quantity': 1}], ensure_ascii=False)
        manager.from_json(json_data)
        self.assertEqual(len(manager.items), 1)
        self.assertEqual(manager.items[0].description, 'Тест')


class TestHardware(unittest.TestCase):
    """Тесты определения железа"""
    
    @patch('uuid.getnode')
    def test_hwid_generation_fallback(self, mock_getnode):
        """Генерация HWID через fallback (MAC-адрес)"""
        mock_getnode.return_value = 123456789012
        
        from utils.hardware import get_hwid, get_hwid_short
        
        hwid = get_hwid()
        # HWID должен быть в формате XXXX-XXXX-XXXX-XXXX
        self.assertRegex(hwid, r'^[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}$')
        
        hwid_short = get_hwid_short()
        # Короткий HWID без дефисов
        self.assertNotIn('-', hwid_short)
        self.assertEqual(len(hwid_short), 16)
    
    def test_hwid_caching(self):
        """Кеширование HWID"""
        from utils.hardware import get_hwid, _cached_hwid
        
        # Сбрасываем кеш
        import utils.hardware as hw_module
        hw_module._cached_hwid = None
        
        hwid1 = get_hwid()
        hwid2 = get_hwid()
        
        self.assertEqual(hwid1, hwid2)


if __name__ == "__main__":
    print("=" * 60)
    print("ServiceUP v15.0 - Расширенные тесты")
    print("=" * 60)
    unittest.main(verbosity=2)
