"""Конкретная реализация IClientRepository поверх database.sqlalchemy_models.Client.

Делает plugins/clients реально работающим плагином (не заглушкой): резолвится
через Kernel DI (см. bootstrap.initialize_kernel), использует ту же SQLite/
Postgres БД, что и остальное приложение (database/engines).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import or_, select

from database.sqlalchemy_models import Client
from plugins.clients import ClientEntity, IClientRepository

if TYPE_CHECKING:
    from database.engines.base import IDatabaseEngine


def _to_entity(client: Client) -> ClientEntity:
    return ClientEntity(
        id=client.id,
        full_name=client.name,
        phone=client.phone,
        email=client.email,
        address=None,  # Client не хранит адрес — вне текущей схемы приложения
        created_at=client.created_at,
        updated_at=client.updated_at,
        notes=client.notes or "",
        is_active=True,  # в схеме нет отдельного флага активности клиента
        orders_count=client.total_orders,
        total_spent=str(client.total_spent),
    )


class SqlAlchemyClientRepository(IClientRepository):
    """Репозиторий клиентов на SQLAlchemy — реализация для plugins/clients."""

    def __init__(self, db_engine: IDatabaseEngine):
        self._engine = db_engine

    def get_by_id(self, client_id: int) -> ClientEntity | None:
        with self._engine.get_session() as s:
            client = s.get(Client, client_id)
            return _to_entity(client) if client else None

    def get_by_phone(self, phone: str) -> ClientEntity | None:
        with self._engine.get_session() as s:
            client = s.execute(
                select(Client).where(Client.phone == phone)
            ).scalar_one_or_none()
            return _to_entity(client) if client else None

    def get_by_email(self, email: str) -> ClientEntity | None:
        with self._engine.get_session() as s:
            client = s.execute(
                select(Client).where(Client.email == email)
            ).scalar_one_or_none()
            return _to_entity(client) if client else None

    def get_all(self, limit: int = 100, active_only: bool = True) -> list[ClientEntity]:
        with self._engine.get_session() as s:
            rows = s.execute(select(Client).limit(limit)).scalars().all()
            return [_to_entity(c) for c in rows]

    def save(self, client: ClientEntity) -> bool:
        try:
            with self._engine.get_session() as s:
                if client.id:
                    row = s.get(Client, client.id)
                else:
                    row = None
                if row is None:
                    row = Client(name=client.full_name, phone=client.phone)
                    s.add(row)
                row.name = client.full_name
                row.phone = client.phone
                row.email = client.email
                row.notes = client.notes
                s.commit()
                client.id = row.id
                return True
        except Exception:
            return False

    def delete(self, client_id: int, hard: bool = False) -> bool:
        """Soft-delete не поддерживается схемой (нет флага is_active на Client) —
        выполняется полное удаление независимо от hard."""
        try:
            with self._engine.get_session() as s:
                row = s.get(Client, client_id)
                if row is None:
                    return False
                s.delete(row)
                s.commit()
                return True
        except Exception:
            return False

    def search(
        self, query: str, limit: int = 50, active_only: bool = True
    ) -> list[ClientEntity]:
        needle = f"%{query}%"
        with self._engine.get_session() as s:
            rows = s.execute(
                select(Client)
                .where(or_(Client.name.ilike(needle), Client.phone.ilike(needle)))
                .limit(limit)
            ).scalars().all()
            return [_to_entity(c) for c in rows]

    def get_with_order_history(
        self, min_orders: int = 1, limit: int = 100
    ) -> list[ClientEntity]:
        with self._engine.get_session() as s:
            rows = s.execute(
                select(Client).where(Client.total_orders >= min_orders).limit(limit)
            ).scalars().all()
            return [_to_entity(c) for c in rows]
