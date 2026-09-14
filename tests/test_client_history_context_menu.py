#!/usr/bin/env python3

"""Тесты для gui/dialogs/client_history.py::ClientHistoryWindow — контекстное
меню (ПКМ по строке истории) никогда не скрывало себя после клика по
кнопке, оставаясь поверх окна навсегда (workflow-найденный баг).

Сиблинг-реализация в gui/main_window_parts/widgets_mixin.py::create_context_menu()
решает ровно эту проблему, оборачивая каждую command в withdraw()-перед-
вызовом — этот паттерн не был скопирован при переносе аналогичного меню в
client_history.py."""

from __future__ import annotations

import os
import tempfile

import customtkinter as ctk
import pytest

pytest.importorskip("gui")

from database.client_db import ClientDatabaseManager
from database.db_config import DatabaseConfig
from database.engines.sqlite_engine import SQLiteEngine
from database.sqlalchemy_database import Database
from gui.dialogs.client_history import ClientHistoryWindow
from utils.colors import get_colors


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
def history_window(tk_root, db, monkeypatch):
    # Команды меню не должны реально ничего открывать/печатать в этом
    # тесте — важна только сама логика "скрыть меню перед вызовом команды".
    # Патчим НА КЛАССЕ до конструирования: _make_wrapper() в create_widgets()
    # захватывает self.edit_order_from_history/self.print_act_from_history в
    # момент создания кнопок, так что патч должен быть виден уже тогда.
    calls = []
    monkeypatch.setattr(
        ClientHistoryWindow,
        "edit_order_from_history",
        lambda self, *a, **k: calls.append("edit"),
    )
    monkeypatch.setattr(
        ClientHistoryWindow,
        "print_act_from_history",
        lambda self, *a, **k: calls.append("print"),
    )

    client_db = ClientDatabaseManager(main_db=db)
    win = ClientHistoryWindow(
        tk_root,
        db,
        client_db,
        client_name="Тест Тестов",
        client_phone="+79990000000",
        client_status="Обычный",
        colors=get_colors("light"),
    )
    win._test_calls = calls
    yield win
    if win.winfo_exists():
        win.destroy()


def _find_button_by_text(widget, text: str):
    for child in widget.winfo_children():
        if isinstance(child, ctk.CTkButton) and child.cget("text") == text:
            return child
        found = _find_button_by_text(child, text)
        if found is not None:
            return found
    return None


class TestContextMenuHidesAfterAction:
    def test_menu_is_hidden_by_default(self, history_window):
        assert not history_window.history_context_menu.winfo_viewable()

    def test_edit_button_withdraws_the_menu(self, history_window):
        history_window.history_context_menu.deiconify()
        btn = _find_button_by_text(
            history_window.history_context_menu, "✏️ Редактировать заказ"
        )
        assert btn is not None
        btn.invoke()

        assert history_window._test_calls == ["edit"]
        assert not history_window.history_context_menu.winfo_viewable(), (
            "context menu must withdraw() itself after a button action — "
            "otherwise it stays floating on top of the window forever"
        )

    def test_print_button_withdraws_the_menu(self, history_window):
        history_window.history_context_menu.deiconify()
        btn = _find_button_by_text(history_window.history_context_menu, "🖨️ Печать акта")
        assert btn is not None
        btn.invoke()

        assert history_window._test_calls == ["print"]
        assert not history_window.history_context_menu.winfo_viewable()
