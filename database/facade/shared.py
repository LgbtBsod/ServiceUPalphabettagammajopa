#!/usr/bin/env python3
"""Свободные функции/константы/исключения, общие для нескольких mixin'ов
database/facade/*_mixin.py — извлечены сюда, а не продублированы в каждом
файле по отдельности (SSOT), см. AUDIT_REPORT_v25.md, Task T."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from database.db_core import DuplicateDatabaseConnectionError  # noqa: F401 — реэкспорт
from database.sqlalchemy_models import Client, CompletedRepair, DictionaryItem, Employee
from database.sqlalchemy_models import Device as DeviceModel
from database.sqlalchemy_models import FinanceRecord, RepairHistoryMain, WorkTemplate
from utils.formatters import parse_price_to_float

logger = logging.getLogger(__name__)

# Раньше эти 4 константы были независимо продублированы здесь как приватные
# строковые литералы, без единого импорта domain.constants — тот самый
# SSOT-разрыв, который сама domain.constants была призвана устранить, см.
# AUDIT_REPORT_v21.md.
OVERDUE_THRESHOLD_DAYS = 14


# SSOT-справка (не генерирует код и не меняет поведение update_device() —
# намеренно, само построение new_values там остаётся явным) — ключи
# device_data, которые update_device() реально читает.
# tests/test_device_field_consistency.py сверяет это множество с
# gui/dialogs/device_form.py::_SCALAR_FIELD_NAMES, чтобы дрейф между двумя
# независимо поддерживаемыми списками (найден AUDIT_REPORT_v25.md —
# тройное ручное дублирование) ловил тест, а не проходил незамеченным.
DEVICE_UPDATE_FIELDS = frozenset({
    "device_type", "brand", "model", "serial_number", "defect",
    "appearance", "completeness", "work_items_json", "client_name",
    "client_status", "phone", "total_price", "prepayment", "priority",
    "engineer", "warranty", "notes", "status", "photos",
    "completion_date", "expense",
})


class QueryError(ValueError):
    """Некорректный структурированный запрос к Database.query() — неизвестная
    таблица/колонка/оператор фильтра/сортировки. Обёртка над всем, что
    Database.query() отвергает до похода в SQLAlchemy."""


# DuplicateDatabaseConnectionError реэкспортирован из database.db_core —
# см. импорт вверху файла (определение и guard от повторного подключения
# переехали туда вместе, Task W: "ядро БД" владеет управлением соединением,
# не facade-mixin'ы).


class OptimisticLockError(RuntimeError):
    """update_device() получил _expected_version, не совпадающую с текущей
    Device.version_id — запись изменил кто-то другой, пока форма была
    открыта. Работает независимо от pessimistic_locking_enabled и от того,
    какой клиент сделал конкурентную правку (GUI или PWA) — единственная
    защита, которая гарантированно есть всегда."""


# Белый список таблиц, доступных через Database.query() — структурированный
# запрос вместо сырого SQL (модуль описывает ЧТО хочет получить как данные,
# а не как выразить это в SQL-тексте; SQLAlchemy строит запрос под текущий
# движок — SQLite/Postgres — и параметризует все значения). Явный whitelist
# не даёт обратиться к произвольной таблице по строковому имени.
QUERYABLE_MODELS: dict[str, type] = {
    "devices": DeviceModel,
    "clients": Client,
    "employees": Employee,
    "finances": FinanceRecord,
    "dictionaries": DictionaryItem,
    "work_templates": WorkTemplate,
    "completed_repairs": CompletedRepair,
    "repair_history_main": RepairHistoryMain,
}

FILTER_OPERATORS = {
    "eq": lambda col, val: col == val,
    "ne": lambda col, val: col != val,
    "gt": lambda col, val: col > val,
    "gte": lambda col, val: col >= val,
    "lt": lambda col, val: col < val,
    "lte": lambda col, val: col <= val,
    "in": lambda col, val: col.in_(val),
    "like": lambda col, val: col.ilike(f"%{val}%"),
}


def resolve_queryable_model(table: str) -> type:
    """Резолвит имя таблицы в модель из белого списка QUERYABLE_MODELS —
    общая точка для query() и любых будущих потребителей белого списка."""
    model = QUERYABLE_MODELS.get(table)
    if model is None:
        raise QueryError(
            f"Неизвестная или недоступная таблица: {table!r}. "
            f"Доступны: {sorted(QUERYABLE_MODELS)}"
        )
    return model


def as_utc(dt: datetime) -> datetime:
    """SQLite не хранит tzinfo даже для колонок DateTime(timezone=True) —
    читает их обратно как naive datetime, хотя писали всегда
    datetime.now(timezone.utc). Без этой нормализации сравнение
    "now - row.last_heartbeat_at" падает TypeError'ом (naive - aware)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def fmt_money(value: float | None) -> str:
    """Форматирует число в строку для полей, которые в legacy-схеме были TEXT.

    Сохраняет обратную совместимость с кодом, ожидающим device['total_price']
    как строку (например device_form.py вызывает parse_price_to_float на ней).
    """
    if value is None:
        return ""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}"


def device_to_row(device: DeviceModel) -> dict[str, Any]:
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
        "total_price": fmt_money(device.total_price),
        "prepayment": fmt_money(device.prepayment),
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
        "created_by_id": device.created_by_id,
        "updated_by_id": device.updated_by_id,
        "created_by_name": device.created_by.full_name if device.created_by else None,
        "updated_by_name": device.updated_by.full_name if device.updated_by else None,
        # Оптимистичная блокировка: GUI-слой обязан пронести это значение
        # обратно в update_device(device_data["_expected_version"]) —
        # версия, актуальная НА МОМЕНТ ОТКРЫТИЯ формы, а не на момент
        # сохранения (см. Device.version_id).
        "version": device.version_id,
    }


def publish_device_status_changed(
    device_id: int, old_status: str, new_status: str, device_row: dict[str, Any]
) -> None:
    """Публикует domain.events.DeviceStatusChangedEvent через
    core.kernel.get_core().publish() — первый и пока единственный реальный
    потребитель EventBus в приложении (managers/integrations.py подписан
    в bootstrap.py), см. AUDIT_REPORT_v25.md. No-op, если статус не
    поменялся, ядро не инициализировано (например, Database() создан
    отдельно в тестах, без core.initialize()) или публикация упала —
    издатель никогда не должен ронять уже закоммиченную запись из-за
    проблемы в подписчике."""
    if old_status == new_status:
        return
    try:
        from core.kernel import get_core
        from domain.events import DeviceStatusChangedEvent

        core = get_core()
        if not core.is_initialized:
            return
        core.publish(
            DeviceStatusChangedEvent(
                event_type="DeviceStatusChangedEvent",
                device_id=device_id,
                old_status=old_status,
                new_status=new_status,
                device_data=device_row,
            )
        )
    except Exception as e:
        logger.warning(f"Не удалось опубликовать DeviceStatusChangedEvent: {e}")
