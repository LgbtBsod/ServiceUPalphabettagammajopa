#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тесты для Pydantic моделей данных.
Роль: Chief Core Business Tester
"""

import sys
import os
import unittest
from decimal import Decimal
from datetime import datetime
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestClientModel(unittest.TestCase):
    """Тесты модели Client"""

    def test_create_valid_client(self):
        """Создание валидного клиента"""
        from models.pydantic_models import Client, ClientStatus
        
        client = Client(
            full_name="Иванов Иван Иванович",
            phone="+7 (999) 123-45-67",
            email="ivan@example.com",
            status=ClientStatus.REGULAR,
        )
        
        self.assertEqual(client.full_name, "Иванов Иван Иванович")
        self.assertIn("+7", client.phone)
        self.assertEqual(client.email, "ivan@example.com")
        self.assertEqual(client.status.value, "Постоянный")

    def test_client_phone_validation_invalid(self):
        """Валидация телефона - некорректный номер"""
        from models.pydantic_models import Client
        
        with self.assertRaises(ValueError):
            Client(
                full_name="Иванов И.И.",
                phone="invalid",
            )

    def test_client_empty_name(self):
        """Валидация имени - пустое имя"""
        from models.pydantic_models import Client
        
        with self.assertRaises(Exception):  # pydantic.ValidationError
            Client(
                full_name="",
                phone="+79991234567",
            )

    def test_client_email_pattern(self):
        """Валидация email по паттерну"""
        from models.pydantic_models import Client
        
        # Некорректный email
        with self.assertRaises(Exception):
            Client(
                full_name="Иванов И.И.",
                phone="+79991234567",
                email="invalid-email",
            )

    def test_client_auto_updated_at(self):
        """Автоматическая установка updated_at"""
        from models.pydantic_models import Client
        
        client = Client(
            full_name="Иванов И.И.",
            phone="+79991234567",
        )
        
        self.assertIsNotNone(client.updated_at)
        self.assertIsInstance(client.updated_at, datetime)


class TestOrderModel(unittest.TestCase):
    """Тесты модели Order"""

    def test_create_valid_order(self):
        """Создание валидного заказа"""
        from models.pydantic_models import Order, OrderStatus, Priority, DeviceType
        from decimal import Decimal
        
        order = Order(
            order_number="00001",
            device_type=DeviceType.LAPTOP,
            brand="Apple",
            model="MacBook Pro",
            defects="Не включается",
            diagnostic_cost=Decimal("1500.00"),
            repair_cost=Decimal("8500.00"),
        )
        
        self.assertEqual(order.order_number, "00001")
        self.assertEqual(order.brand, "Apple")
        self.assertEqual(order.status.value, "Диагностика")  # default
        self.assertAlmostEqual(float(order.total_cost), 10000.00)

    def test_order_total_calculation_diagnostic_only(self):
        """Расчет total_cost только с диагностикой"""
        from models.pydantic_models import Order, DeviceType
        from decimal import Decimal
        
        order = Order(
            order_number="00002",
            device_type=DeviceType.SMARTPHONE,
            brand="Samsung",
            model="Galaxy S21",
            defects="Разбит экран",
            diagnostic_cost=Decimal("1000.00"),
        )
        
        self.assertAlmostEqual(float(order.total_cost), 1000.00)

    def test_order_total_calculation_repair_only(self):
        """Расчет total_cost только с ремонтом"""
        from models.pydantic_models import Order, DeviceType
        from decimal import Decimal
        
        order = Order(
            order_number="00003",
            device_type=DeviceType.PC,
            brand="Custom",
            model="Gaming PC",
            defects="Замена БП",
            repair_cost=Decimal("5000.00"),
        )
        
        self.assertAlmostEqual(float(order.total_cost), 5000.00)

    def test_order_days_in_service(self):
        """Проверка days_in_service"""
        from models.pydantic_models import Order, DeviceType
        from datetime import datetime, timedelta
        
        # Заказ создан 5 дней назад
        receipt_date = datetime.now() - timedelta(days=5)
        
        order = Order(
            order_number="00004",
            device_type=DeviceType.TABLET,
            brand="iPad",
            model="Pro 11",
            defects="Замена батареи",
            receipt_date=receipt_date,
        )
        
        self.assertGreaterEqual(order.days_in_service, 5)

    def test_order_is_overdue(self):
        """Проверка is_overdue (более 14 дней)"""
        from models.pydantic_models import Order, DeviceType
        from datetime import datetime, timedelta
        
        # Просроченный заказ (20 дней)
        receipt_date = datetime.now() - timedelta(days=20)
        
        order = Order(
            order_number="00005",
            device_type=DeviceType.MONITOR,
            brand="LG",
            model="UltraFine",
            defects="Нет изображения",
            receipt_date=receipt_date,
        )
        
        self.assertTrue(order.is_overdue)
        
        # Не просроченный заказ (5 дней)
        receipt_date_fresh = datetime.now() - timedelta(days=5)
        order_fresh = Order(
            order_number="00006",
            device_type=DeviceType.PRINTER,
            brand="HP",
            model="LaserJet",
            defects="Захват бумаги",
            receipt_date=receipt_date_fresh,
        )
        
        self.assertFalse(order_fresh.is_overdue)


class TestDeviceModel(unittest.TestCase):
    """Тесты модели Device"""

    def test_create_valid_device(self):
        """Создание валидного устройства"""
        from models.pydantic_models import Device, DeviceType
        
        device = Device(
            device_type=DeviceType.LAPTOP,
            brand="Dell",
            model="XPS 15",
            serial_number="ABC123XYZ",
            defects="Не работает клавиатура",
        )
        
        self.assertEqual(device.device_type.value, "Ноутбук")
        self.assertEqual(device.brand, "Dell")
        self.assertEqual(device.serial_number, "ABC123XYZ")

    def test_device_required_fields(self):
        """Проверка обязательных полей"""
        from models.pydantic_models import Device, DeviceType
        
        with self.assertRaises(Exception):
            Device(
                device_type=DeviceType.LAPTOP,
                # brand отсутствует - должно вызвать ошибку
                model="Test",
                defects="Test defect",
            )


class TestWorkItemModel(unittest.TestCase):
    """Тесты модели WorkItem"""

    def test_create_work_item_with_price(self):
        """Создание работы с ценой"""
        from models.pydantic_models import WorkItem
        from decimal import Decimal
        
        work = WorkItem(
            name="Замена дисплея",
            price=Decimal("3500.00"),
            warranty="3 месяца",
        )
        
        self.assertEqual(work.name, "Замена дисплея")
        self.assertAlmostEqual(float(work.price), 3500.00)
        self.assertEqual(work.warranty, "3 месяца")

    def test_work_item_optional_price(self):
        """Работа без цены (опционально)"""
        from models.pydantic_models import WorkItem
        
        work = WorkItem(
            name="Консультация",
        )
        
        self.assertIsNone(work.price)


class TestSettingsModel(unittest.TestCase):
    """Тесты модели Settings"""

    def test_create_default_settings(self):
        """Создание настроек по умолчанию"""
        from models.pydantic_models import Settings
        
        settings = Settings()
        
        self.assertEqual(settings.theme, "light")
        self.assertEqual(settings.fullscreen, False)
        self.assertEqual(settings.confirm_delete, True)
        self.assertEqual(settings.overdue_days, 14)

    def test_settings_validation_accent_color(self):
        """Валидация accent_color (hex формат)"""
        from models.pydantic_models import Settings
        
        # Некорректный цвет
        with self.assertRaises(Exception):
            Settings(accent_color="invalid-color")
        
        # Корректный цвет
        settings = Settings(accent_color="#FF5733")
        self.assertEqual(settings.accent_color, "#FF5733")

    def test_settings_window_size_validation(self):
        """Валидация размеров окна"""
        from models.pydantic_models import Settings
        
        # Слишком маленькое окно
        with self.assertRaises(Exception):
            Settings(window_width=400)  # min 800
        
        # Слишком большое окно
        with self.assertRaises(Exception):
            Settings(window_height=3000)  # max 2160
        
        # Корректные размеры
        settings = Settings(window_width=1920, window_height=1080)
        self.assertEqual(settings.window_width, 1920)
        self.assertEqual(settings.window_height, 1080)


class TestEnums(unittest.TestCase):
    """Тесты Enum типов"""

    def test_order_status_values(self):
        """Проверка значений OrderStatus"""
        from models.pydantic_models import OrderStatus
        
        self.assertEqual(OrderStatus.DIAGNOSTICS.value, "Диагностика")
        self.assertEqual(OrderStatus.IN_REPAIR.value, "В ремонте")
        self.assertEqual(OrderStatus.READY.value, "Готов к выдаче")

    def test_priority_values(self):
        """Проверка значений Priority"""
        from models.pydantic_models import Priority
        
        self.assertEqual(Priority.LOW.value, "Низкий")
        self.assertEqual(Priority.URGENT.value, "Срочный")

    def test_device_type_values(self):
        """Проверка значений DeviceType"""
        from models.pydantic_models import DeviceType
        
        self.assertEqual(DeviceType.LAPTOP.value, "Ноутбук")
        self.assertEqual(DeviceType.SMARTPHONE.value, "Смартфон")


if __name__ == "__main__":
    print("=" * 60)
    print("ServiceUP v15.0 - Pydantic Models Tests")
    print("=" * 60)
    unittest.main(verbosity=2)
