#!/usr/bin/env python3
"""SQLAlchemy-backed drop-in замена database.db_manager.Database.

Тот же публичный API (имена и сигнатуры методов, форма возвращаемых
словарей), что и у легаси-класса на сыром sqlite3 — но персистентность
идёт через IDatabaseEngine (database/engines/), выбираемый по DB_TYPE.
Это позволяет gui/main_window.py и pwa/server.py получать этот класс
через Kernel DI без единой правки в местах вызова self.db.method(...).

Также добавляет Calculation Offloading: calculate(name, **params) — тяжёлые
агрегации (просроченные заказы, статистика дашборда) считает SQL, а не Python.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import case, func, select

from database.sqlalchemy_models import (
    Client,
    CompletedRepair,
    Counter,
    DictionaryItem,
    FinanceRecord,
    RepairHistoryMain,
)
from database.sqlalchemy_models import Device as DeviceModel
from utils.formatters import normalize_phone_digits, parse_price_to_float

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from database.engines.base import IDatabaseEngine

logger = logging.getLogger(__name__)

_ISSUED_STATUS = "Выдан клиенту"
_REFUSED_STATUS = "Отказ от ремонта"
_READY_STATUS = "Готов к выдаче"
_CLOSED_STATUSES = (_ISSUED_STATUS, _REFUSED_STATUS)
OVERDUE_THRESHOLD_DAYS = 14


def _fmt_money(value: float | None) -> str:
    """Форматирует число в строку для полей, которые в legacy-схеме были TEXT.

    Сохраняет обратную совместимость с кодом, ожидающим device['total_price']
    как строку (например device_form.py вызывает parse_price_to_float на ней).
    """
    if value is None:
        return ""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}"


def _device_to_row(device: DeviceModel) -> dict[str, Any]:
    """Device -> dict в форме legacy-строки таблицы `devices`."""
    return {
        "id": device.id,
        "order_number": device.order_number,
        "receipt_date": device.receipt_date,
        "completion_date": device.completion_date,
        "device_type": device.device_type,
        "brand": device.brand,
        "model": device.model,
        "serial_number": device.serial_number,
        "defect": device.defect,
        "appearance": device.appearance,
        "completeness": device.completeness,
        "work_items": device.work_items,
        "client_name": device.client_name,
        "client_status": device.client_status,
        "phone": device.phone,
        "total_price": _fmt_money(device.total_price),
        "prepayment": _fmt_money(device.prepayment),
        "total_price_num": device.total_price or 0.0,
        "prepayment_num": device.prepayment or 0.0,
        "expense_num": parse_price_to_float(device.expense or "0"),
        "status": device.status,
        "priority": device.priority,
        "engineer": device.engineer,
        "warranty": device.warranty,
        "notes": device.notes,
        "photos": device.photos,
        "expense": device.expense,
        "created_at": device.created_at.isoformat() if device.created_at else None,
    }


class Database:
    """Drop-in замена database.db_manager.Database на SQLAlchemy."""

    def __init__(self, db_engine: IDatabaseEngine | None = None):
        if db_engine is None:
            from database.engines import get_database_engine

            db_engine = get_database_engine()
        self._engine = db_engine
        self._engine.create_tables()
        self._dict_cache: dict[str, list[str]] = {}

    @property
    def engine(self) -> IDatabaseEngine:
        """Публичный доступ к движку — нужен, например, плагинам, которым
        требуется своя SQLAlchemy-сессия (см. plugins/clients/repository.py)."""
        return self._engine

    def _session(self) -> Session:
        return self._engine.get_session()

    def close(self) -> None:
        """Совместимость с legacy API — сессии открываются и закрываются
        по одной на вызов, отдельного постоянного соединения нет."""

    # ==================== СЧЁТЧИКИ / НОМЕРА ЗАКАЗОВ ====================

    def get_next_order_number(self) -> int:
        with self._session() as s:
            counter = s.execute(
                select(Counter).where(Counter.name == "order_counter")
            ).scalar_one_or_none()
            if counter is None:
                counter = Counter(name="order_counter", value=1)
                s.add(counter)
                s.flush()
            current = counter.value
            counter.value = current + 1
            s.commit()
            return current

    def peek_next_order_number(self) -> int:
        """Возвращает следующий номер заказа БЕЗ инкремента счётчика — для
        превью в UI (например, заголовок формы нового устройства). Раньше
        для этого GUI лез в self.db.conn.cursor() напрямую, чего у этого
        facade нет — AttributeError гасился bare except и номер всегда
        показывался как '???' (см. AUDIT_REPORT_v21.md)."""
        with self._session() as s:
            counter = s.execute(
                select(Counter).where(Counter.name == "order_counter")
            ).scalar_one_or_none()
            return counter.value if counter is not None else 1

    # ==================== СЛОВАРИ ====================

    def get_dict_values(self, dict_type: str) -> list[str]:
        if dict_type in self._dict_cache:
            return self._dict_cache[dict_type]
        with self._session() as s:
            rows = s.execute(
                select(DictionaryItem.value)
                .where(DictionaryItem.dict_type == dict_type)
                .order_by(DictionaryItem.sort_order)
            ).scalars().all()
            values = list(rows)
            self._dict_cache[dict_type] = values
            return values

    def _invalidate_dict_cache(self, dict_type: str | None = None) -> None:
        if dict_type:
            self._dict_cache.pop(dict_type, None)
        else:
            self._dict_cache.clear()

    def get_all_dict_items(self, dict_type: str) -> list[dict[str, Any]]:
        with self._session() as s:
            rows = s.execute(
                select(DictionaryItem)
                .where(DictionaryItem.dict_type == dict_type)
                .order_by(DictionaryItem.sort_order)
            ).scalars().all()
            return [
                {
                    "id": r.id,
                    "value": r.value,
                    "sort_order": r.sort_order,
                    "additional_info": r.additional_info,
                }
                for r in rows
            ]

    def add_dict_value(
        self, dict_type: str, value: str, additional_info: str = ""
    ) -> bool:
        try:
            with self._session() as s:
                max_order = s.execute(
                    select(func.max(DictionaryItem.sort_order)).where(
                        DictionaryItem.dict_type == dict_type
                    )
                ).scalar()
                item = DictionaryItem(
                    dict_type=dict_type,
                    value=value,
                    sort_order=(max_order or 0) + 1,
                    additional_info=additional_info,
                )
                s.add(item)
                s.commit()
            self._invalidate_dict_cache(dict_type)
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления в словарь: {e}", exc_info=True)
            return False

    def update_dict_value(
        self, item_id: int, value: str, additional_info: str = ""
    ) -> bool:
        try:
            with self._session() as s:
                item = s.get(DictionaryItem, item_id)
                if item is None:
                    return False
                item.value = value
                item.additional_info = additional_info
                s.commit()
            self._invalidate_dict_cache()
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления словаря: {e}", exc_info=True)
            return False

    def delete_dict_value(self, item_id: int) -> bool:
        try:
            with self._session() as s:
                item = s.get(DictionaryItem, item_id)
                if item is None:
                    return False
                s.delete(item)
                s.commit()
            self._invalidate_dict_cache()
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления из словаря: {e}", exc_info=True)
            return False

    # ==================== УСТРОЙСТВА ====================

    def add_device(self, device_data: dict[str, Any]) -> int | None:
        try:
            with self._session() as s:
                device = DeviceModel(
                    order_number=device_data.get("order_number", ""),
                    receipt_date=device_data.get("receipt_date", ""),
                    device_type=device_data.get("device_type", ""),
                    brand=device_data.get("brand", ""),
                    model=device_data.get("model", ""),
                    serial_number=device_data.get("serial_number", ""),
                    defect=device_data.get("defect", ""),
                    appearance=device_data.get("appearance", ""),
                    completeness=device_data.get("completeness", ""),
                    work_items=device_data.get("work_items_json", "") or "[]",
                    client_name=device_data.get("client_name", ""),
                    client_status=device_data.get("client_status", "Новый"),
                    phone=device_data.get("phone", ""),
                    total_price=parse_price_to_float(device_data.get("total_price", "0")),
                    prepayment=parse_price_to_float(device_data.get("prepayment", "0")),
                    status=device_data.get("status", "Диагностика"),
                    priority=device_data.get("priority", "Обычный"),
                    engineer=device_data.get("engineer", ""),
                    warranty=device_data.get("warranty", ""),
                    notes=device_data.get("notes", ""),
                    photos=device_data.get("photos", ""),
                    expense=device_data.get("expense", "0"),
                )
                s.add(device)
                s.flush()
                device_id = device.id
                self._sync_work_items(s, device_id, device_data.get("work_items_json", ""))
                self._sync_photos(s, device_id, device_data.get("photos", ""))
                s.commit()
                return device_id
        except Exception as e:
            logger.error(f"Ошибка добавления устройства: {e}", exc_info=True)
            return None

    def update_device(self, device_id: int, device_data: dict[str, Any]) -> bool:
        try:
            with self._session() as s:
                device = s.get(DeviceModel, device_id)
                if device is None:
                    return False

                completion_date = device_data.get("completion_date", "")
                status = device_data.get("status", "")
                if status == _ISSUED_STATUS and not completion_date:
                    completion_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                device.device_type = device_data.get("device_type", "")
                device.brand = device_data.get("brand", "")
                device.model = device_data.get("model", "")
                device.serial_number = device_data.get("serial_number", "")
                device.defect = device_data.get("defect", "")
                device.appearance = device_data.get("appearance", "")
                device.completeness = device_data.get("completeness", "")
                device.work_items = device_data.get("work_items_json", "") or "[]"
                device.client_name = device_data.get("client_name", "")
                device.client_status = device_data.get("client_status", "Новый")
                device.phone = device_data.get("phone", "")
                device.total_price = parse_price_to_float(device_data.get("total_price", "0"))
                device.prepayment = parse_price_to_float(device_data.get("prepayment", "0"))
                device.priority = device_data.get("priority", "Обычный")
                device.engineer = device_data.get("engineer", "")
                device.warranty = device_data.get("warranty", "")
                device.notes = device_data.get("notes", "")
                device.status = status
                device.photos = device_data.get("photos", "")
                device.completion_date = completion_date
                device.expense = device_data.get("expense", "0")

                if status == _ISSUED_STATUS:
                    order_number = device_data.get("order_number") or device.order_number
                    if order_number:
                        income = parse_price_to_float(device_data.get("total_price", "0"))
                        expense_val = parse_price_to_float(device_data.get("expense", "0"))
                        self._upsert_finance_record(
                            s, order_number, completion_date, income, expense_val
                        )

                self._sync_work_items(s, device_id, device_data.get("work_items_json", ""))
                self._sync_photos(s, device_id, device_data.get("photos", ""))
                s.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка обновления устройства: {e}", exc_info=True)
            return False

    def update_device_status(
        self, device_id: int, status: str, completion_date: str | None = None
    ) -> bool:
        try:
            with self._session() as s:
                device = s.get(DeviceModel, device_id)
                if device is None:
                    return False
                device.status = status
                if status == _ISSUED_STATUS:
                    device.completion_date = completion_date or datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                s.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка обновления статуса: {e}", exc_info=True)
            return False

    def delete_device(self, device_id: int) -> bool:
        try:
            with self._session() as s:
                device = s.get(DeviceModel, device_id)
                if device is None:
                    return False
                s.delete(device)  # cascade удаляет work_item_records/photo_records
                s.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка удаления устройства: {e}", exc_info=True)
            return False

    def get_all_devices(self, include_completed: bool = True) -> list[dict[str, Any]]:
        with self._session() as s:
            stmt = select(DeviceModel).order_by(DeviceModel.receipt_date.desc())
            if not include_completed:
                stmt = stmt.where(DeviceModel.status.notin_(_CLOSED_STATUSES))
            return [_device_to_row(d) for d in s.execute(stmt).scalars().all()]

    def get_device(self, device_id: int) -> dict[str, Any] | None:
        with self._session() as s:
            device = s.get(DeviceModel, device_id)
            return _device_to_row(device) if device else None

    def get_device_by_order_number(self, order_number: str) -> dict[str, Any] | None:
        with self._session() as s:
            device = s.execute(
                select(DeviceModel).where(DeviceModel.order_number == order_number)
            ).scalar_one_or_none()
            return _device_to_row(device) if device else None

    def get_device_id_by_order_number(self, order_number: str) -> int | None:
        with self._session() as s:
            return s.execute(
                select(DeviceModel.id).where(DeviceModel.order_number == order_number)
            ).scalar_one_or_none()

    def search_devices(
        self, search_text: str, include_completed: bool = True
    ) -> list[dict[str, Any]]:
        search_text = (search_text or "").strip()
        if not search_text:
            return self.get_all_devices(include_completed=include_completed)

        all_rows = self.get_all_devices(include_completed=include_completed)
        needle = search_text.lower()
        phone_digits = normalize_phone_digits(search_text)
        order_digits = "".join(ch for ch in search_text if ch.isdigit())

        from database.db_manager import Database as _LegacyDatabase

        return [
            row
            for row in all_rows
            if _LegacyDatabase._row_matches(row, needle, phone_digits, order_digits)
        ]

    def get_devices_by_filters(
        self,
        status_filter: str,
        priority_filter: str,
        include_completed: bool = True,
        device_type_filter: str = "Все",
        brand_filter: str = "Все",
    ) -> list[dict[str, Any]]:
        with self._session() as s:
            stmt = select(DeviceModel)
            if not include_completed:
                stmt = stmt.where(DeviceModel.status.notin_(_CLOSED_STATUSES))
            if status_filter and status_filter != "Все":
                stmt = stmt.where(DeviceModel.status == status_filter)
            if priority_filter and priority_filter != "Все":
                stmt = stmt.where(DeviceModel.priority == priority_filter)
            if device_type_filter and device_type_filter != "Все":
                stmt = stmt.where(DeviceModel.device_type == device_type_filter)
            if brand_filter and brand_filter != "Все":
                stmt = stmt.where(DeviceModel.brand == brand_filter)
            stmt = stmt.order_by(DeviceModel.receipt_date.desc())
            return [_device_to_row(d) for d in s.execute(stmt).scalars().all()]

    def get_statistics(self) -> dict[str, int]:
        with self._session() as s:
            total = s.execute(select(func.count(DeviceModel.id))).scalar() or 0
            in_repair = s.execute(
                select(func.count(DeviceModel.id)).where(
                    DeviceModel.status.notin_(_CLOSED_STATUSES)
                )
            ).scalar() or 0
            ready = s.execute(
                select(func.count(DeviceModel.id)).where(
                    DeviceModel.status == _READY_STATUS
                )
            ).scalar() or 0
            total_income = s.execute(
                select(func.coalesce(func.sum(DeviceModel.total_price), 0.0)).where(
                    DeviceModel.status == _ISSUED_STATUS
                )
            ).scalar() or 0.0
            return {
                "total": total,
                "in_repair": in_repair,
                "ready": ready,
                "total_income": float(total_income),
            }

    # ==================== CALCULATION OFFLOADING ====================

    def calculate(self, name: str, **params: Any) -> Any:
        """Тяжёлые агрегации на стороне SQL вместо питоновских циклов.

        Поддерживаемые name: 'overdue_count', 'overdue_orders', 'dashboard_stats'.
        """
        handlers = {
            "overdue_count": self._calc_overdue_count,
            "overdue_orders": self._calc_overdue_orders,
            "dashboard_stats": self._calc_dashboard_stats,
        }
        handler = handlers.get(name)
        if handler is None:
            raise ValueError(f"Неизвестное вычисление: {name!r}")
        return handler(**params)

    def _calc_overdue_count(self, threshold_days: int = OVERDUE_THRESHOLD_DAYS) -> int:
        with self._session() as s:
            cutoff = (datetime.now() - timedelta(days=threshold_days)).strftime("%Y-%m-%d")
            return s.execute(
                select(func.count(DeviceModel.id)).where(
                    DeviceModel.status.notin_(_CLOSED_STATUSES),
                    DeviceModel.receipt_date < cutoff,
                )
            ).scalar() or 0

    def _calc_overdue_orders(
        self, threshold_days: int = OVERDUE_THRESHOLD_DAYS
    ) -> list[dict[str, Any]]:
        with self._session() as s:
            cutoff = (datetime.now() - timedelta(days=threshold_days)).strftime("%Y-%m-%d")
            stmt = (
                select(DeviceModel)
                .where(
                    DeviceModel.status.notin_(_CLOSED_STATUSES),
                    DeviceModel.receipt_date < cutoff,
                )
                .order_by(DeviceModel.receipt_date)
            )
            return [_device_to_row(d) for d in s.execute(stmt).scalars().all()]

    def _calc_dashboard_stats(self) -> dict[str, Any]:
        stats = self.get_statistics()
        stats["overdue"] = self._calc_overdue_count()
        return stats

    # ==================== ФИНАНСЫ ====================

    def get_finances(self, period: str = "all") -> list[dict[str, Any]]:
        with self._session() as s:
            stmt = select(FinanceRecord)
            cutoff = self._period_cutoff(period)
            if cutoff:
                stmt = stmt.where(FinanceRecord.completion_date >= cutoff)
            stmt = stmt.order_by(FinanceRecord.completion_date.desc())
            return [
                {
                    "id": r.id,
                    "order_number": r.order_number,
                    "completion_date": r.completion_date,
                    "income": r.income,
                    "expense": r.expense,
                    "profit": r.profit,
                }
                for r in s.execute(stmt).scalars().all()
            ]

    def get_finance_summary(self, period: str = "all") -> dict[str, float]:
        with self._session() as s:
            stmt = select(
                func.coalesce(func.sum(FinanceRecord.income), 0.0),
                func.coalesce(func.sum(FinanceRecord.expense), 0.0),
                func.coalesce(func.sum(FinanceRecord.profit), 0.0),
            )
            cutoff = self._period_cutoff(period)
            if cutoff:
                stmt = stmt.where(FinanceRecord.completion_date >= cutoff)
            income, expense, profit = s.execute(stmt).one()
            return {
                "total_income": income,
                "total_expense": expense,
                "total_profit": profit,
            }

    @staticmethod
    def _period_cutoff(period: str) -> str | None:
        if period == "week":
            return (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        if period == "month":
            return (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        return None

    def update_finance_expense(self, order_number: str, expense: float) -> bool:
        try:
            with self._session() as s:
                record = s.execute(
                    select(FinanceRecord).where(
                        FinanceRecord.order_number == order_number
                    )
                ).scalar_one_or_none()
                if record is None:
                    return False
                record.expense = expense
                record.profit = (record.income or 0.0) - expense
                s.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка обновления расхода: {e}", exc_info=True)
            return False

    def _upsert_finance_record(
        self, s: Session, order_number: str, completion_date: str, income: float, expense: float
    ) -> None:
        record = s.execute(
            select(FinanceRecord).where(FinanceRecord.order_number == order_number)
        ).scalar_one_or_none()
        if record is None:
            record = FinanceRecord(order_number=order_number)
            s.add(record)
        record.completion_date = completion_date
        record.income = income
        record.expense = expense
        record.profit = income - expense

    # ==================== РАБОТЫ / ФОТО (дочерние таблицы) ====================

    def _sync_work_items(self, s: Session, device_id: int, work_items_json: str) -> None:
        device = s.get(DeviceModel, device_id)
        if device is not None:
            for item in list(device.work_item_records):
                s.delete(item)
        if not work_items_json:
            return
        try:
            items = json.loads(work_items_json)
        except (json.JSONDecodeError, TypeError):
            return
        if not isinstance(items, list):
            return
        from database.sqlalchemy_models import WorkItemRecord

        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            price = parse_price_to_float(item.get("price", 0))
            try:
                qty = max(int(item.get("quantity", 1)), 1)
            except (ValueError, TypeError):
                qty = 1
            s.add(
                WorkItemRecord(
                    device_id=device_id,
                    description=item.get("description", ""),
                    price=price,
                    quantity=qty,
                    total=price * qty,
                    sort_order=i,
                )
            )

    def get_work_items_from_db(self, device_id: int) -> list[dict[str, Any]]:
        with self._session() as s:
            device = s.get(DeviceModel, device_id)
            if device is None:
                return []
            return [
                {
                    "description": w.description,
                    "price": w.price,
                    "quantity": w.quantity,
                    "total": w.total,
                }
                for w in sorted(device.work_item_records, key=lambda w: w.sort_order)
            ]

    def _sync_photos(self, s: Session, device_id: int, photos_csv: str) -> None:
        import os

        device = s.get(DeviceModel, device_id)
        if device is not None:
            for photo in list(device.photo_records):
                s.delete(photo)
        if not photos_csv:
            return
        from database.sqlalchemy_models import PhotoRecord

        paths = [p.strip() for p in photos_csv.split(",") if p.strip()]
        for i, path in enumerate(paths):
            s.add(
                PhotoRecord(
                    device_id=device_id,
                    file_path=path,
                    filename=os.path.basename(path) if path else "",
                    sort_order=i,
                )
            )

    def get_photos_from_db(self, device_id: int) -> list[dict[str, Any]]:
        with self._session() as s:
            device = s.get(DeviceModel, device_id)
            if device is None:
                return []
            return [
                {
                    "id": p.id,
                    "file_path": p.file_path,
                    "filename": p.filename,
                    "photo_type": p.photo_type,
                }
                for p in sorted(device.photo_records, key=lambda p: p.sort_order)
            ]

    def add_photo_to_db(self, device_id: int, file_path: str) -> bool:
        import os

        try:
            with self._session() as s:
                from database.sqlalchemy_models import PhotoRecord

                max_order = s.execute(
                    select(func.max(PhotoRecord.sort_order)).where(
                        PhotoRecord.device_id == device_id
                    )
                ).scalar()
                s.add(
                    PhotoRecord(
                        device_id=device_id,
                        file_path=file_path,
                        filename=os.path.basename(file_path),
                        sort_order=(max_order if max_order is not None else -1) + 1,
                    )
                )
                s.commit()
                return True
        except Exception as e:
            logger.warning(f"Ошибка добавления фото в БД: {e}")
            return False

    def add_completed_repair(self, device: dict[str, Any]) -> bool:
        try:
            with self._session() as s:
                s.add(
                    CompletedRepair(
                        device_id=device.get("id"),
                        order_number=device.get("order_number"),
                        completion_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        work_description=device.get("work_items", ""),
                        work_price=device.get("total_price", ""),
                        engineer=device.get("engineer", ""),
                        warranty=device.get("warranty", ""),
                        notes=device.get("notes", ""),
                    )
                )
                s.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка добавления завершенного ремонта: {e}", exc_info=True)
            return False

    # ==================== КЛИЕНТЫ (объединённые) ====================

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
