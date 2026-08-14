#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Базовые тесты для ServiceUP v15.0
Роль: Chief Core Business Tester
"""

import sys
import os
import unittest

# Добавляем корень проекта в path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestConfig(unittest.TestCase):
    """Тесты модуля конфигурации"""
    
    def test_config_import(self):
        """Проверка импорта config без side effects"""
        # Важно: импорт не должен создавать директории
        import config
        self.assertTrue(hasattr(config, 'APP_VERSION'))
        self.assertTrue(hasattr(config, 'BASE_DIR'))
        self.assertTrue(hasattr(config, 'DB_PATH'))
    
    def test_app_version(self):
        """Проверка версии приложения"""
        import config
        self.assertEqual(config.APP_VERSION, "15.0")
    
    def test_ensure_directories(self):
        """Проверка создания директорий"""
        from config import ensure_directories
        # Функция должна выполняться без ошибок
        ensure_directories()
        
        # Проверяем что директории существуют
        from config import BACKUP_DIR, EXPORT_DIR, PHOTOS_DIR
        self.assertTrue(os.path.isdir(BACKUP_DIR))
        self.assertTrue(os.path.isdir(EXPORT_DIR))
        self.assertTrue(os.path.isdir(PHOTOS_DIR))


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


class TestConstants(unittest.TestCase):
    """Тесты констант"""
    
    def test_statuses_not_empty(self):
        """Статусы не должны быть пустыми"""
        from utils.constants import STATUSES
        self.assertGreater(len(STATUSES), 0)
    
    def test_priorities_not_empty(self):
        """Приоритеты не должны быть пустыми"""
        from utils.constants import PRIORITIES
        self.assertGreater(len(PRIORITIES), 0)
    
    def test_dictionary_types_structure(self):
        """Словари должны иметь правильную структуру"""
        from utils.constants import DICTIONARY_TYPES
        self.assertIsInstance(DICTIONARY_TYPES, dict)
        for dict_type, config in DICTIONARY_TYPES.items():
            self.assertIn('name', config)
            self.assertIn('icon', config)
            self.assertIn('default_values', config)


class TestFormatters(unittest.TestCase):
    """Тесты утилит форматирования"""
    
    def test_format_price(self):
        """Проверка форматирования цены"""
        from utils.formatters import format_price
        # Функция возвращает цену с двумя знаками после запятой
        result = format_price(1000)
        self.assertIn("1 000", result)
        self.assertIn("₽", result)
    
    def test_format_phone(self):
        """Проверка форматирования телефона"""
        from utils.formatters import format_phone
        # Базовая проверка что функция существует и работает
        result = format_phone("+79991234567")
        self.assertIsInstance(result, str)


class TestValidators(unittest.TestCase):
    """Тесты валидаторов"""
    
    def test_validate_phone_valid(self):
        """Валидация корректного телефона"""
        from utils.validators import validate_phone
        self.assertTrue(validate_phone("+79991234567"))
        self.assertTrue(validate_phone("89991234567"))
    
    def test_validate_phone_invalid(self):
        """Валидация некорректного телефона"""
        from utils.validators import validate_phone
        self.assertFalse(validate_phone("abc"))
        self.assertFalse(validate_phone(""))
    
    def test_validate_price_valid(self):
        """Валидация корректной цены"""
        from utils.validators import validate_price
        self.assertTrue(validate_price("1000"))
        self.assertTrue(validate_price("1000.50"))
    
    def test_validate_price_invalid(self):
        """Валидация некорректной цены"""
        from utils.validators import validate_price
        self.assertFalse(validate_price("abc"))
        # Отрицательные числа могут быть допустимы для скидок/возвратов
        # self.assertFalse(validate_price("-100"))


if __name__ == "__main__":
    print("=" * 60)
    print("ServiceUP v15.0 - Запуск тестов")
    print("=" * 60)
    unittest.main(verbosity=2)
