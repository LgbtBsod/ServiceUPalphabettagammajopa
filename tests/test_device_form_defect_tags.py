#!/usr/bin/env python3

"""Regression test for gui/dialogs/device_form_parts/widgets_mixin.py's
defect-tag chips ("Теги неисправности") — a dictionary-backed ("defects",
domain.constants.DICTIONARY_TYPES) child-table feature (DeviceDefectRecord)
that ADDS structured tags alongside the free-text "Неисправность" field,
not instead of it. Mirrors tests/test_gui_flet.py::TestOrderFormDefectTags
for the classic customtkinter GUI."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

pytest.importorskip("gui")

from database import ClientDatabaseManager, Database
from database.db_config import DatabaseConfig
from database.engines.sqlite_engine import SQLiteEngine
from gui.dialogs.device_form import DeviceFormDialog
from managers.photo_manager import PhotoManager
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


def _make_dialog(tk_root, db, *, is_new=True, device_data=None):
    return DeviceFormDialog(
        tk_root,
        db,
        ClientDatabaseManager(db),
        PhotoManager(settings=None),
        get_colors("light"),
        is_new=is_new,
        device_data=device_data,
    )


@pytest.fixture
def dialog_no_dialogs(monkeypatch):
    """Ни один тест здесь не должен реально показать messagebox — тот
    создал бы настоящее модальное окно на этой (не headless) машине и
    повесил бы процесс (тот же риск, что и в
    tests/test_device_form_model_dictionary.py)."""
    shown_errors: list[str] = []
    monkeypatch.setattr(
        "gui.dialogs.device_form_parts.save_mixin.messagebox.showerror",
        lambda _title, message: shown_errors.append(message),
    )
    monkeypatch.setattr(
        "gui.dialogs.device_form_parts.save_mixin.messagebox.showinfo",
        lambda *_a, **_kw: None,
    )
    monkeypatch.setattr(
        "gui.dialogs.device_form_parts.save_mixin.messagebox.askyesno",
        lambda *_a, **_kw: False,
    )
    return shown_errors


class TestDefectTagsState:
    def test_new_device_starts_with_no_tags(self, tk_root, db):
        dialog = _make_dialog(tk_root, db)
        try:
            assert dialog.defect_tags_state == []
        finally:
            if dialog.winfo_exists():
                dialog.destroy()

    def test_editing_a_device_preloads_its_existing_tags(self, tk_root, db):
        device_id = db.add_device(
            {
                "order_number": "1",
                "client_name": "Иван",
                "phone": "+79990000000",
                "defect": "Не включается",
                "defect_tags_json": json.dumps([{"text": "Разбит экран"}]),
            }
        )
        device_data = db.get_device(device_id)

        dialog = _make_dialog(tk_root, db, is_new=False, device_data=device_data)
        try:
            assert dialog.defect_tags_state == [
                {"text": "Разбит экран", "is_from_dictionary": False}
            ]
        finally:
            if dialog.winfo_exists():
                dialog.destroy()

    def test_adding_a_tag_appends_to_state_and_clears_the_input(self, tk_root, db):
        dialog = _make_dialog(tk_root, db)
        try:
            dialog.defect_tag_combo.set("Своя нестандартная поломка")
            dialog._add_defect_tag()

            assert dialog.defect_tags_state == [
                {"text": "Своя нестандартная поломка", "is_from_dictionary": False}
            ]
            assert dialog.defect_tag_combo.get() == ""
        finally:
            if dialog.winfo_exists():
                dialog.destroy()

    def test_adding_a_dictionary_value_marks_it_as_from_dictionary(self, tk_root, db):
        dialog = _make_dialog(tk_root, db)
        try:
            known = dialog.db.get_dict_values("defects")[0]
            dialog.defect_tag_combo.set(known)
            dialog._add_defect_tag()

            assert dialog.defect_tags_state == [
                {"text": known, "is_from_dictionary": True}
            ]
        finally:
            if dialog.winfo_exists():
                dialog.destroy()

    def test_adding_a_duplicate_tag_is_ignored(self, tk_root, db):
        dialog = _make_dialog(tk_root, db)
        try:
            dialog.defect_tag_combo.set("Разбит экран")
            dialog._add_defect_tag()
            dialog.defect_tag_combo.set("Разбит экран")
            dialog._add_defect_tag()

            assert len(dialog.defect_tags_state) == 1
        finally:
            if dialog.winfo_exists():
                dialog.destroy()

    def test_removing_a_tag_updates_state(self, tk_root, db):
        dialog = _make_dialog(tk_root, db)
        try:
            dialog.defect_tag_combo.set("Своя нестандартная поломка")
            dialog._add_defect_tag()
            dialog.defect_tag_combo.set("Не заряжается")
            dialog._add_defect_tag()

            dialog._remove_defect_tag(0)

            assert dialog.defect_tags_state == [
                {"text": "Не заряжается", "is_from_dictionary": True}
            ]
        finally:
            if dialog.winfo_exists():
                dialog.destroy()


class TestDefectTagsSaving:
    def test_saving_a_new_device_persists_its_tags(
        self, tk_root, db, dialog_no_dialogs
    ):
        dialog = _make_dialog(tk_root, db)
        try:
            dialog.device_type_combo.set("Ноутбук")
            dialog.brand_combo.set("Apple")
            dialog.model_combo.set("MacBook Air")
            dialog.defect_text.insert("1.0", "Не включается")
            dialog.client_name_entry.insert(0, "Тестовый Клиент")
            dialog.phone_entry.insert(0, "+79991234567")
            dialog.defect_tag_combo.set("Разбит экран")
            dialog._add_defect_tag()

            dialog.save()

            assert dialog_no_dialogs == []
            devices = db.get_all_devices()
            device = next(d for d in devices if d["client_name"] == "Тестовый Клиент")
            tags = db.get_device_defects_from_db(device["id"])
            assert [t["text"] for t in tags] == ["Разбит экран"]
        finally:
            if dialog.winfo_exists():
                dialog.destroy()

    def test_editing_only_tags_persists_the_change(
        self, tk_root, db, dialog_no_dialogs
    ):
        """Регрессия: без Device.defect_tags как scalar-колонки в
        change-detection update_device(), правка ИСКЛЮЧИТЕЛЬНО тегов (без
        изменения других полей) не выставляла бы changed=True и молча не
        сохранялась."""
        device_id = db.add_device(
            {
                "order_number": "1",
                "device_type": "Ноутбук",
                "brand": "Apple",
                "model": "MacBook Air",
                "client_name": "Тестовый Клиент",
                "phone": "+79991234567",
                "defect": "Не включается",
                "defect_tags_json": json.dumps([{"text": "Разбит экран"}]),
            }
        )
        device_data = db.get_device(device_id)
        dialog = _make_dialog(tk_root, db, is_new=False, device_data=device_data)
        try:
            dialog.defect_tag_combo.set("Не заряжается")
            dialog._add_defect_tag()

            dialog.save()

            assert dialog_no_dialogs == []
            tags = db.get_device_defects_from_db(device_id)
            assert {t["text"] for t in tags} == {"Разбит экран", "Не заряжается"}
        finally:
            if dialog.winfo_exists():
                dialog.destroy()
