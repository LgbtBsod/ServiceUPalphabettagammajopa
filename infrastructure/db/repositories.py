"""Database repositories - реализации репозиториев для работы с SQLite.

Использует SQLAlchemy для ORM и следует паттерну Repository.
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager, suppress
from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from domain.entities import Client, Device, OrderStatus, Photo, Priority, WorkItem

logger = logging.getLogger(__name__)

T = TypeVar("T")


class DatabaseConnection:
    """Управление подключением к базе данных.

    Реализует singleton pattern для подключения.
    Использует WAL mode для лучшей производительности.
    """

    _instance: DatabaseConnection | None = None

    def __new__(cls, db_path: str = ":memory:"):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str = ":memory:"):
        if self._initialized:
            return

        self._db_path = db_path
        self._engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            future=True,
            connect_args={"timeout": 30},
        )

        # Настройка PRAGMA для SQLite
        @event.listens_for(self._engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=-6400")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        self._session_factory = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

        self._initialized = True
        logger.info(f"Подключение к БД: {db_path}")

    @property
    def engine(self):
        return self._engine

    @contextmanager
    def get_session(self) -> Session:
        """Получение сессии БД (context manager)."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


class BaseRepository[T]:
    """Базовый класс репозитория."""

    def __init__(self, session: Session):
        self._session = session


class DeviceRepository(BaseRepository[Device]):
    """Репозиторий для работы с устройствами/заказами.

    Реализует CRUD операции и поиск.
    """

    def get(self, order_id: int) -> Device | None:
        """Получение заказа по ID."""
        # TODO: Реализация через SQLAlchemy models
        # Пока используем raw SQL для совместимости
        query = text("SELECT * FROM devices WHERE id = :id")
        result = self._session.execute(query, {"id": order_id}).fetchone()

        if not result:
            return None

        return self._row_to_device(result)

    def get_by_order_number(self, order_number: str) -> Device | None:
        """Получение заказа по номеру."""
        query = text("SELECT * FROM devices WHERE order_number = :order_number")
        result = self._session.execute(query, {"order_number": order_number}).fetchone()

        if not result:
            return None

        return self._row_to_device(result)

    def get_all(self, filters: dict[str, Any] | None = None) -> list[Device]:
        """Получение всех заказов с фильтрацией."""
        query = "SELECT * FROM devices WHERE 1=1"
        params = {}

        if filters:
            if "status" in filters:
                query += " AND status = :status"
                params["status"] = filters["status"]

            if "client_name" in filters:
                query += " AND client_name LIKE :client_name"
                params["client_name"] = f"%{filters['client_name']}%"

            if "phone" in filters:
                query += " AND phone LIKE :phone"
                params["phone"] = f"%{filters['phone']}%"

            if "device_type" in filters:
                query += " AND device_type = :device_type"
                params["device_type"] = filters["device_type"]

            if "brand" in filters:
                query += " AND brand = :brand"
                params["brand"] = filters["brand"]

            if "priority" in filters:
                query += " AND priority = :priority"
                params["priority"] = filters["priority"]

            if "date_from" in filters:
                query += " AND receipt_date >= :date_from"
                params["date_from"] = filters["date_from"]

            if "date_to" in filters:
                query += " AND receipt_date <= :date_to"
                params["date_to"] = filters["date_to"]

        query += " ORDER BY created_at DESC"

        results = self._session.execute(text(query), params).fetchall()
        return [self._row_to_device(row) for row in results]

    def save(self, device: Device) -> Device:
        """Сохранение заказа (create or update)."""
        data = device.to_dict()

        # Сериализация сложных полей
        data["work_items"] = json.dumps([wi.to_dict() for wi in device.work_items])
        data["photos"] = json.dumps([p.to_dict() for p in device.photos])
        data["status"] = device.status.value
        data["priority"] = device.priority.value

        if device.receipt_date:
            data["receipt_date"] = device.receipt_date.isoformat()
        if device.completion_date:
            data["completion_date"] = device.completion_date.isoformat()
        if device.created_at:
            data["created_at"] = device.created_at.isoformat()

        if device.id:
            # Update
            self._update(device.id, data)
        else:
            # Insert
            device.id = self._insert(data)

        return device

    def delete(self, order_id: int) -> bool:
        """Удаление заказа."""
        try:
            query = text("DELETE FROM devices WHERE id = :id")
            self._session.execute(query, {"id": order_id})
            return True
        except Exception as e:
            logger.exception(f"Ошибка удаления заказа: {e}")
            return False

    def search(self, query: str) -> list[Device]:
        """Поиск заказов по строке."""
        search_pattern = f"%{query}%"
        sql = text("""
            SELECT * FROM devices
            WHERE client_name LIKE :pattern
               OR phone LIKE :pattern
               OR order_number LIKE :pattern
               OR brand LIKE :pattern
               OR model LIKE :pattern
            ORDER BY created_at DESC
        """)

        results = self._session.execute(sql, {"pattern": search_pattern}).fetchall()
        return [self._row_to_device(row) for row in results]

    def get_next_order_number(self) -> int:
        """Получение следующего номера заказа."""
        # Используем существующую логику из counters таблицы
        query = text("SELECT value FROM counters WHERE name = 'order_counter'")
        result = self._session.execute(query).fetchone()
        current = result["value"] if result else 1

        # Инкремент
        update_query = text(
            "UPDATE counters SET value = value + 1 WHERE name = 'order_counter'"
        )
        self._session.execute(update_query)

        return current

    def _insert(self, data: dict[str, Any]) -> int:
        """Вставка новой записи."""
        columns = ", ".join(data.keys())
        placeholders = ", ".join(f":{k}" for k in data)
        query = text(f"""
            INSERT INTO devices ({columns}) VALUES ({placeholders})
            RETURNING id
        """)

        result = self._session.execute(query, data).fetchone()
        return result["id"] if result else 0

    def _update(self, order_id: int, data: dict[str, Any]) -> None:
        """Обновление существующей записи."""
        sets = ", ".join(f"{k} = :{k}" for k in data)
        query = text(f"""
            UPDATE devices SET {sets} WHERE id = :id
        """)

        data_with_id = dict(data, id=order_id)
        self._session.execute(query, data_with_id)

    def _row_to_device(self, row) -> Device:
        """Преобразование строки БД в сущность Device."""
        # Получаем данные из row (sqlite3.Row или namedtuple)
        row_dict = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)

        # Парсинг JSON полей
        work_items = []
        if row_dict.get("work_items"):
            try:
                wi_data = json.loads(row_dict["work_items"])
                work_items = [WorkItem.from_dict(wi) for wi in wi_data]
            except json.JSONDecodeError, KeyError:
                pass

        photos = []
        if row_dict.get("photos"):
            try:
                photo_data = json.loads(row_dict["photos"])
                photos = [Photo.from_dict(p) for p in photo_data]
            except json.JSONDecodeError, KeyError:
                pass

        # Парсинг дат
        receipt_date = None
        if row_dict.get("receipt_date"):
            with suppress(ValueError, TypeError):
                receipt_date = datetime.fromisoformat(row_dict["receipt_date"])

        completion_date = None
        if row_dict.get("completion_date"):
            with suppress(ValueError, TypeError):
                completion_date = datetime.fromisoformat(row_dict["completion_date"])

        created_at = datetime.now()
        if row_dict.get("created_at"):
            with suppress(ValueError, TypeError):
                created_at = datetime.fromisoformat(row_dict["created_at"])

        return Device(
            id=row_dict.get("id"),
            order_number=row_dict.get("order_number"),
            receipt_date=receipt_date or datetime.now(),
            completion_date=completion_date,
            device_type=row_dict.get("device_type", ""),
            brand=row_dict.get("brand", ""),
            model=row_dict.get("model", ""),
            serial_number=row_dict.get("serial_number", ""),
            defect=row_dict.get("defect", ""),
            appearance=row_dict.get("appearance", ""),
            completeness=row_dict.get("completeness", ""),
            work_items=work_items,
            client_name=row_dict.get("client_name", ""),
            client_status=row_dict.get("client_status", "Новый"),
            phone=row_dict.get("phone", ""),
            total_price=float(
                row_dict.get("total_price_num") or row_dict.get("total_price") or 0
            ),
            prepayment=float(
                row_dict.get("prepayment_num") or row_dict.get("prepayment") or 0
            ),
            status=OrderStatus(row_dict.get("status", "Диагностика")),
            priority=Priority(row_dict.get("priority", "Обычный")),
            engineer=row_dict.get("engineer", ""),
            warranty=row_dict.get("warranty", ""),
            notes=row_dict.get("notes", ""),
            photos=photos,
            expense=float(row_dict.get("expense_num") or row_dict.get("expense") or 0),
            created_at=created_at,
        )


class ClientRepository(BaseRepository[Client]):
    """Репозиторий для работы с клиентами."""

    def get(self, client_id: int) -> Client | None:
        """Получение клиента по ID."""
        query = text("SELECT * FROM clients WHERE id = :id")
        result = self._session.execute(query, {"id": client_id}).fetchone()

        if not result:
            return None

        return self._row_to_client(result)

    def get_by_phone(self, phone: str) -> Client | None:
        """Получение клиента по телефону."""
        query = text("SELECT * FROM clients WHERE phone = :phone")
        result = self._session.execute(query, {"phone": phone}).fetchone()

        if not result:
            return None

        return self._row_to_client(result)

    def get_all(self) -> list[Client]:
        """Получение всех клиентов."""
        query = text("SELECT * FROM clients ORDER BY created_at DESC")
        results = self._session.execute(query).fetchall()
        return [self._row_to_client(row) for row in results]

    def save(self, client: Client) -> Client:
        """Сохранение клиента."""
        data = client.to_dict()

        if client.first_order_date:
            data["first_order_date"] = client.first_order_date.isoformat()
        if client.last_order_date:
            data["last_order_date"] = client.last_order_date.isoformat()
        if client.created_at:
            data["created_at"] = client.created_at.isoformat()

        if client.id:
            self._update(client.id, data)
        else:
            client.id = self._insert(data)

        return client

    def delete(self, client_id: int) -> bool:
        """Удаление клиента."""
        try:
            query = text("DELETE FROM clients WHERE id = :id")
            self._session.execute(query, {"id": client_id})
            return True
        except Exception as e:
            logger.exception(f"Ошибка удаления клиента: {e}")
            return False

    def search(self, query: str) -> list[Client]:
        """Поиск клиентов."""
        search_pattern = f"%{query}%"
        sql = text("""
            SELECT * FROM clients
            WHERE name LIKE :pattern OR phone LIKE :pattern
            ORDER BY created_at DESC
        """)

        results = self._session.execute(sql, {"pattern": search_pattern}).fetchall()
        return [self._row_to_client(row) for row in results]

    def _insert(self, data: dict[str, Any]) -> int:
        """Вставка нового клиента."""
        columns = ", ".join(data.keys())
        placeholders = ", ".join(f":{k}" for k in data)
        query = text(f"""
            INSERT INTO clients ({columns}) VALUES ({placeholders})
            RETURNING id
        """)

        result = self._session.execute(query, data).fetchone()
        return result["id"] if result else 0

    def _update(self, client_id: int, data: dict[str, Any]) -> None:
        """Обновление клиента."""
        sets = ", ".join(f"{k} = :{k}" for k in data)
        query = text(f"""
            UPDATE clients SET {sets} WHERE id = :id
        """)

        data_with_id = dict(data, id=client_id)
        self._session.execute(query, data_with_id)

    def _row_to_client(self, row) -> Client:
        """Преобразование строки БД в сущность Client."""
        row_dict = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)

        first_order_date = None
        if row_dict.get("first_order_date"):
            with suppress(ValueError, TypeError):
                first_order_date = datetime.fromisoformat(row_dict["first_order_date"])

        last_order_date = None
        if row_dict.get("last_order_date"):
            with suppress(ValueError, TypeError):
                last_order_date = datetime.fromisoformat(row_dict["last_order_date"])

        created_at = datetime.now()
        if row_dict.get("created_at"):
            with suppress(ValueError, TypeError):
                created_at = datetime.fromisoformat(row_dict["created_at"])

        return Client(
            id=row_dict.get("id"),
            name=row_dict.get("name", ""),
            phone=row_dict.get("phone", ""),
            status=row_dict.get("status", "Новый"),
            total_orders=int(row_dict.get("total_orders", 0)),
            completed_orders=int(row_dict.get("completed_orders", 0)),
            total_spent=float(row_dict.get("total_spent", 0)),
            first_order_date=first_order_date,
            last_order_date=last_order_date,
            favorite_device=row_dict.get("favorite_device", ""),
            created_at=created_at,
        )


class UnitOfWork:
    """Unit of Work - управление транзакциями.

    Гарантирует атомарность операций и согласованность данных.
    """

    def __init__(self, db_connection: DatabaseConnection):
        self._db = db_connection
        self._device_repo: DeviceRepository | None = None
        self._client_repo: ClientRepository | None = None

    @contextmanager
    def __call__(self):
        """Контекст менеджера для транзакции."""
        with self._db.get_session() as session:
            self._device_repo = DeviceRepository(session)
            self._client_repo = ClientRepository(session)

            try:
                yield self
                session.commit()
            except Exception:
                session.rollback()
                raise

    @property
    def devices(self) -> DeviceRepository:
        if self._device_repo is None:
            raise RuntimeError(
                "UnitOfWork не инициализирован. Используйте контекстный менеджер."
            )
        return self._device_repo

    @property
    def clients(self) -> ClientRepository:
        if self._client_repo is None:
            raise RuntimeError(
                "UnitOfWork не инициализирован. Используйте контекстный менеджер."
            )
        return self._client_repo
