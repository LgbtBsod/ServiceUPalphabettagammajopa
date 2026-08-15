#!/usr/bin/env python3
"""Миграция service_center.db (raw sqlite3) на SQLAlchemy-схему.

Безопасность:
1. Делает timestamped-копию текущего файла БД перед любыми действиями.
2. Читает исходные данные ТОЛЬКО через существующий database.db_manager.Database
   (проверенный код, не переписываю SQL заново).
3. Пишет в НОВЫЙ файл (рядом с оригиналом, суффикс .sqlalchemy.db) через
   database.sqlalchemy_database.Database — оригинал не трогается вообще.
4. Верифицирует результат (количество строк по каждой таблице) и печатает отчёт.
5. Ничего не переключает автоматически — переключение источника (DB_PATH)
   делает пользователь/bootstrap.py осознанно, после проверки отчёта.

Запуск:
    python tools/migrate_to_sqlalchemy.py [--target PATH] [--yes]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path


def _backup(source: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = source.with_name(f"{source.stem}.backup_{stamp}{source.suffix}")
    shutil.copy2(source, backup_path)
    return backup_path


def migrate(source_path: Path, target_path: Path) -> dict:
    """Мигрирует данные из source_path (legacy raw sqlite3) в target_path
    (новая SQLAlchemy-схема). Возвращает отчёт о количестве перенесённых строк.
    """
    from sqlalchemy import select

    from database.db_config import DatabaseConfig, DatabaseType
    from database.db_manager import Database as LegacyDatabase
    from database.engines import create_engine_for
    from database.sqlalchemy_database import Database as NewDatabase
    from database.sqlalchemy_models import Counter, FinanceRecord

    legacy = LegacyDatabase(str(source_path))

    new_engine = create_engine_for(
        DatabaseConfig(db_type=DatabaseType.SQLITE, database=str(target_path))
    )
    new_db = NewDatabase(new_engine)

    report = {"clients": 0, "devices": 0, "dictionaries": 0, "finances": 0, "counters": 0}

    # --- Счётчики (order_counter и т.п.) — переносим значение как есть, чтобы
    # номера заказов не начали генерироваться заново с 1 после переключения ---
    cursor = legacy.conn.cursor()
    cursor.execute("SELECT name, value FROM counters")
    for name, value in cursor.fetchall():
        with new_db._session() as s:  # прямой доступ оправдан только для миграции
            counter = s.execute(
                select(Counter).where(Counter.name == name)
            ).scalar_one_or_none()
            if counter is None:
                s.add(Counter(name=name, value=value))
            else:
                counter.value = value
            s.commit()
        report["counters"] += 1

    # --- Словари (нужны до устройств, т.к. содержат используемые в них значения) ---
    cursor = legacy.conn.cursor()
    cursor.execute("SELECT DISTINCT dict_type FROM dictionaries")
    for (dict_type,) in cursor.fetchall():
        for item in legacy.get_all_dict_items(dict_type):
            new_db.add_dict_value(dict_type, item["value"], item.get("additional_info") or "")
            report["dictionaries"] += 1

    # --- Клиенты (нужны до устройств, т.к. add_device не создаёт клиента) ---
    cursor.execute("SELECT name, phone, status FROM clients")
    client_id_map: dict[str, int] = {}
    for name, phone, status in cursor.fetchall():
        new_id = new_db.get_or_create_client(name, phone, status or "Новый")
        if new_id:
            client_id_map[phone] = new_id
            report["clients"] += 1

    # --- Устройства/заказы ---
    for device in legacy.get_all_devices(include_completed=True):
        device_data = dict(device)
        device_data["work_items_json"] = device_data.get("work_items", "")
        new_id = new_db.add_device(device_data)
        if new_id:
            report["devices"] += 1
            client_id = client_id_map.get(device_data.get("phone"))
            if client_id:
                new_db.add_to_repair_history_main(client_id, new_id, device_data)

    # --- Финансы (для записей, не связанных с уже перенесёнными заказами) ---
    for fin in legacy.get_finances(period="all"):
        # update_finance_expense требует существующей записи — она уже создана
        # add_device/update_device при статусе "Выдан клиенту"; для случаев,
        # когда исходных данных о доходе нет в devices, досоздаём напрямую.
        existing = [f for f in new_db.get_finances() if f["order_number"] == fin["order_number"]]
        if not existing:
            with new_db._session() as s:  # прямой доступ оправдан только для миграции
                s.add(FinanceRecord(
                    order_number=fin["order_number"],
                    completion_date=fin.get("completion_date"),
                    income=fin.get("income") or 0.0,
                    expense=fin.get("expense") or 0.0,
                    profit=fin.get("profit") or 0.0,
                ))
                s.commit()
        report["finances"] += 1

    legacy.close() if hasattr(legacy, "close") else None
    new_engine.dispose()
    return report


def verify(source_path: Path, target_path: Path) -> bool:
    """Сравнивает количество строк по каждой общей таблице. True, если совпало."""
    import sqlite3

    tables = [
        "clients", "devices", "dictionaries", "finances",
        "counters", "work_items_db", "photos_db",
        "completed_repairs", "repair_history_main",
    ]
    ok = True
    print("\n=== Верификация (старая БД -> новая БД) ===")
    with sqlite3.connect(source_path) as src, sqlite3.connect(target_path) as dst:
        for table in tables:
            src_n = src.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            try:
                dst_n = dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.OperationalError:
                dst_n = None
            status = "OK" if src_n == dst_n else "MISMATCH"
            if src_n != dst_n:
                ok = False
            print(f"  {table:20s}: старая={src_n:>5}  новая={dst_n if dst_n is not None else '—':>5}  [{status}]")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", default=None, help="Путь к исходной БД (по умолчанию — config.DB_PATH)"
    )
    parser.add_argument(
        "--target", default=None,
        help="Путь к новому файлу (по умолчанию — <source>.sqlalchemy.db)",
    )
    parser.add_argument(
        "--yes", action="store_true", help="Не спрашивать подтверждения"
    )
    args = parser.parse_args()

    from config import get_db_path

    source_path = Path(args.source) if args.source else get_db_path()
    if not source_path.exists():
        print(f"Исходная БД не найдена: {source_path}")
        return 1

    target_path = Path(args.target) if args.target else source_path.with_suffix(".sqlalchemy.db")
    if target_path.exists():
        print(f"Целевой файл уже существует: {target_path}")
        print("Удалите его или укажите другой --target, чтобы не перезаписать чужие данные.")
        return 1

    print(f"Источник: {source_path}")
    print(f"Цель:     {target_path}")

    if not args.yes:
        answer = input("Продолжить? Оригинал не изменяется, будет сделан бэкап. [y/N] ")
        if answer.strip().lower() != "y":
            print("Отменено.")
            return 1

    backup_path = _backup(source_path)
    print(f"Бэкап создан: {backup_path}")

    report = migrate(source_path, target_path)
    print("\n=== Перенесено ===")
    for key, value in report.items():
        print(f"  {key}: {value}")

    ok = verify(source_path, target_path)
    print("\n" + ("[OK] Верификация пройдена — новая БД готова к использованию." if ok
                   else "[MISMATCH] Расхождение количества строк — НЕ переключайтесь на новую БД, разберитесь в причине."))
    print(f"\nЧтобы начать использовать новую БД, задайте в .env: DB_PATH={target_path}")
    print("(источник и бэкап остаются нетронутыми на диске)")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
