#!/usr/bin/env python3

"""Тесты для database/db_migration_tool.py — перенос данных между двумя
БД (используется кнопкой "Мигрировать" в настройках), с построчной
проверкой количества записей до переключения боевого пути."""

import os
import tempfile

import pytest

from database.db_config import DatabaseConfig
from database.db_migration_tool import _reset_target_sequences, migrate_data, verify_migration
from database.engines.sqlite_engine import SQLiteEngine
from database.sqlalchemy_database import Database


@pytest.fixture
def two_engines():
    fd1, path1 = tempfile.mkstemp(suffix=".db")
    os.close(fd1)
    fd2, path2 = tempfile.mkstemp(suffix=".db")
    os.close(fd2)

    source_engine = SQLiteEngine(DatabaseConfig(database=path1))
    target_engine = SQLiteEngine(DatabaseConfig(database=path2))

    yield source_engine, target_engine

    source_engine.dispose()
    target_engine.dispose()
    for p in (path1, path2):
        if os.path.exists(p):
            os.remove(p)


class TestMigrateData:
    def test_migrates_devices_and_clients(self, two_engines):
        source_engine, target_engine = two_engines
        source_db = Database(source_engine)
        source_db.add_device(
            {
                "order_number": "00001",
                "receipt_date": "2026-01-01",
                "device_type": "Ноутбук",
                "client_name": "Иван Иванов",
                "phone": "+79991234567",
                "status": "Диагностика",
            }
        )
        source_db.get_or_create_client("Иван Иванов", "+79991234567")

        target_engine.create_tables()  # схема должна существовать до переноса
        report = migrate_data(source_engine, target_engine)

        assert report["devices"]["source"] == 1
        assert report["devices"]["target"] == 1
        assert report["clients"]["source"] >= 1
        assert report["clients"]["target"] == report["clients"]["source"]

    def test_verify_migration_reports_mismatches(self):
        report = {
            "devices": {"source": 5, "target": 5},
            "clients": {"source": 3, "target": 2},
        }
        mismatches = verify_migration(report)
        assert mismatches == ["clients"]

    def test_verify_migration_empty_on_full_match(self):
        report = {"devices": {"source": 5, "target": 5}}
        assert verify_migration(report) == []

    def test_migration_preserves_ids_for_fk_integrity(self, two_engines):
        source_engine, target_engine = two_engines
        source_db = Database(source_engine)
        device_id = source_db.add_device(
            {
                "order_number": "00001",
                "receipt_date": "2026-01-01",
                "device_type": "Ноутбук",
                "client_name": "Иван Иванов",
                "phone": "+79991234567",
                "status": "Диагностика",
            }
        )

        target_engine.create_tables()
        migrate_data(source_engine, target_engine)

        target_db = Database(target_engine)
        migrated_device = target_db.get_device(device_id)
        assert migrated_device is not None
        assert migrated_device["order_number"] == "00001"

    def test_migration_handles_forward_referencing_self_fk(self, two_engines):
        """Регрессия: сотрудник с меньшим ID может ссылаться (updated_by_id)
        на сотрудника с БОЛЬШИМ ID (кто угодно может отредактировать чью
        угодно запись) — раньше это падало IntegrityError при миграции,
        т.к. Session.merge() внутри цикла по строкам автофлашит уже
        смёрженные, ещё не закоммиченные строки в порядке итерации, а не в
        порядке зависимостей. Найдено пост-фичным аудитом сессии."""
        from sqlalchemy.orm import Session

        from database.sqlalchemy_models import Employee

        source_engine, target_engine = two_engines
        source_engine.create_tables()

        with Session(source_engine.get_engine()) as s:
            first = Employee(full_name="Первый Сотрудник", login="first")
            s.add(first)
            s.flush()  # получаем first.id, не коммитим ещё
            first_id = first.id

            second = Employee(full_name="Второй Сотрудник", login="second")
            s.add(second)
            s.flush()
            second_id = second.id

            # first (меньший ID) ссылается на second (больший ID) —
            # ровно тот сценарий, что ломал наивную вставку по порядку.
            first.updated_by_id = second_id
            s.commit()

        target_engine.create_tables()
        report = migrate_data(source_engine, target_engine)  # не должно бросить IntegrityError

        assert report["employees"]["source"] == 2
        assert report["employees"]["target"] == 2

        with Session(target_engine.get_engine()) as s:
            migrated_first = s.get(Employee, first_id)
            assert migrated_first.updated_by_id == second_id


class TestResetTargetSequences:
    """Регрессия AUDIT_v25 (fragile zone, MEDIUM): migrate_data() не
    сбрасывал identity-последовательность PostgreSQL после переноса строк
    с явными PK — первый органический add_device() после миграции получал
    id=1, конфликтуя с уже перенесённой строкой. Фикс — no-op для всех
    движков, кроме postgresql (SQLite выводит id из MAX(rowid), сбрасывать
    нечего); реальный Postgres-путь непроверен без живого сервера."""

    def test_noop_for_non_postgres_target(self, two_engines):
        """SQLiteEngine.db_type == "sqlite" -> сброс последовательности не
        должен даже пытаться выполниться (и тем более не должен падать)."""
        from sqlalchemy.orm import Session

        source_engine, target_engine = two_engines
        target_engine.create_tables()
        with Session(target_engine.get_engine()) as s:
            _reset_target_sequences(s, target_engine, ["devices", "employees"])
            # Не бросило — контракт "no-op на не-postgres" подтверждён.
