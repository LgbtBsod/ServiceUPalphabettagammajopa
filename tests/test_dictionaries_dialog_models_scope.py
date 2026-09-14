#!/usr/bin/env python3

"""Regression test for gui/dialogs/dictionaries.py's "models" tab — models
are scoped per brand (domain.constants.models_dict_type()), not one flat
list, per explicit user request ("список на 10 листов A1" otherwise).
Mirrors the equivalent Flet coverage in tests/test_gui_flet_dictionaries.py
(TestBrandScopedModels), but exercises the real classic-GUI dialog."""

from __future__ import annotations

import os
import tempfile

import pytest

pytest.importorskip("gui")

from database.db_config import DatabaseConfig
from database.engines.sqlite_engine import SQLiteEngine
from database.sqlalchemy_database import Database
from domain.constants import models_dict_type
from gui.dialogs.dictionaries import DictionariesManagerWindow
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
def dialog(tk_root, db, monkeypatch):
    # Ни один из этих тестов не должен реально показать messagebox — тот
    # создал бы настоящее модальное окно на этой (не headless) машине и
    # повесил бы процесс в ожидании клика (тот же риск, что и в
    # tests/test_device_form_model_dictionary.py).
    monkeypatch.setattr(
        "gui.dialogs.dictionaries.messagebox.showinfo", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(
        "gui.dialogs.dictionaries.messagebox.showerror", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(
        "gui.dialogs.dictionaries.messagebox.showwarning", lambda *_a, **_kw: None
    )
    dlg = DictionariesManagerWindow(tk_root, db, get_colors("light"))
    yield dlg
    if dlg.winfo_exists():
        dlg.destroy()


class TestModelsTabIsBrandScoped:
    def test_models_tab_has_a_brand_scope_selector(self, dialog):
        assert "models" in dialog.scope_combos, (
            "models — scoped_by='brands' в domain.constants.DICTIONARY_TYPES, "
            "поэтому её вкладка должна показывать доп. комбобокс выбора бренда"
        )

    def test_other_tabs_have_no_scope_selector(self, dialog):
        assert "brands" not in dialog.scope_combos
        assert "device_types" not in dialog.scope_combos

    def test_defaults_scope_to_the_first_available_brand(self, dialog, db):
        assert dialog.scope_values["models"] == db.get_dict_values("brands")[0]

    def test_adding_a_model_stores_it_under_the_selected_brands_dict_type(
        self, dialog, db
    ):
        dialog.scope_values["models"] = "Apple"
        entry = dialog.entries["models"]
        entry["value"].insert(0, "iPhone 13")

        dialog.add_new_item("models", entry["value"], entry["info"])

        assert db.get_dict_values(models_dict_type("Apple")) == ["iPhone 13"]
        assert db.get_dict_values("models") == []
        assert db.get_dict_values(models_dict_type("Samsung")) == []

    def test_switching_brand_scope_reloads_that_brands_models(self, dialog, db):
        db.add_dict_value(models_dict_type("Apple"), "iPhone 13")
        db.add_dict_value(models_dict_type("Samsung"), "Galaxy S22")

        dialog._on_scope_change("models", "Samsung")

        assert dialog.scope_values["models"] == "Samsung"
        tree = dialog.trees["models"]
        values = [tree.item(iid)["values"][1] for iid in tree.get_children()]
        assert values == ["Galaxy S22"]
