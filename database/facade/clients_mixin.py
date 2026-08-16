#!/usr/bin/env python3
"""ClientsMixin — клиенты и объединённая история ремонтов
(repair_history_main). См. AUDIT_REPORT_v25.md, Task T."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import case, func, select

from database.facade.shared import logger
from database.sqlalchemy_models import Client, RepairHistoryMain
from domain.constants import STATUS_ISSUED as _ISSUED_STATUS
from utils.formatters import normalize_phone_digits

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class ClientsMixin:
    """Требует self._session() от финального класса Database."""

    def get_or_create_client(
        self, name: str, phone: str, status: str = "Новый"
    ) -> int | None:
        try:
            with self._session() as s:
                client = s.execute(
                    select(Client).where(Client.phone == phone)
                ).scalar_one_or_none()
                if client is not None:
                    return client.id
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                client = Client(
                    name=name, phone=phone, status=status,
                    first_order_date=now, last_order_date=now,
                )
                s.add(client)
                s.commit()
                return client.id
        except Exception as e:
            logger.error(f"Ошибка get_or_create_client: {e}", exc_info=True)
            return None

    def add_to_repair_history_main(
        self, client_id: int, device_id: int, device_data: dict[str, Any]
    ) -> None:
        try:
            with self._session() as s:
                order_number = device_data.get("order_number", "")
                record = s.execute(
                    select(RepairHistoryMain).where(
                        RepairHistoryMain.client_id == client_id,
                        RepairHistoryMain.order_number == order_number,
                    )
                ).scalar_one_or_none()
                if record is None:
                    record = RepairHistoryMain(client_id=client_id, order_number=order_number)
                    s.add(record)
                record.device_id = device_id
                record.receipt_date = device_data.get("receipt_date", "")
                record.completion_date = device_data.get("completion_date", "")
                record.device_type = device_data.get("device_type", "")
                record.brand = device_data.get("brand", "")
                record.model = device_data.get("model", "")
                record.serial_number = device_data.get("serial_number", "")
                record.defect = device_data.get("defect", "")
                record.work_items = device_data.get("work_items_json", "")
                record.status = device_data.get("status", "")
                record.total_price = device_data.get("total_price", "")
                record.engineer = device_data.get("engineer", "")
                record.warranty = device_data.get("warranty", "")
                record.notes = device_data.get("notes", "")
                record.photos = device_data.get("photos", "")
                s.flush()
                self._recalc_client_stats(s, client_id)
                s.commit()
        except Exception as e:
            logger.error(f"Ошибка add_to_repair_history_main: {e}", exc_info=True)

    @staticmethod
    def _recalc_client_stats(s: Session, client_id: int) -> None:
        completed_case = case((RepairHistoryMain.status == _ISSUED_STATUS, 1), else_=0)
        total, completed, first_date, last_date = s.execute(
            select(
                func.count(RepairHistoryMain.id),
                func.coalesce(func.sum(completed_case), 0),
                func.min(RepairHistoryMain.receipt_date),
                func.max(RepairHistoryMain.receipt_date),
            ).where(RepairHistoryMain.client_id == client_id)
        ).one()
        client = s.get(Client, client_id)
        if client is None:
            return
        client.total_orders = total or 0
        client.completed_orders = completed or 0
        client.first_order_date = first_date
        client.last_order_date = last_date

    def get_client_history_main(
        self, client_name: str, client_phone: str
    ) -> list[dict[str, Any]]:
        with self._session() as s:
            phone_digits = normalize_phone_digits(client_phone)
            if len(phone_digits) >= 10:
                last10 = phone_digits[-10:]
                clients = s.execute(select(Client)).scalars().all()
                matching_ids = [
                    c.id for c in clients
                    if normalize_phone_digits(c.phone).endswith(last10)
                ]
                if not matching_ids:
                    return []
                stmt = (
                    select(RepairHistoryMain)
                    .where(RepairHistoryMain.client_id.in_(matching_ids))
                    .order_by(RepairHistoryMain.receipt_date.desc())
                )
            else:
                client = s.execute(
                    select(Client).where(
                        (Client.name == client_name) | (Client.phone == client_phone)
                    )
                ).scalar_one_or_none()
                if client is None:
                    return []
                stmt = (
                    select(RepairHistoryMain)
                    .where(RepairHistoryMain.client_id == client.id)
                    .order_by(RepairHistoryMain.receipt_date.desc())
                )
            rows = s.execute(stmt).scalars().all()
            return [
                {
                    "id": r.id,
                    "client_id": r.client_id,
                    "device_id": r.device_id,
                    "order_number": r.order_number,
                    "receipt_date": r.receipt_date,
                    "completion_date": r.completion_date,
                    "device_type": r.device_type,
                    "brand": r.brand,
                    "model": r.model,
                    "serial_number": r.serial_number,
                    "defect": r.defect,
                    "work_items": r.work_items,
                    "status": r.status,
                    "total_price": r.total_price,
                    "engineer": r.engineer,
                    "warranty": r.warranty,
                    "notes": r.notes,
                    "photos": r.photos,
                }
                for r in rows
            ]

    def get_client_stats_main(
        self, client_name: str, client_phone: str
    ) -> dict[str, Any]:
        with self._session() as s:
            client = s.execute(
                select(Client).where(
                    Client.name == client_name, Client.phone == client_phone
                )
            ).scalar_one_or_none()
            if client is None:
                return {}
            return {
                "id": client.id,
                "name": client.name,
                "phone": client.phone,
                "status": client.status,
                "total_orders": client.total_orders,
                "completed_orders": client.completed_orders,
                "total_spent": client.total_spent,
                "first_order_date": client.first_order_date,
                "last_order_date": client.last_order_date,
                "favorite_device": client.favorite_device,
            }

    def migrate_client_dbs(self) -> int:
        """Миграция legacy DBClients/*.db в основную БД.

        Делегирует проверенной реализации database.db_manager.Database —
        она читает per-client .db файлы через сырой sqlite3 и пишет в те же
        таблицы clients/repair_history_main, что использует и этот facade
        (общая физическая SQLite БД под capital SQLAlchemy-моделями).
        """
        from database.db_config import get_db_config
        from database.db_manager import Database as _LegacyDatabase

        legacy = _LegacyDatabase(get_db_config().database)
        try:
            return legacy.migrate_client_dbs()
        finally:
            legacy.close() if hasattr(legacy, "close") else None
