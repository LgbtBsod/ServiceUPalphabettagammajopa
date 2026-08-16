#!/usr/bin/env python3

"""Перенос данных между двумя БД (например, при смене SQLite-файла или
переходе на PostgreSQL) — с построчной проверкой количества записей на
каждую таблицу до переключения боевого пути.

Используется диалогом "Настройки → База данных" (gui/dialogs/database_migration.py)
и может вызываться напрямую (скрипты/тесты). Копирует ВСЕ таблицы схемы
(не только белый список Database.query() — миграция должна быть полной),
в порядке, учитывающем внешние ключи (Base.metadata.sorted_tables), сохраняя
исходные ID (иначе связи client_id/device_id/... разъедутся).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from database.sqlalchemy_models import (
    Base,
    Client,
    CompletedRepair,
    Counter,
    Device,
    DictionaryItem,
    Employee,
    FinanceRecord,
    PhotoRecord,
    RepairHistoryMain,
    Settings,
    WorkItemRecord,
    WorkTemplate,
)

if TYPE_CHECKING:
    from database.engines.base import IDatabaseEngine

logger = logging.getLogger(__name__)

# Полный перечень моделей схемы (не белый список query() — миграция обязана
# перенести всё, а не только то, что безопасно открывать для ad-hoc запросов).
_ALL_MODELS: dict[str, type] = {
    "employees": Employee,
    "clients": Client,
    "devices": Device,
    "work_templates": WorkTemplate,
    "settings": Settings,
    "counters": Counter,
    "dictionaries": DictionaryItem,
    "finances": FinanceRecord,
    "work_items_db": WorkItemRecord,
    "photos_db": PhotoRecord,
    "completed_repairs": CompletedRepair,
    "repair_history_main": RepairHistoryMain,
}


class MigrationVerificationError(RuntimeError):
    """Количество строк в целевой БД не совпало с исходной после переноса —
    переключать боевой путь на target НЕЛЬЗЯ, пока не разобрались, почему."""


def _self_referencing_columns(model: type) -> list[str]:
    """Имена колонок модели, чей FK ссылается на ЕЁ ЖЕ таблицу (например
    Employee.created_by_id/updated_by_id -> employees.id).

    Такие колонки нельзя переносить в общем цикле по строкам таблицы: строка
    A может ссылаться на строку B той же таблицы, ещё не вставленную (порядок
    строк внутри одной таблицы не гарантирован, в отличие от порядка МЕЖДУ
    таблицами, который уже даёт Base.metadata.sorted_tables) — при
    immediate-режиме проверки внешних ключей (PRAGMA foreign_keys=ON, уже
    включён для SQLite) это падает IntegrityError. Найдено аудитом сессии:
    у Employee ровно такой случай (сотрудник Б мог отредактировать запись
    сотрудника А, вставленного раньше по ID).
    """
    table = model.__table__
    return [
        fk.parent.name for fk in table.foreign_keys if fk.column.table is table
    ]


def migrate_data(
    source_engine: IDatabaseEngine, target_engine: IDatabaseEngine
) -> dict[str, dict[str, int]]:
    """Копирует все строки всех таблиц из source_engine в target_engine.

    target_engine должен уже иметь схему (create_tables() уже вызван —
    например, через Database(target_engine) или engine.create_tables()
    напрямую) — эта функция только переносит ДАННЫЕ, не создаёт таблицы.

    Returns:
        {имя_таблицы: {"source": N, "target": M}} — количество строк по
        каждой таблице в обеих БД ПОСЛЕ переноса. Вызывающий код обязан
        сверить source == target для всех таблиц перед тем, как считать
        миграцию успешной (см. verify_migration()).
    """
    result: dict[str, dict[str, int]] = {}
    table_order = [t.name for t in Base.metadata.sorted_tables]

    with Session(source_engine.get_engine()) as src, Session(
        target_engine.get_engine()
    ) as dst:
        for table_name in table_order:
            model = _ALL_MODELS.get(table_name)
            if model is None:
                continue

            rows = src.execute(select(model)).scalars().all()
            source_count = len(rows)
            self_ref_cols = _self_referencing_columns(model)

            if self_ref_cols:
                # Двухфазная вставка: сначала все строки БЕЗ
                # самоссылающихся колонок (NULL — FK тривиально
                # удовлетворён), затем второй проход простановает реальные
                # значения — к этому моменту все строки таблицы уже
                # существуют, порядок не важен.
                deferred: list[tuple[Any, dict[str, Any]]] = []
                for row in rows:
                    data = row.to_dict()
                    real_values = {
                        col: data.pop(col) for col in self_ref_cols
                    }
                    deferred.append((data.get("id"), real_values))
                    for col in self_ref_cols:
                        data.setdefault(col, None)
                        data[col] = None
                    dst.merge(model(**data))
                dst.commit()

                for row_id, real_values in deferred:
                    if all(v is None for v in real_values.values()):
                        continue  # нечего доставлять — экономим запись
                    target_row = dst.get(model, row_id)
                    if target_row is None:
                        continue
                    for col, value in real_values.items():
                        setattr(target_row, col, value)
                dst.commit()
            else:
                for row in rows:
                    data = row.to_dict()
                    # merge() по PK (id уже в data) — insert если нет, update
                    # если есть; сохраняет исходные ID, иначе FK-связи
                    # (client_id, device_id...) между таблицами разъедутся.
                    dst.merge(model(**data))
                dst.commit()

            target_count = dst.execute(select(model)).scalars().all()
            result[table_name] = {
                "source": source_count,
                "target": len(target_count),
            }
            logger.info(
                f"Миграция {table_name}: {source_count} -> {len(target_count)}"
            )

        _reset_target_sequences(dst, target_engine, table_order)

    return result


def _reset_target_sequences(
    dst: Session, target_engine: IDatabaseEngine, table_order: list[str]
) -> None:
    """Postgres не продвигает SERIAL/identity-последовательность при
    вставке строки с явным PK (а migrate_data() всегда переносит исходные
    id, иначе развалятся FK) — счётчик остаётся на последнем ВЫДАННОМ
    значении (обычно 1 на свежей базе). Первый же органический add_device()
    после миграции (без явного id, полагается на nextval) получит id=1 —
    конфликт с уже перенесённой строкой, IntegrityError. На SQLite это
    не воспроизводится (id выводится из MAX(rowid), а не отдельного
    объекта-последовательности) — поэтому no-op для всех движков, кроме
    postgresql. См. AUDIT_REPORT_v25.md.

    Не проверялось против реального сервера PostgreSQL (в этом окружении
    его нет) — pg_get_serial_sequence()/setval() стандартные встроенные
    функции Postgres, но перед боевым использованием стоит прогнать
    вручную на тестовой Postgres-базе."""
    if target_engine.db_type != "postgresql":
        return
    for table_name in table_order:
        model = _ALL_MODELS.get(table_name)
        if model is None:
            continue
        try:
            dst.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table_name}), 1))"
                )
            )
        except Exception as e:
            logger.warning(
                f"Не удалось сбросить identity-последовательность {table_name}: {e}"
            )
    dst.commit()


def verify_migration(report: dict[str, dict[str, int]]) -> list[str]:
    """Возвращает список таблиц, где source != target (пусто — миграция
    полная и совпадает). Проверять ДО переключения боевого пути на target."""
    return [
        table
        for table, counts in report.items()
        if counts["source"] != counts["target"]
    ]
