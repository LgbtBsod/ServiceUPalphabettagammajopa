#!/usr/bin/env python3

"""Regression test for gui/dialogs/device_form_parts/widgets_mixin.py —
wiring "Модель" into a dictionary-backed CTkComboBox (free text OR pick
from a per-brand "models:<Бренд>" dict_type, domain/constants.py::
models_dict_type()), matching how "Тип устройства"/"Бренд" already work
— except models are scoped to the currently selected brand (one flat
list of every brand's models at once was explicitly rejected as
unusable: "список на 10 листов A1").

Moving "model" from the plain-CTkEntry branch into the CTkComboBox branch
meant every OTHER read/write site keyed on the old `self.model_entry`
attribute (gui/dialogs/device_form_parts/save_mixin.py,
gui/dialogs/device_form_parts/locking_mixin.py) had to be updated to
`self.model_combo` too — several of those reads were guarded by
`hasattr(self, "model_entry")`, so a missed rename would have silently
saved an empty model on every order instead of raising an AttributeError.
This test actually constructs the real dialog (not just a static name
check) so a missed rename fails loudly here instead of silently in
production."""

from __future__ import annotations

import os
import tempfile

import pytest

pytest.importorskip("gui")

from database import ClientDatabaseManager, Database
from database.db_config import DatabaseConfig
from database.engines.sqlite_engine import SQLiteEngine
from domain.constants import models_dict_type
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


class TestModelFieldIsADictionaryBackedCombo:
    def test_model_combo_is_populated_from_that_brands_models_at_construction(
        self, tk_root, db
    ):
        db.add_dict_value(models_dict_type("Apple"), "iPhone 13")
        db.add_dict_value(models_dict_type("Samsung"), "Galaxy S22")
        device_id = db.add_device(
            {
                "order_number": "1",
                "device_type": "Смартфон",
                "brand": "Apple",
                "model": "iPhone 13",
                "client_name": "Иван",
                "phone": "+79990000000",
                "defect": "Не включается",
            }
        )
        device_data = db.get_device(device_id)

        dialog = _make_dialog(tk_root, db, is_new=False, device_data=device_data)
        try:
            assert hasattr(dialog, "model_combo"), (
                "Модель должна строиться как CTkComboBox (self.model_combo), "
                "как Тип устройства/Бренд — не остаться plain CTkEntry "
                "(self.model_entry)"
            )
            values = dialog.model_combo.cget("values")
            assert "iPhone 13" in values
            assert "Galaxy S22" not in values, (
                "модели ДРУГОГО бренда (Samsung) не должны просачиваться в "
                "список подсказок для Apple — справочник моделей отдельный "
                "на каждый бренд"
            )
        finally:
            if dialog.winfo_exists():
                dialog.destroy()

    def test_changing_brand_refreshes_the_model_suggestions_live(self, tk_root, db):
        db.add_dict_value(models_dict_type("Apple"), "iPhone 13")
        db.add_dict_value(models_dict_type("Samsung"), "Galaxy S22")

        dialog = _make_dialog(tk_root, db)
        try:
            dialog.brand_combo.set("Samsung")
            # CTkComboBox.configure(command=...) не срабатывает на .set()
            # (программная установка — не выбор мышью из списка) — зовём
            # тот же callback напрямую, как это делает сам виджет при
            # реальном клике по варианту в выпадающем списке.
            dialog.brand_combo.cget("command")(None)

            assert dialog.model_combo.cget("values") == ["Galaxy S22"]
        finally:
            if dialog.winfo_exists():
                dialog.destroy()

    def test_saving_persists_a_freely_typed_model_not_in_the_dictionary(
        self, tk_root, db, monkeypatch
    ):
        # Защита от зависания: и валидационный messagebox.showerror(), И
        # (на успешном пути save() для is_new=True) messagebox.showinfo()
        # "Заказ создан!" создали бы РЕАЛЬНОЕ модальное окно на этой (не
        # headless) машине и повесили бы тестовый процесс в ожидании
        # клика, которого никто не сделает (эмпирически воспроизведено —
        # именно showinfo на успешном пути повесил первый прогон этого
        # теста). Подменяем оба на запись в список.
        shown_errors: list[str] = []
        monkeypatch.setattr(
            "gui.dialogs.device_form_parts.save_mixin.messagebox.showerror",
            lambda _title, message: shown_errors.append(message),
        )
        monkeypatch.setattr(
            "gui.dialogs.device_form_parts.save_mixin.messagebox.showinfo",
            lambda *_a, **_kw: None,
        )

        dialog = _make_dialog(tk_root, db)
        try:
            dialog.device_type_combo.set("Ноутбук")
            dialog.brand_combo.set("Lenovo")
            dialog.model_combo.set(
                "ThinkPad X1 Carbon Gen 11"
            )  # не из справочника — ручной ввод
            dialog.defect_text.insert("1.0", "Не включается")
            dialog.client_name_entry.insert(0, "Тестовый Клиент")
            dialog.phone_entry.insert(0, "+79991234567")

            dialog.save()

            assert shown_errors == [], f"save() hit a validation error: {shown_errors}"
            devices = db.get_all_devices()
            assert any(
                d["model"] == "ThinkPad X1 Carbon Gen 11" for d in devices
            ), (
                "manual (non-dictionary) model text must still be saved — "
                "the user explicitly asked to keep free text entry "
                "alongside the dictionary"
            )
        finally:
            if dialog.winfo_exists():
                dialog.destroy()
