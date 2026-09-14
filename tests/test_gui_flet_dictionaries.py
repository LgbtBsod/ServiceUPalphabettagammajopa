#!/usr/bin/env python3

"""Тесты чистой логики gui_flet/views_dictionaries.py::DictionariesView —
Flet-эквивалент gui/dialogs/dictionaries.py.

Как и в tests/test_gui_flet.py — без поднятия реальной страницы/сессии
(Control-дерево Flet не тестируется через настоящий рендер headless)."""

from __future__ import annotations

import os
import tempfile

import flet as ft
import pytest

import gui  # noqa: F401 — обход циклического импорта managers/__init__.py
from database.db_config import DatabaseConfig
from database.engines.sqlite_engine import SQLiteEngine
from database.sqlalchemy_database import Database
from domain.constants import DICTIONARY_TYPES, models_dict_type
from gui_flet.theme import colors
from gui_flet.views_dictionaries import DictionariesView


class _FakePage:
    def __init__(self):
        self.dialogs = []

    def update(self):
        pass

    def show_dialog(self, dialog):
        self.dialogs.append(dialog)

    def pop_dialog(self):
        if self.dialogs:
            self.dialogs.pop()


class _FakeApp:
    def __init__(self, db):
        self.db = db
        self.colors = colors("light")
        self.page = _FakePage()
        self.snackbars = []
        self.rerender_calls = 0

    def show_snackbar(self, message, error=False):
        self.snackbars.append((message, error))

    def rerender(self):
        self.rerender_calls += 1


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
def app(db):
    return _FakeApp(db)


@pytest.fixture
def view(app):
    return DictionariesView(app)


def _list_column(card):
    """list_card — второй Container в верхнем ResponsiveRow; сама карточка
    оборачивает Column([title, spacer, Column(rows, ...)])."""
    inner_column = card.content
    return inner_column.controls[2]


def _edit_column(rendered):
    """edit_card — Container(col=...) -> Container (карточка) -> Column
    [title, spacer, value_field, info_field, spacer, Row(buttons)]."""
    edit_card = rendered.controls[2].controls[1].content
    return edit_card.content


def _header_controls(rendered):
    """Верхний Row — [title, spacer, (scope_selector,) type_selector].
    scope_selector присутствует только для scoped_by-категорий (сейчас —
    "models"), так что искать по фиксированному индексу нельзя — ищем по
    подписи (label)."""
    return {c.label: c for c in rendered.controls[0].controls if hasattr(c, "label")}


# Категория "models" теперь scoped_by="brands" (домен-константа) — для
# generic CRUD-тестов (add/edit/delete), которым исторически был нужен
# ПУСТОЙ по умолчанию справочник, используем её всё так же, но явно
# фиксируем scope_value и читаем/пишем через models_dict_type(), а не
# буквальный dict_type="models" (который сам по себе больше нигде не
# хранит данные).
_TEST_BRAND = "Apple"  # входит в default_values справочника "brands"


class TestInitialRender:
    def test_defaults_to_the_first_dictionary_type(self, view):
        assert view.current_type == next(iter(DICTIONARY_TYPES))

    def test_seeded_defaults_render_as_list_tiles(self, view):
        rendered = view.render()
        list_card = rendered.controls[2].controls[0].content
        rows = _list_column(list_card).controls

        first_type = next(iter(DICTIONARY_TYPES))
        expected_values = DICTIONARY_TYPES[first_type]["default_values"]
        assert len(rows) == len(expected_values)
        assert rows[0].title.value == expected_values[0]

    def test_empty_dictionary_shows_placeholder_text(self, view):
        view.current_type = "models"
        view.scope_value = _TEST_BRAND
        rendered = view.render()
        list_card = rendered.controls[2].controls[0].content
        rows = _list_column(list_card).controls

        assert len(rows) == 1
        assert isinstance(rows[0], ft.Container)  # placeholder, not a ListTile
        assert "пока нет значений" in rows[0].content.value


class TestBrandScopedModels:
    """Regression: models — dict_type="models:<Бренд>", не плоский
    "models" — один общий список моделей всех брендов сразу стал бы
    нечитаемо длинным (прямая просьба пользователя: "список на 10 листов
    A1"). views_dictionaries.py показывает доп. селектор бренда для любой
    scoped_by-категории и подставляет models_dict_type(scope_value)
    вместо буквального current_type."""

    def test_models_category_shows_a_brand_scope_selector(self, view):
        view.current_type = "models"
        rendered = view.render()

        header = _header_controls(rendered)
        assert "Бренд" in header

    def test_non_scoped_category_has_no_scope_selector(self, view):
        view.current_type = "brands"
        rendered = view.render()

        header = _header_controls(rendered)
        assert "Бренд" not in header

    def test_defaults_scope_to_the_first_available_brand(self, view, db):
        view.current_type = "models"
        view.render()

        assert view.scope_value == db.get_dict_values("brands")[0]

    def test_adding_a_model_stores_it_under_the_selected_brands_dict_type(
        self, view, app, db
    ):
        view.current_type = "models"
        view.scope_value = _TEST_BRAND
        rendered = view.render()
        edit_card = _edit_column(rendered)
        value_field = edit_card.controls[2]
        save_btn = edit_card.controls[5].controls[0]

        value_field.value = "iPhone 13"
        save_btn.on_click(None)

        assert db.get_dict_values(models_dict_type(_TEST_BRAND)) == ["iPhone 13"]
        # Не протекает в общий/другой бренд.
        assert db.get_dict_values("models") == []
        assert db.get_dict_values(models_dict_type("Samsung")) == []

    def test_switching_brand_scope_clears_selection_and_shows_that_brands_models(
        self, view, db
    ):
        db.add_dict_value(models_dict_type("Apple"), "iPhone 13")
        db.add_dict_value(models_dict_type("Samsung"), "Galaxy S22")
        view.current_type = "models"
        view.scope_value = "Apple"
        view.selected_item_id = db.get_all_dict_items(models_dict_type("Apple"))[0]["id"]

        rendered = view.render()
        header = _header_controls(rendered)
        header["Бренд"].on_select(
            type("Event", (), {"control": type("Ctrl", (), {"value": "Samsung"})()})()
        )

        assert view.scope_value == "Samsung"
        assert view.selected_item_id is None

        rendered = view.render()
        list_card = rendered.controls[2].controls[0].content
        rows = _list_column(list_card).controls
        assert rows[0].title.value == "Galaxy S22"


class TestAddValue:
    def test_add_new_value_persists_and_shows_success_snackbar(self, view, app, db):
        view.current_type = "models"
        view.scope_value = _TEST_BRAND
        rendered = view.render()
        edit_card = _edit_column(rendered)
        value_field, info_field = edit_card.controls[2], edit_card.controls[3]
        save_btn = edit_card.controls[5].controls[0]

        value_field.value = "iPhone 13"
        info_field.value = "Apple, 2021"
        save_btn.on_click(None)

        assert db.get_dict_values(models_dict_type(_TEST_BRAND)) == ["iPhone 13"]
        assert app.snackbars[-1] == ("Значение добавлено", False)

    def test_add_with_empty_value_shows_error_and_does_not_persist(self, view, app, db):
        view.current_type = "models"
        view.scope_value = _TEST_BRAND
        rendered = view.render()
        edit_card = _edit_column(rendered)
        save_btn = edit_card.controls[5].controls[0]

        save_btn.on_click(None)

        assert db.get_dict_values(models_dict_type(_TEST_BRAND)) == []
        assert app.snackbars[-1] == ("Введите значение", True)

    def test_add_duplicate_value_shows_error(self, view, app, db):
        db.add_dict_value(models_dict_type(_TEST_BRAND), "iPhone 13")
        view.current_type = "models"
        view.scope_value = _TEST_BRAND
        rendered = view.render()
        edit_card = _edit_column(rendered)
        value_field = edit_card.controls[2]
        save_btn = edit_card.controls[5].controls[0]

        value_field.value = "iPhone 13"
        save_btn.on_click(None)

        assert app.snackbars[-1] == ("Такое значение уже существует", True)


class TestSelectEditDelete:
    def _first_row_and_item(self, view, db):
        dict_type = models_dict_type(_TEST_BRAND)
        db.add_dict_value(dict_type, "iPhone 13")
        [item] = db.get_all_dict_items(dict_type)
        view.current_type = "models"
        view.scope_value = _TEST_BRAND
        rendered = view.render()
        list_card = rendered.controls[2].controls[0].content
        row = _list_column(list_card).controls[0]
        return row, item

    def test_clicking_a_row_selects_it_for_editing(self, view, db):
        row, item = self._first_row_and_item(view, db)

        row.on_click(None)

        assert view.selected_item_id == item["id"]

    def test_saving_a_selected_item_updates_it_not_duplicates(self, view, app, db):
        row, _item = self._first_row_and_item(view, db)
        row.on_click(None)

        rendered = view.render()
        edit_card = _edit_column(rendered)
        value_field = edit_card.controls[2]
        save_btn = edit_card.controls[5].controls[0]
        value_field.value = "iPhone 13 Pro"

        save_btn.on_click(None)

        assert db.get_dict_values(models_dict_type(_TEST_BRAND)) == ["iPhone 13 Pro"]
        assert app.snackbars[-1] == ("Значение обновлено", False)

    def test_delete_without_selection_shows_error(self, view, app):
        view.current_type = "models"
        view.scope_value = _TEST_BRAND
        rendered = view.render()
        edit_card = _edit_column(rendered)
        delete_btn = edit_card.controls[5].controls[2]

        delete_btn.on_click(None)

        assert app.snackbars[-1] == ("Выберите элемент для удаления", True)
        assert not app.page.dialogs

    def test_delete_opens_confirm_dialog_without_deleting_yet(self, view, app, db):
        row, _item = self._first_row_and_item(view, db)
        row.on_click(None)
        rendered = view.render()
        edit_card = _edit_column(rendered)
        delete_btn = edit_card.controls[5].controls[2]

        delete_btn.on_click(None)

        assert app.page.dialogs
        assert db.get_dict_values(models_dict_type(_TEST_BRAND)) == ["iPhone 13"]

    def test_confirming_delete_removes_the_item(self, view, app, db):
        row, _item = self._first_row_and_item(view, db)
        row.on_click(None)
        rendered = view.render()
        edit_card = _edit_column(rendered)
        delete_btn = edit_card.controls[5].controls[2]
        delete_btn.on_click(None)
        dialog = app.page.dialogs[-1]
        confirm_btn = next(a for a in dialog.actions if a.content == "Удалить")

        confirm_btn.on_click(None)

        assert db.get_dict_values(models_dict_type(_TEST_BRAND)) == []
        assert view.selected_item_id is None


class TestCategorySwitch:
    def test_changing_dictionary_type_clears_selection(self, view, db):
        db.add_dict_value(models_dict_type(_TEST_BRAND), "iPhone 13")
        view.current_type = "models"
        view.scope_value = _TEST_BRAND
        view.selected_item_id = db.get_all_dict_items(models_dict_type(_TEST_BRAND))[0]["id"]

        rendered = view.render()
        type_selector = _header_controls(rendered)["Справочник"]
        type_selector.on_select(type("Event", (), {"control": type("Ctrl", (), {"value": "brands"})()})())

        assert view.current_type == "brands"
        assert view.selected_item_id is None
