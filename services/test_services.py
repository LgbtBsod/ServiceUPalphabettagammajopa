#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тесты для сервисного слоя.

Проверяют бизнес-логику OrderService и ClientService.
Соблюдают принципы изоляции тестов и покрытия граничных случаев.
"""

import pytest
import sqlite3
import os
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, MagicMock, patch

# Импорты тестируемых модулей
from services import OrderService, ClientService, create_services
from database.repositories.unit_of_work import UnitOfWork
from database.repositories.sqlite_connection import SQLAlchemyConnection
from models.pydantic_models import OrderStatus, Priority, WorkItem


@pytest.fixture
def test_db_path(tmp_path):
    """Создание временной БД для тестов."""
    db_path = tmp_path / "test_service.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Создание таблиц с полной схемой как в production (включая work_items для SQLAlchemy модели)
    cursor.execute('''
        CREATE TABLE devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT UNIQUE,
            receipt_date TEXT,
            completion_date TEXT,
            device_type TEXT,
            brand TEXT,
            model TEXT,
            serial_number TEXT,
            defect TEXT,
            appearance TEXT,
            completeness TEXT,
            work_items TEXT DEFAULT '[]',
            client_name TEXT,
            client_status TEXT DEFAULT 'Новый',
            phone TEXT,
            total_price REAL DEFAULT 0,
            prepayment REAL DEFAULT 0,
            status TEXT DEFAULT 'Диагностика',
            priority TEXT DEFAULT 'Обычный',
            engineer TEXT,
            warranty TEXT,
            notes TEXT,
            photos TEXT,
            expense TEXT,
            diagnostic_cost TEXT,
            repair_cost TEXT,
            client_id INTEGER,
            ready_date TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT UNIQUE,
            status TEXT DEFAULT 'Новый',
            email TEXT,
            notes TEXT,
            total_orders INTEGER DEFAULT 0,
            completed_orders INTEGER DEFAULT 0,
            total_spent REAL DEFAULT 0,
            last_order_date TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE counters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            value INTEGER DEFAULT 1
        )
    ''')
    cursor.execute("INSERT INTO counters (name, value) VALUES ('order_counter', 1)")
    
    conn.commit()
    conn.close()
    
    return str(db_path)


@pytest.fixture
def connection(test_db_path):
    """Подключение к тестовой БД."""
    conn = SQLAlchemyConnection(f"sqlite:///{test_db_path}")
    conn.connect()
    yield conn
    conn.disconnect()


@pytest.fixture
def uow(connection):
    """Unit of Work для тестов."""
    return UnitOfWork(connection)


@pytest.fixture
def order_service(uow):
    """Сервис заказов для тестов."""
    return OrderService(lambda: uow)


@pytest.fixture
def client_service(uow):
    """Сервис клиентов для тестов."""
    return ClientService(lambda: uow)


class TestOrderService:
    """Тесты OrderService."""

    def test_create_order_success(self, order_service, uow):
        """Создание заказа успешно."""
        order_data = {
            'device_type': 'Ноутбук',
            'brand': 'Apple',
            'model': 'MacBook Pro',
            'defect': 'Не включается',
            'client_name': 'Иванов И.И.',
            'phone': '+79991234567',
        }
        
        order = order_service.create_order(order_data)
        
        assert order is not None
        assert order.order_number in ['00001', '00002']  # Первый или второй заказ
        assert order.status == OrderStatus.DIAGNOSTICS.value
        assert order.priority == Priority.NORMAL.value
        assert order.brand == 'Apple'

    def test_create_order_with_custom_status(self, order_service, uow):
        """Создание заказа с пользовательским статусом."""
        order_data = {
            'device_type': 'Смартфон',
            'brand': 'Samsung',
            'model': 'Galaxy S21',
            'defect': 'Разбит экран',
            'status': 'В ремонте',
            'priority': 'Срочный',
        }
        
        order = order_service.create_order(order_data)
        
        assert order.status == 'В ремонте'
        assert order.priority == 'Срочный'

    def test_get_order_by_id(self, order_service, uow):
        """Получение заказа по ID."""
        # Сначала создадим заказ
        order_data = {
            'device_type': 'ПК',
            'brand': 'Dell',
            'model': 'OptiPlex',
            'defect': 'Шумит',
        }
        created = order_service.create_order(order_data)
        
        # Получим по ID
        retrieved = order_service.get_order(created.id)
        
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.brand == 'Dell'

    def test_get_order_not_found(self, order_service):
        """Получение несуществующего заказа."""
        result = order_service.get_order(99999)
        assert result is None

    def test_update_order_status_success(self, order_service, uow):
        """Успешное обновление статуса заказа."""
        # Создаем заказ
        order_data = {
            'device_type': 'Планшет',
            'brand': 'iPad',
            'model': 'Air',
            'defect': 'Не работает кнопка',
        }
        order = order_service.create_order(order_data)
        
        # Обновляем статус
        updated = order_service.update_order_status(order.id, OrderStatus.READY)
        
        assert updated is not None
        assert updated.status == OrderStatus.READY.value
        assert updated.ready_date is not None

    def test_update_refused_order_forbidden(self, order_service, uow):
        """Запрет изменения статуса отказанного заказа."""
        # Создаем заказ со статусом "Отказ"
        order_data = {
            'device_type': 'Монитор',
            'brand': 'LG',
            'model': 'UltraFine',
            'defect': 'Нет изображения',
            'status': 'Отказ от ремонта',
        }
        order = order_service.create_order(order_data)
        
        # Пытаемся изменить статус
        with pytest.raises(ValueError, match="Нельзя изменить статус отказанного заказа"):
            order_service.update_order_status(order.id, OrderStatus.IN_REPAIR)

    def test_add_work_item(self, order_service, uow):
        """Добавление работы к заказу."""
        # Создаем заказ
        order_data = {
            'device_type': 'Ноутбук',
            'brand': 'HP',
            'model': 'Pavilion',
            'defect': 'Тормозит',
        }
        order = order_service.create_order(order_data)
        
        # Добавляем работу
        work_item = WorkItem(
            name='Чистка от пыли',
            price=Decimal('1500.00'),
            warranty='3 месяца',
        )
        
        updated = order_service.add_work_item(order.id, work_item)
        
        assert updated is not None
        # Проверяем, что работа добавлена (через репозиторий)
        works = uow.devices.get_work_items(order.id)
        assert len(works) == 1
        assert works[0]['name'] == 'Чистка от пыли'

    def test_search_orders(self, order_service, uow):
        """Поиск заказов."""
        # Создаем несколько заказов
        order_service.create_order({
            'device_type': 'Ноутбук',
            'brand': 'Apple',
            'model': 'MacBook Air',
            'defect': 'Не работает клавиатура',
            'client_name': 'Петров П.П.',
        })
        
        order_service.create_order({
            'device_type': 'Смартфон',
            'brand': 'Google',
            'model': 'Pixel',
            'defect': 'Быстро разряжается',
            'client_name': 'Сидоров С.С.',
        })
        
        # Поиск по бренду
        results = order_service.search_orders('Apple')
        assert len(results) >= 1
        assert any(r.brand == 'Apple' for r in results)
        
        # Поиск по клиенту
        results = order_service.search_orders('Петров')
        assert len(results) >= 1

    def test_get_overdue_orders(self, order_service, uow):
        """Получение просроченных заказов."""
        connection = uow._connection
        
        # Создаем старый заказ напрямую в БД
        old_date = (datetime.now() - timedelta(days=20)).isoformat()
        connection.execute('''
            INSERT INTO devices (order_number, receipt_date, device_type, brand, model, defect, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', ('00099', old_date, 'Ноутбук', 'Old', 'Model', 'Старый дефект', 'В ремонте'))
        connection.commit()
        
        overdue = order_service.get_overdue_orders(days=14)
        
        assert len(overdue) >= 1
        assert any(o.days_in_service > 14 for o in overdue)


class TestClientService:
    """Тесты ClientService."""

    def test_create_client_success(self, client_service, uow):
        """Создание клиента успешно."""
        client_data = {
            'full_name': 'Иванов Иван Иванович',
            'phone': '+79991112233',
            'email': 'ivan@example.com',
        }
        
        client = client_service.create_client(client_data)
        
        assert client is not None
        assert client.full_name == 'Иванов Иван Иванович'
        assert '+7' in client.phone

    def test_create_duplicate_client_warning(self, client_service, caplog):
        """Предупреждение при создании дубликата клиента."""
        import logging
        caplog.set_level(logging.WARNING)
        
        # Создаем первого клиента
        client_service.create_client({
            'full_name': 'Первый Клиент',
            'phone': '+79990001122',
        })
        
        # Пытаемся создать дубликат
        client_service.create_client({
            'full_name': 'Дубликат Клиента',
            'phone': '+79990001122',
        })
        
        assert "уже существует" in caplog.text

    def test_get_client_by_phone(self, client_service, uow):
        """Получение клиента по телефону."""
        # Создаем клиента
        client_service.create_client({
            'full_name': 'Телефонный Клиент',
            'phone': '+79995556677',
        })
        
        # Получаем по телефону
        client = client_service.get_client_by_phone('+79995556677')
        
        assert client is not None
        assert client.full_name == 'Телефонный Клиент'

    def test_get_client_not_found(self, client_service):
        """Получение несуществующего клиента."""
        result = client_service.get_client_by_phone('+79990000000')
        assert result is None

    def test_search_clients(self, client_service, uow):
        """Поиск клиентов."""
        # Создаем клиентов
        client_service.create_client({
            'full_name': 'Александр Пушкин',
            'phone': '+79991111111',
        })
        
        client_service.create_client({
            'full_name': 'Михаил Лермонтов',
            'phone': '+79992222222',
        })
        
        # Поиск по имени
        results = client_service.search_clients('Александр')
        assert len(results) >= 1
        
        # Поиск по телефону (частичный)
        results = client_service.search_clients('9991111')
        assert len(results) >= 1

    def test_update_client_stats(self, client_service, uow):
        """Обновление статистики клиента."""
        # Создаем клиента
        client = client_service.create_client({
            'full_name': 'Статистический Клиент',
            'phone': '+79998887766',
        })
        
        # Создаем заказы для этого клиента
        order_data = {
            'device_type': 'Ноутбук',
            'brand': 'Test',
            'model': 'Model',
            'defect': 'Test',
            'client_name': 'Статистический Клиент',
            'phone': '+79998887766',
        }
        
        from services import OrderService
        order_service = OrderService(lambda: uow)
        order_service.create_order(order_data)
        
        # Обновляем статистику
        updated = client_service.update_client_stats(client.id)
        
        assert updated is not None
        # Статистика должна обновиться (проверяется через логику update_stats)


class TestCreateServices:
    """Тесты фабрики сервисов."""

    def test_create_services_returns_dict(self, uow):
        """Фабрика возвращает словарь с сервисами."""
        services = create_services(lambda: uow)
        
        assert isinstance(services, dict)
        assert 'orders' in services
        assert 'clients' in services
        assert isinstance(services['orders'], OrderService)
        assert isinstance(services['clients'], ClientService)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
