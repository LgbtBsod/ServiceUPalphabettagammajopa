#!/usr/bin/env python3
"""DevicesMixin — счётчики номеров заказов + CRUD/поиск/фильтры/статистика
устройств. Самый крупный раздел бывшего sqlalchemy_database.py (см.
AUDIT_REPORT_v25.md, Task T)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from database.facade.shared import (
    OptimisticLockError,
    device_to_row,
    logger,
    publish_device_status_changed,
)
from database.sqlalchemy_models import Counter
from database.sqlalchemy_models import Device as DeviceModel
from domain.constants import CLOSED_STATUSES as _CLOSED_STATUSES
from domain.constants import STATUS_ISSUED as _ISSUED_STATUS
from domain.constants import STATUS_READY as _READY_STATUS
from utils.formatters import normalize_phone_digits, parse_price_to_float, row_matches_search


class DevicesMixin:
    """Требует self._session() от финального класса Database (см.
    database/sqlalchemy_database.py) — как и все остальные mixin'ы здесь,
    сам по себе не открывает сессий."""

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

    # ==================== УСТРОЙСТВА ====================

    def add_device(self, device_data: dict[str, Any]) -> int | None:
        try:
            with self._session() as s:
                device = DeviceModel(
                    order_number=device_data.get("order_number", ""),
                    receipt_date=device_data.get("receipt_date", ""),
                    # "" (не None) — тот же сентинел, что update_device()
                    # использует для "не выдан" (completion_date=""). БЕЗ
                    # этого свежесозданное устройство, пересохранённое без
                    # правок, ложно выглядело бы изменённым (None != "") —
                    # ровно то, что BOBF-детект должен был исключить.
                    completion_date=device_data.get("completion_date", ""),
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
                    created_by_id=device_data.get("created_by_id"),
                    updated_by_id=device_data.get("created_by_id"),
                    version_id=1,
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
        """Обновляет устройство — но только если данные РЕАЛЬНО отличаются
        от текущих (BOBF-стиль change detection: просмотр записи — не
        правка). Если после сравнения ничего не изменилось, строка не
        трогается вообще: ни updated_at (onupdate сработает только если
        объект попадёт во flush), ни updated_by_id, ни дочерние таблицы
        work_items/photos, ни финансовая запись — иначе "открыл форму и
        нажал Сохранить, ничего не поменяв" выглядел бы как реальное
        изменение записи.

        Ожидаемые ключи device_data — см. facade.shared.DEVICE_UPDATE_FIELDS
        (плюс необязательный "_expected_version", см. AUDIT_REPORT_v25.md
        про оптимистичную блокировку)."""
        try:
            with self._session() as s:
                device = s.get(DeviceModel, device_id)
                if device is None:
                    return False
                old_status = device.status

                status = device_data.get("status", "")
                if status == _ISSUED_STATUS:
                    if device.status == _ISSUED_STATUS:
                        # Уже был выдан — не перештамповываем дату выдачи
                        # заново на "сейчас" только потому, что форму
                        # пересохранили (например, поправили заметку).
                        completion_date = device.completion_date or ""
                    else:
                        # Первый переход в "Выдан клиенту" — фиксируем момент.
                        completion_date = device_data.get(
                            "completion_date"
                        ) or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                else:
                    completion_date = device_data.get("completion_date", "")

                new_values = {
                    "device_type": device_data.get("device_type", ""),
                    "brand": device_data.get("brand", ""),
                    "model": device_data.get("model", ""),
                    "serial_number": device_data.get("serial_number", ""),
                    "defect": device_data.get("defect", ""),
                    "appearance": device_data.get("appearance", ""),
                    "completeness": device_data.get("completeness", ""),
                    "work_items": device_data.get("work_items_json", "") or "[]",
                    "client_name": device_data.get("client_name", ""),
                    "client_status": device_data.get("client_status", "Новый"),
                    "phone": device_data.get("phone", ""),
                    "total_price": parse_price_to_float(device_data.get("total_price", "0")),
                    "prepayment": parse_price_to_float(device_data.get("prepayment", "0")),
                    "priority": device_data.get("priority", "Обычный"),
                    "engineer": device_data.get("engineer", ""),
                    "warranty": device_data.get("warranty", ""),
                    "notes": device_data.get("notes", ""),
                    "status": status,
                    "photos": device_data.get("photos", ""),
                    "completion_date": completion_date,
                    "expense": device_data.get("expense", "0"),
                }

                changed = False
                for field, new_value in new_values.items():
                    if getattr(device, field) != new_value:
                        setattr(device, field, new_value)
                        changed = True

                if not changed:
                    return True

                # Оптимистичная блокировка: _expected_version — версия,
                # прочитанная GUI в момент открытия формы (Database.get_device
                # кладёт её в "version"). Сравниваем ТОЛЬКО когда есть что
                # реально записывать (changed=True) — безобидный ресейв без
                # правок конфликтом не считается, даже если версия успела
                # уйти вперёд. None — вызывающий код не в курсе версии
                # (например, старый вызов) — проверка тогда пропускается,
                # не ломает обратную совместимость.
                expected_version = device_data.get("_expected_version")
                if expected_version is not None and device.version_id != expected_version:
                    raise OptimisticLockError(
                        f"Заказ #{device.order_number} изменён другим "
                        f"пользователем (ожидалась версия {expected_version}, "
                        f"сейчас {device.version_id})."
                    )
                device.version_id = (device.version_id or 1) + 1

                # created_by_id НЕ трогаем при обновлении — остаётся тем, кто
                # создал заказ изначально; "текущий сотрудник" на момент
                # реального изменения фиксируется только как updated_by_id.
                if "created_by_id" in device_data:
                    device.updated_by_id = device_data.get("created_by_id")

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
                publish_device_status_changed(device_id, old_status, status, device_to_row(device))
                return True
        except OptimisticLockError:
            # Не глотаем как обычную ошибку записи — вызывающий код (GUI)
            # должен отличить "конфликт версий" от "БД недоступна", чтобы
            # показать кнопку "Обновить", а не общий "Ошибка сохранения".
            # Ничего не закоммичено (raise случился до s.commit()) — сессия
            # просто закрывается без изменений.
            raise
        except Exception as e:
            logger.error(f"Ошибка обновления устройства: {e}", exc_info=True)
            return False

    def update_device_status(
        self, device_id: int, status: str, completion_date: str | None = None
    ) -> bool:
        """Быстрая смена статуса (PWA PUT /status, кнопка "выдать" в
        main_window.py) — без полной формы, но по той же логике
        версии/финзаписи, что и update_device(), чтобы этот путь не
        расходился с обычным сохранением формы. Раньше НЕ бампил version_id
        и НЕ создавал финзапись при переходе в "Выдан" — тихая дыра в
        финучёте (доход с быстрой выдачи никогда не попадал в finances) и
        слепая зона оптимистичной блокировки (конкурентное сохранение
        открытой формы не видело такой смены статуса как конфликт), см.
        AUDIT_REPORT_v25.md."""
        try:
            with self._session() as s:
                device = s.get(DeviceModel, device_id)
                if device is None:
                    return False
                if device.status == status:
                    return True  # BOBF: реального изменения нет

                old_status = device.status
                was_issued = device.status == _ISSUED_STATUS
                device.status = status
                device.version_id = (device.version_id or 1) + 1

                if status == _ISSUED_STATUS:
                    device.completion_date = completion_date or datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    if not was_issued and device.order_number:
                        income = device.total_price or 0.0
                        expense_val = parse_price_to_float(device.expense or "0")
                        self._upsert_finance_record(
                            s,
                            device.order_number,
                            device.completion_date,
                            income,
                            expense_val,
                        )
                s.commit()
                publish_device_status_changed(device_id, old_status, status, device_to_row(device))
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
            return [device_to_row(d) for d in s.execute(stmt).scalars().all()]

    def get_device(self, device_id: int) -> dict[str, Any] | None:
        with self._session() as s:
            device = s.get(DeviceModel, device_id)
            return device_to_row(device) if device else None

    def get_device_by_order_number(self, order_number: str) -> dict[str, Any] | None:
        with self._session() as s:
            device = s.execute(
                select(DeviceModel).where(DeviceModel.order_number == order_number)
            ).scalar_one_or_none()
            return device_to_row(device) if device else None

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

        return [
            row
            for row in all_rows
            if row_matches_search(row, needle, phone_digits, order_digits)
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
            return [device_to_row(d) for d in s.execute(stmt).scalars().all()]

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
