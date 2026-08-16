#!/usr/bin/env python3
"""ChildRecordsMixin — дочерние таблицы устройства: позиции работ, фото,
запись о завершённом ремонте. См. AUDIT_REPORT_v25.md, Task T."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from database.facade.shared import logger
from database.sqlalchemy_models import CompletedRepair
from database.sqlalchemy_models import Device as DeviceModel
from utils.formatters import parse_price_to_float

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class ChildRecordsMixin:
    """Требует self._session() от финального класса Database."""

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
