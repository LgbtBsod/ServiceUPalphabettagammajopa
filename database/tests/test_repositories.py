#!/usr/bin/env python3

"""Тесты для репозиториев базы данных.

Проверка корректности работы репозиториев, транзакций и Unit of Work.
Соблюдает принципы тестирования: изолированность, повторяемость, автоматизация.
"""

import os
import tempfile

import pytest

from database.repositories import (
    ClientRepository,
    DeviceRepository,
    SQLAlchemyConnection,
    UnitOfWork,
)


class TestSQLAlchemyConnection:
    """Тесты подключения к SQLite."""

    @pytest.fixture
    def temp_db(self):
        """Создание временной БД для тестов."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.remove(path)

    @pytest.fixture
    def connection(self, temp_db):
        """Создание подключения для тестов."""
        conn = SQLAlchemyConnection(f"sqlite:///{temp_db}")
        conn.connect()
        # Создаем минимальную схему для тестов с использованием SQLAlchemy моделей
        from database.sqlalchemy_models import Base

        engine = conn.engine
        Base.metadata.create_all(engine)
        yield conn
        conn.disconnect()

    def test_connect_disconnect(self, temp_db):
        """Тест подключения и отключения."""
        conn = SQLAlchemyConnection(f"sqlite:///{temp_db}")
        assert not conn.is_connected

        conn.connect()
        assert conn.is_connected

        conn.disconnect()
        assert not conn.is_connected

    def test_execute_query(self, connection):
        """Тест выполнения SQL запроса."""
        from datetime import datetime

        now = datetime.utcnow().isoformat()
        # Используем полный набор полей для совместимости с SQLAlchemy моделью
        cursor = connection.execute(
            "INSERT INTO clients (name, phone, status, total_orders, completed_orders, total_spent, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("Тестовый клиент", "+79991234567", "Новый", 0, 0, 0.0, now, now),
        )
        connection.commit()

        cursor = connection.execute(
            "SELECT * FROM clients WHERE phone = ?", ("+79991234567",)
        )
        row = cursor.fetchone()
        assert row is not None
        assert row._mapping["name"] == "Тестовый клиент"

    def test_transaction_commit(self, connection):
        """Тест фиксации транзакции."""
        from datetime import datetime

        from sqlalchemy import text

        now = datetime.utcnow().isoformat()
        with connection.transaction() as sess:
            sess.execute(
                text(
                    "INSERT INTO clients (name, phone, status, total_orders, completed_orders, total_spent, created_at, updated_at) VALUES (:param_0, :param_1, :param_2, :param_3, :param_4, :param_5, :param_6, :param_7)"
                ),
                {
                    "param_0": "Клиент 1",
                    "param_1": "+79991111111",
                    "param_2": "Новый",
                    "param_3": 0,
                    "param_4": 0,
                    "param_5": 0.0,
                    "param_6": now,
                    "param_7": now,
                },
            )

        # Проверяем что данные закоммичены
        cursor = connection.execute("SELECT COUNT(*) FROM clients")
        count = cursor.fetchone()[0]
        assert count >= 1

    def test_transaction_rollback(self, connection):
        """Тест отката транзакции."""
        from datetime import datetime

        from sqlalchemy import text

        # Получаем начальное количество записей
        cursor = connection.execute("SELECT COUNT(*) FROM clients")
        initial_count = cursor.fetchone()[0]

        try:
            with connection.transaction() as sess:
                now = datetime.utcnow().isoformat()
                sess.execute(
                    text(
                        "INSERT INTO clients (name, phone, status, total_orders, completed_orders, total_spent, created_at, updated_at) VALUES (:param_0, :param_1, :param_2, :param_3, :param_4, :param_5, :param_6, :param_7)"
                    ),
                    {
                        "param_0": "Клиент для отката",
                        "param_1": "+79992222222",
                        "param_2": "Новый",
                        "param_3": 0,
                        "param_4": 0,
                        "param_5": 0.0,
                        "param_6": now,
                        "param_7": now,
                    },
                )
                raise ValueError("Искусственная ошибка")
        except ValueError:
            pass  # Ожидаемая ошибка

        # Проверяем что данные откачены
        cursor = connection.execute("SELECT COUNT(*) FROM clients")
        count = cursor.fetchone()[0]
        assert count == initial_count


class TestDeviceRepository:
    """Тесты репозитория устройств."""

    @pytest.fixture
    def device_repo(self):
        """Создание репозитория для тестов."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

        conn = SQLAlchemyConnection(f"sqlite:///{path}")
        conn.connect()

        # Создаем схему с использованием SQLAlchemy моделей
        from database.sqlalchemy_models import Base

        engine = conn.engine
        Base.metadata.create_all(engine)

        repo = DeviceRepository(conn)
        yield repo

        conn.disconnect()
        if os.path.exists(path):
            os.remove(path)

    def test_create_device(self, device_repo):
        """Тест создания устройства."""
        device_data = {
            "order_number": "ORD-001",
            "client_name": "Иван Иванов",
            "phone": "+79991234567",
            "device_type": "Смартфон",
            "brand": "Apple",
            "model": "iPhone 13",
            "status": "Диагностика",
            "total_price": "5000",
        }

        device = device_repo.create(device_data)

        assert device is not None
        assert device.order_number == "ORD-001"
        assert device.client_name == "Иван Иванов"

    def test_get_device(self, device_repo):
        """Тест получения устройства по ID."""
        device_data = {
            "order_number": "ORD-002",
            "client_name": "Петр Петров",
            "phone": "+79997654321",
            "status": "В работе",
        }

        created = device_repo.create(device_data)
        retrieved = device_repo.get(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.client_name == "Петр Петров"

    def test_get_by_order_number(self, device_repo):
        """Тест получения устройства по номеру заказа."""
        device_data = {
            "order_number": "ORD-003",
            "client_name": "Сидор Сидоров",
        }

        device_repo.create(device_data)
        retrieved = device_repo.get_by_order_number("ORD-003")

        assert retrieved is not None
        assert retrieved.client_name == "Сидор Сидоров"

    def test_update_device(self, device_repo):
        """Тест обновления устройства."""
        device_data = {
            "order_number": "ORD-004",
            "client_name": "Анна Анна",
            "status": "Диагностика",
        }

        created = device_repo.create(device_data)
        updated = device_repo.update(created.id, {"status": "Готов"})

        assert updated is not None
        assert updated.status == "Готов"

    def test_delete_device(self, device_repo):
        """Тест удаления устройства."""
        device_data = {
            "order_number": "ORD-005",
            "client_name": "Борис Борис",
        }

        created = device_repo.create(device_data)
        deleted = device_repo.delete(created.id)

        assert deleted is True
        assert device_repo.get(created.id) is None

    def test_count_devices(self, device_repo):
        """Тест подсчета устройств."""
        for i in range(5):
            device_repo.create(
                {
                    "order_number": f"ORD-00{i}",
                    "client_name": f"Клиент {i}",
                }
            )

        count = device_repo.count()
        assert count == 5

    def test_search_devices(self, device_repo):
        """Тест поиска устройств."""
        device_repo.create(
            {
                "order_number": "ORD-100",
                "client_name": "Иван Иванов",
                "phone": "+79991234567",
                "brand": "Samsung",
            }
        )

        results = device_repo.search("Иван")
        assert len(results) == 1
        assert results[0].client_name == "Иван Иванов"

        results = device_repo.search("Samsung")
        assert len(results) == 1


class TestClientRepository:
    """Тесты репозитория клиентов."""

    @pytest.fixture
    def client_repo(self):
        """Создание репозитория для тестов."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

        conn = SQLAlchemyConnection(f"sqlite:///{path}")
        conn.connect()

        # Создаем схему с использованием SQLAlchemy моделей
        from database.sqlalchemy_models import Base

        engine = conn.engine
        Base.metadata.create_all(engine)

        repo = ClientRepository(conn)
        yield repo

        conn.disconnect()
        if os.path.exists(path):
            os.remove(path)

    def test_create_client(self, client_repo):
        """Тест создания клиента."""
        client_data = {
            "name": "Тест Клиент",
            "phone": "+79991112233",
        }

        client = client_repo.create(client_data)

        assert client is not None
        assert client["name"] == "Тест Клиент"

    def test_get_by_phone(self, client_repo):
        """Тест получения клиента по телефону."""
        client_repo.create(
            {
                "name": "Телефонный клиент",
                "phone": "+79995556677",
            }
        )

        client = client_repo.get_by_phone("+79995556677")

        assert client is not None
        assert client["name"] == "Телефонный клиент"

    def test_search_clients(self, client_repo):
        """Тест поиска клиентов."""
        client_repo.create(
            {
                "name": "Поисковый клиент",
                "phone": "+79998889900",
            }
        )

        results = client_repo.search("Поисковый")
        assert len(results) == 1


class TestUnitOfWork:
    """Тесты Unit of Work паттерна."""

    @pytest.fixture
    def uow_setup(self):
        """Настройка для тестов Unit of Work."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

        conn = SQLAlchemyConnection(f"sqlite:///{path}")
        conn.connect()

        # Создаем схему с использованием SQLAlchemy моделей
        from database.sqlalchemy_models import Base

        engine = conn.engine
        Base.metadata.create_all(engine)

        uow = UnitOfWork(conn)
        yield uow, conn, path

        conn.disconnect()
        if os.path.exists(path):
            os.remove(path)

    def test_unit_of_work_commit(self, uow_setup):
        """Тест фиксации транзакции через Unit of Work."""
        uow, _conn, _ = uow_setup

        with uow:
            uow.clients.create(
                {
                    "name": "UOW Клиент",
                    "phone": "+79990001111",
                }
            )

        # Проверяем что клиент создан
        retrieved = uow.clients.get_by_phone("+79990001111")
        assert retrieved is not None
        assert retrieved["name"] == "UOW Клиент"

    def test_unit_of_work_rollback(self, uow_setup):
        """Тест отката транзакции через Unit of Work."""
        uow, conn, _ = uow_setup

        # Получаем начальное количество клиентов
        cursor = conn.execute("SELECT COUNT(*) FROM clients")
        initial_count = cursor.fetchone()[0]

        try:
            with uow:
                uow.clients.create(
                    {
                        "name": "Клиент для отката",
                        "phone": "+79990002222",
                    }
                )
                raise ValueError("Искусственная ошибка для отката")
        except ValueError:
            pass

        # Проверяем что транзакция откачена
        cursor = conn.execute("SELECT COUNT(*) FROM clients")
        count = cursor.fetchone()[0]
        assert count == initial_count

    def test_unit_of_work_lazy_loading(self, uow_setup):
        """Тест ленивой инициализации репозиториев."""
        uow, _, _ = uow_setup

        # Репозитории не созданы до первого обращения
        assert uow._devices is None
        assert uow._clients is None

        # Обращение к devices создает только DeviceRepository
        _ = uow.devices
        assert uow._devices is not None
        assert uow._clients is None

        # Обращение к clients создает ClientRepository
        _ = uow.clients
        assert uow._clients is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
