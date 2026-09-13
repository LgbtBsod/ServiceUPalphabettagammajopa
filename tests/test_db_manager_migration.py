#!/usr/bin/env python3

"""Тесты для database/db_manager.py::Database.migrate_client_dbs() —
регрессия workflow-найденного бага: cl_conn закрывался только на success/
early-continue путях; любое исключение МЕЖДУ open() и этими close()
(например, отсутствие таблицы repair_history в конкретном клиентском
файле) утекало sqlite3-соединение/файловый дескриптор."""

from __future__ import annotations

import os
import sqlite3

from database.db_manager import Database


def _rename_probe_unlocked(path: str) -> bool:
    """os.rename(path, path) — надёжная проба "файл не занят" на Windows:
    обычный open() по умолчанию НЕ детектирует чужой открытый хендл (файлы
    открываются в разделяемом режиме), а переименование требует
    эксклюзивного доступа и падает WinError 32, пока есть любой другой
    открытый хендл (см. tests/test_print_utils.py — тот же приём)."""
    try:
        os.rename(path, path)
        return True
    except OSError:
        return False


def test_migrate_client_dbs_closes_connection_even_when_a_file_errors(tmp_path, monkeypatch):
    main_db_path = tmp_path / "main.db"
    database = Database(str(main_db_path))

    clients_dir = tmp_path / "DBClients"
    clients_dir.mkdir()
    bad_client_db = clients_dir / "ivanov_79991234567.db"

    # Валидный sqlite-файл БЕЗ таблицы repair_history — та самая ситуация из
    # workflow-найденного бага (битый/несовместимый клиентский файл).
    conn = sqlite3.connect(str(bad_client_db))
    conn.execute("CREATE TABLE unrelated (id INTEGER)")
    conn.commit()
    conn.close()

    monkeypatch.setattr("config.CLIENTS_DB_DIR", str(clients_dir))

    migrated = database.migrate_client_dbs()

    assert migrated == 0
    assert _rename_probe_unlocked(str(bad_client_db)), (
        "соединение с клиентской БД осталось открытым после ошибки миграции"
    )

    database.conn.close()
