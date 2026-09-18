#!/usr/bin/env python3

"""Regression test for gui/main_window_parts/device_dialogs_mixin.py's
show_client_history() — Workflow-found off-by-one: the Treeview's real
column order (see `columns` tuple in widgets_mixin.py and the `values`
tuple `_render_device_row()` builds, devices_table_mixin.py) is
0=order_number, 1=receipt_date, 2=days, 3=completion_date, 4=device_name,
5=client_name, 6=phone - but show_client_history() read values[4]/values[5]
(device name / client name) instead of values[5]/values[6] (client name /
phone). Right-clicking any order and choosing "История клиента" opened the
window with the device's name where the client's name should be, and the
client's name where the phone should be - every invocation of this feature
was broken. This test builds a row the SAME way the real table does
(_render_device_row) rather than hand-encoding the tuple shape a second
time, so it can't independently drift the same way the bug did."""

from __future__ import annotations

import os
import tempfile
from tkinter import ttk

import pytest

pytest.importorskip("gui")

from database.db_config import DatabaseConfig
from database.engines.sqlite_engine import SQLiteEngine
from database.sqlalchemy_database import Database
from gui.main_window_parts.device_dialogs_mixin import DeviceDialogsMixin
from gui.main_window_parts.devices_table_mixin import DevicesTableMixin


class _FakeMainWindow(DeviceDialogsMixin, DevicesTableMixin):
    def __init__(self, root, db):
        self.root = root
        self.db = db
        self.client_db = None
        self.settings = {"remind_overdue": True, "overdue_days": 14}
        self.colors = {}
        self.photo_manager = None
        self.report_gen = None
        self.employees_api = None
        self.lock_api = None

        columns = (
            "Заказ №", "Дата приёма", "Дней", "Дата выдачи", "Устройство",
            "Клиент", "Телефон", "Неисправность", "Статус", "Приоритет",
            "Инженер", "Цена", "Фото",
        )
        self.tree = ttk.Treeview(root, columns=columns, show="headings")


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
def stub_client_history_window(monkeypatch):
    """Real ClientHistoryWindow builds a CTkToplevel - stub it to just
    record the args show_client_history() passed it, same reasoning as
    monkeypatching messagebox elsewhere in this test suite (no real modal
    window on this non-headless machine)."""
    captured = {}

    class _Stub:
        def __init__(
            self, root, db, client_db, client_name, client_phone,
            client_status, colors, **kwargs,
        ):
            captured["client_name"] = client_name
            captured["client_phone"] = client_phone
            captured["client_status"] = client_status

    monkeypatch.setattr(
        "gui.main_window_parts.device_dialogs_mixin.ClientHistoryWindow", _Stub
    )
    return captured


class TestShowClientHistoryReadsTheRightColumns:
    def test_extracts_the_real_client_name_and_phone_not_the_device_name(
        self, tk_root, db, stub_client_history_window
    ):
        device_id = db.add_device(
            {
                "order_number": "1",
                "device_type": "Ноутбук",
                "brand": "Apple",
                "model": "MacBook Air",
                "client_name": "Иван Иванов",
                "phone": "+79991234567",
                "defect": "Не включается",
            }
        )
        device = db.get_device(device_id)

        app = _FakeMainWindow(tk_root, db)
        values, _tag = app._render_device_row(device)
        # sanity: prove the row really does put the device name before the
        # client name, i.e. the bug's premise is accurate for real rows.
        assert "Apple" in values[4]
        assert values[5] == "Иван Иванов"

        app.tree.insert("", "end", values=values)
        app.tree.selection_set(app.tree.get_children()[0])

        app.show_client_history()

        assert stub_client_history_window["client_name"] == "Иван Иванов"
        assert "999" in stub_client_history_window["client_phone"]
        assert "Apple" not in stub_client_history_window["client_name"]
