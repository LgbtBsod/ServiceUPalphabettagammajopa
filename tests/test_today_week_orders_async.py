#!/usr/bin/env python3

"""Regression test for gui/main_window_parts/devices_table_mixin.py's
show_today_orders()/show_week_orders()/show_overdue_orders() — Workflow-found
bug: unlike their sibling filter methods in the same class/file
(load_devices, apply_filters, search_devices), these fetched/computed the
WHOLE devices table synchronously on the calling (GUI) thread, freezing the
window for the duration of the query as order history grows. Fixed by
routing them through the same AsyncLoadMixin._run_async() pattern the
sibling methods already use.

Reuses the deterministic _StubRoot/_SyncCore test doubles from
test_async_load_mixin.py rather than re-implementing them - they already
exist specifically to make _run_async's background-thread dispatch
synchronous/inspectable for tests."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta
from tkinter import ttk

import pytest

pytest.importorskip("gui")

from database.db_config import DatabaseConfig
from database.engines.sqlite_engine import SQLiteEngine
from database.sqlalchemy_database import Database
from gui.main_window_parts.async_load_mixin import AsyncLoadMixin
from gui.main_window_parts.devices_table_mixin import DevicesTableMixin
from gui.widgets.skeleton import SKELETON_TAG
from tests.test_async_load_mixin import _StubRoot, _SyncCore


class _Host(DevicesTableMixin, AsyncLoadMixin):
    def __init__(self, tree, db, core):
        self.root = _StubRoot()
        self._core = core
        self.tree = tree
        self.db = db
        self.settings = {"remind_overdue": True, "overdue_days": 14}
        self.status_bar_messages: list[str] = []

    def update_status_bar(self, text):
        self.status_bar_messages.append(text)

    def _on_devices_load_error(self, exc):
        raise exc


_COLUMNS = (
    "Заказ №", "Дата приёма", "Дней", "Дата выдачи", "Устройство",
    "Клиент", "Телефон", "Неисправность", "Статус", "Приоритет",
    "Инженер", "Цена", "Фото",
)


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = SQLiteEngine(DatabaseConfig(database=path))
    database = Database(engine)
    yield database
    engine.dispose()
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def host(tk_root, db):
    tree = ttk.Treeview(tk_root, columns=_COLUMNS, show="headings")
    return _Host(tree, db, _SyncCore())


class TestShowTodayOrdersUsesAsyncLoad:
    def test_fetch_runs_through_run_async_not_synchronously(self, db, host, monkeypatch):
        """The DB call must happen inside a _run_async-dispatched fetch,
        not directly on the calling thread - proven by checking it goes
        through the same ThreadManager stub path search_devices/
        apply_filters already use (_SyncCore records nothing special, but
        the result only lands on the tree after run_pending())."""
        db.add_device(
            {
                "order_number": "1",
                "client_name": "Иван",
                "phone": "+79990000000",
                "receipt_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

        host.show_today_orders()
        # До run_pending() (имитирует ещё не тикнувший Tk mainloop) дерево
        # должно содержать только skeleton-плейсхолдеры (insert_skeleton_rows,
        # вызывается синхронно ДО запроса), а не реальную строку заказа -
        # подтверждает, что применение результата действительно отложено
        # через root.after(), а не выполнено немедленно синхронно.
        assert all(
            SKELETON_TAG in host.tree.item(i, "tags")
            for i in host.tree.get_children()
        )

        host.root.run_pending()

        assert len(host.tree.get_children()) == 1
        assert any("сегодня" in m for m in host.status_bar_messages)

    def test_only_todays_orders_are_shown(self, db, host):
        db.add_device(
            {
                "order_number": "1",
                "client_name": "Сегодня",
                "phone": "+79990000001",
                "receipt_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        db.add_device(
            {
                "order_number": "2",
                "client_name": "Вчера",
                "phone": "+79990000002",
                "receipt_date": (datetime.now() - timedelta(days=2)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }
        )

        host.show_today_orders()
        host.root.run_pending()

        rows = [host.tree.item(i)["values"] for i in host.tree.get_children()]
        names = {r[5] for r in rows}
        assert names == {"Сегодня"}


class TestShowWeekOrdersUsesAsyncLoad:
    def test_fetch_runs_through_run_async_not_synchronously(self, db, host):
        db.add_device(
            {
                "order_number": "1",
                "client_name": "Иван",
                "phone": "+79990000000",
                "receipt_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

        host.show_week_orders()
        assert all(
            SKELETON_TAG in host.tree.item(i, "tags")
            for i in host.tree.get_children()
        )

        host.root.run_pending()

        assert len(host.tree.get_children()) == 1
        assert any("неделю" in m for m in host.status_bar_messages)

    def test_orders_older_than_a_week_are_excluded(self, db, host):
        db.add_device(
            {
                "order_number": "1",
                "client_name": "Недавно",
                "phone": "+79990000001",
                "receipt_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        db.add_device(
            {
                "order_number": "2",
                "client_name": "Давно",
                "phone": "+79990000002",
                "receipt_date": (datetime.now() - timedelta(days=30)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }
        )

        host.show_week_orders()
        host.root.run_pending()

        rows = [host.tree.item(i)["values"] for i in host.tree.get_children()]
        names = {r[5] for r in rows}
        assert names == {"Недавно"}


class TestShowOverdueOrdersUsesAsyncLoad:
    def test_fetch_runs_through_run_async_not_synchronously(self, db, host):
        db.add_device(
            {
                "order_number": "1",
                "client_name": "Просрочен",
                "phone": "+79990000000",
                "receipt_date": (datetime.now() - timedelta(days=30)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }
        )

        host.show_overdue_orders()
        assert all(
            SKELETON_TAG in host.tree.item(i, "tags")
            for i in host.tree.get_children()
        )

        host.root.run_pending()

        assert len(host.tree.get_children()) == 1
        assert any("Просроченных" in m for m in host.status_bar_messages)

    def test_orders_within_the_threshold_are_excluded(self, db, host):
        db.add_device(
            {
                "order_number": "1",
                "client_name": "Недавно",
                "phone": "+79990000001",
                "receipt_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        db.add_device(
            {
                "order_number": "2",
                "client_name": "Давно",
                "phone": "+79990000002",
                "receipt_date": (datetime.now() - timedelta(days=30)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }
        )

        host.show_overdue_orders()
        host.root.run_pending()

        rows = [host.tree.item(i)["values"] for i in host.tree.get_children()]
        names = {r[5] for r in rows}
        assert names == {"Давно"}
