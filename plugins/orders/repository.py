"""Конкретная реализация IOrderRepository — тонкий адаптер поверх уже
существующего Database facade (не поверх сырого SQLAlchemy engine, как
plugins/clients и plugins/employees).

Почему по-другому: Device — не простая CRUD-таблица, а агрегат с
оптимистичной блокировкой (version_id), dual-write дочерними таблицами
(FinanceRecord/WorkItemRecord/PhotoRecord), BOBF change-detection и
публикацией DeviceStatusChangedEvent (см. database/facade/devices_mixin.py)
— вся эта логика уже написана, протестирована и используется ~150+
вызывающими местами через Database/db_access. Реализовать
IOrderRepository ещё раз поверх голого engine означало бы завести ВТОРУЮ
независимую копию этой логики — то самое DRY-нарушение, которое эта же
кодовая база уже правила в других местах (см. AUDIT_REPORT_v25.md) — вместо
этого репозиторий просто делегирует в db_access, оставаясь настоящей
swappable-точкой на будущее (другая реализация/хранилище), но не рискуя
разойтись с проверенной логикой Database.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from plugins.orders import IOrderRepository

if TYPE_CHECKING:
    from database.sqlalchemy_database import Database


class SqlAlchemyOrderRepository(IOrderRepository):
    """Делегирует все вызовы в уже работающий Database facade (db_access)."""

    def __init__(self, db_access: Database):
        self._db = db_access

    def get_next_order_number(self) -> int:
        return self._db.get_next_order_number()

    def peek_next_order_number(self) -> int:
        return self._db.peek_next_order_number()

    def add_device(self, device_data: dict[str, Any]) -> int | None:
        return self._db.add_device(device_data)

    def update_device(self, device_id: int, device_data: dict[str, Any]) -> bool:
        return self._db.update_device(device_id, device_data)

    def update_device_status(
        self, device_id: int, status: str, completion_date: str | None = None
    ) -> bool:
        return self._db.update_device_status(device_id, status, completion_date)

    def delete_device(self, device_id: int) -> bool:
        return self._db.delete_device(device_id)

    def get_all_devices(self, include_completed: bool = True) -> list[dict[str, Any]]:
        return self._db.get_all_devices(include_completed)

    def get_device(self, device_id: int) -> dict[str, Any] | None:
        return self._db.get_device(device_id)

    def get_device_by_order_number(self, order_number: str) -> dict[str, Any] | None:
        return self._db.get_device_by_order_number(order_number)

    def get_device_id_by_order_number(self, order_number: str) -> int | None:
        return self._db.get_device_id_by_order_number(order_number)

    def search_devices(
        self, search_text: str, include_completed: bool = True
    ) -> list[dict[str, Any]]:
        return self._db.search_devices(search_text, include_completed)

    def get_devices_by_filters(
        self,
        status_filter: str,
        priority_filter: str,
        include_completed: bool = True,
        device_type_filter: str = "Все",
        brand_filter: str = "Все",
    ) -> list[dict[str, Any]]:
        return self._db.get_devices_by_filters(
            status_filter,
            priority_filter,
            include_completed,
            device_type_filter,
            brand_filter,
        )

    def get_statistics(self) -> dict[str, int]:
        return self._db.get_statistics()
