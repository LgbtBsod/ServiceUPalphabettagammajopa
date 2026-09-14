#!/usr/bin/env python3

"""Тесты для database/engines/__init__.py::get_database_engine() — регрессия
workflow-найденного бага: unsync check-then-act на module-level
_engine_instance, идентичный уже пофикшенным (double-checked locking)
get_core()/get_container()/get_event_bus()/get_plugin_manager()/
get_module_cache(). DatabaseCore.__init__ вызывает это на каждом обычном
пути построения Database() — два потока, конкурентно конструирующих
DatabaseCore для одного файла (GUI-поток vs. поток запуска PWA-сервера),
могли создать по отдельному SQLAlchemy Engine/пулу соединений на один и тот
же файл, молча осиротив один из них (без .dispose())."""

from __future__ import annotations

import os
import tempfile
import threading
import time

import database.engines as engines_module
from database.db_config import DatabaseConfig


class TestGetDatabaseEngineSingletonIsThreadSafe:
    def test_concurrent_first_access_returns_the_same_instance(self, monkeypatch):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

        engines_module.reset_database_engine()
        monkeypatch.setattr(
            "database.db_config.get_db_config",
            lambda: DatabaseConfig(database=path),
        )

        original_create = engines_module.create_engine_for

        def _slow_create(config):
            time.sleep(0.05)
            return original_create(config)

        monkeypatch.setattr(engines_module, "create_engine_for", _slow_create)

        try:
            results = []
            barrier = threading.Barrier(10)

            def _worker():
                barrier.wait()
                results.append(engines_module.get_database_engine())

            threads = [threading.Thread(target=_worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

            assert len({id(r) for r in results}) == 1, (
                "concurrent first-time get_database_engine() calls must all "
                "return the exact same engine instance"
            )
        finally:
            engines_module.reset_database_engine()
            if os.path.exists(path):
                os.remove(path)
