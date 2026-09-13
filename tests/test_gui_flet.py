"""Тесты чистой логики Flet-оболочки (gui_flet/) — без поднятия страницы.

customtkinter-интерфейс (gui/) тоже не покрыт юнит-тестами (виджеты Tk
нельзя осмысленно тестировать headless) — здесь то же самое ограничение для
Control-дерева Flet. Но часть логики вокруг вью — чистые функции, не
требующие Page/сессии, и именно на этой границе уже случались реальные
регрессии (Dropdown.Option без text — молча пустая подпись в браузере,
найдено только живым прогоном), поэтому стоит закрепить их тестами."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

import gui  # noqa: F401 — обход циклического импорта managers/__init__.py
from database.db_config import DatabaseConfig
from database.engines.sqlite_engine import SQLiteEngine
from database.sqlalchemy_database import Database
from domain.constants import PRIORITIES, STATUSES, WARRANTIES
from gui_flet.theme import card_border, colors
from gui_flet.views_orders import (
    OrdersView,
    _dropdown_options_with_fallback,
    _opt,
    _status_options,
)


class TestDropdownOption:
    def test_opt_sets_both_key_and_text(self):
        opt = _opt("В работе")
        assert opt.key == "В работе"
        assert opt.text == "В работе"

    def test_opt_custom_label(self):
        opt = _opt("Готов", label="Готов (устаревший статус)")
        assert opt.key == "Готов"
        assert opt.text == "Готов (устаревший статус)"

    def test_opt_empty_value_falls_back_to_dash(self):
        opt = _opt("")
        assert opt.text == "—"


class TestStatusOptions:
    def test_known_status_not_duplicated(self):
        opts = _status_options(STATUSES[0])
        keys = [o.key for o in opts]
        assert keys.count(STATUSES[0]) == 1
        assert keys == list(STATUSES)

    def test_legacy_status_prepended(self):
        opts = _status_options("Готов")
        assert opts[0].key == "Готов"
        assert "устаревш" in opts[0].text
        # Остальные штатные статусы всё ещё присутствуют — легаси-значение
        # не замещает список, а дополняет его.
        assert [o.key for o in opts[1:]] == list(STATUSES)

    def test_empty_status_no_extra_option(self):
        opts = _status_options("")
        assert [o.key for o in opts] == list(STATUSES)


class TestTheme:
    def test_colors_light_and_dark_have_same_keys(self):
        light = colors("light")
        dark = colors("dark")
        assert set(light.keys()) == set(dark.keys())
        assert "bg_card" in light and "text_primary" in light

    def test_card_border_uses_same_color_all_sides(self):
        border = card_border("#d2d2d7")
        assert border.top.color == "#d2d2d7"
        assert border.left.color == border.right.color == border.bottom.color == border.top.color


class TestDropdownOptionsWithFallback:
    """warranty/priority — в классическом интерфейсе редактируемый
    CTkComboBox, а не закрытый список, так что произвольное легаси-значение
    там абсолютно легально; Flet-Dropdown должен уметь его хотя бы показать,
    а не молча сбросить на сохранении (тот же класс бага, что и у статуса)."""

    def test_known_value_not_duplicated(self):
        opts = _dropdown_options_with_fallback(PRIORITIES[0], PRIORITIES, "нет в списке")
        assert [o.key for o in opts] == list(PRIORITIES)

    def test_legacy_value_prepended(self):
        opts = _dropdown_options_with_fallback("Срочно вчера", PRIORITIES, "нет в списке")
        assert opts[0].key == "Срочно вчера"
        assert "нет в списке" in opts[0].text
        assert [o.key for o in opts[1:]] == list(PRIORITIES)

    def test_empty_value_no_extra_option(self):
        opts = _dropdown_options_with_fallback("", WARRANTIES, "нет в списке")
        assert [o.key for o in opts] == list(WARRANTIES)


def _walk(control):
    if isinstance(control, str):
        return
    yield control
    for child in getattr(control, "controls", None) or []:
        yield from _walk(child)
    content = getattr(control, "content", None)
    if content is not None:
        yield from _walk(content)


def _find(control, **attrs):
    for node in _walk(control):
        if all(getattr(node, key, None) == value for key, value in attrs.items()):
            return node
    return None


def _find_button(control, label: str):
    """FilledButton/OutlinedButton store their visible label directly as a
    plain string in `.content` in this Flet version (no `.text` attribute
    at all) — a bare `_find(..., text=...)` never matches."""
    for node in _walk(control):
        if getattr(node, "content", None) == label and hasattr(node, "on_click"):
            return node
    return None


class _FakePage:
    def update(self):
        pass


class _FakeApp:
    def __init__(self, db):
        self.db = db
        self.colors = colors("light")
        self.page = _FakePage()
        self.snackbars = []

    def show_snackbar(self, message, error=False):
        self.snackbars.append((message, error))

    def rerender(self):
        pass


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


class TestOrderFormSave:
    """Регрессия: OrdersView._render_form()'s on_save() раньше строил
    device_data БЕЗ ключей work_items_json/photos/completeness/appearance/
    expense — Database.update_device()/_sync_photos()/_sync_work_items()
    трактуют отсутствующий ключ как "очистить всё", так что сохранение формы
    редактирования через Flet тихо стирало все фото и позиции работ заказа.
    Отдельно: order_number для НОВОГО заказа брался из
    peek_next_order_number() (не инкрементирует счётчик) вместо
    get_next_order_number() в момент сохранения — два заказа подряд,
    созданных через Flet, получали один и тот же номер и падали на
    unique-ограничении devices.order_number."""

    def test_editing_preserves_unedited_photo_and_work_item_data(self, db):
        device_id = db.add_device(
            {
                "order_number": "1",
                "client_name": "Иван",
                "phone": "+79990000000",
                "work_items_json": json.dumps(
                    [{"description": "Чистка", "price": 100, "quantity": 1}]
                ),
                "photos": "a.jpg,b.jpg",
                "completeness": "Полная",
                "appearance": "Хорошее",
            }
        )
        app = _FakeApp(db)
        view = OrdersView(app)
        view.mode = "form"
        view.editing_id = device_id
        form = view._render_form()

        save_btn = _find_button(form, "Сохранить")
        assert save_btn is not None
        save_btn.on_click(None)

        after = db.get_device(device_id)
        assert after["work_items"]
        assert json.loads(after["work_items"])[0]["description"] == "Чистка"
        assert after["photos"] == "a.jpg,b.jpg"
        assert after["completeness"] == "Полная"
        assert after["appearance"] == "Хорошее"

    def test_two_new_orders_get_different_order_numbers(self, db):
        app = _FakeApp(db)

        for i in (1, 2):
            view = OrdersView(app)
            view.mode = "form"
            form = view._render_form()
            _find(form, label="Имя клиента").value = f"Клиент {i}"
            _find(form, label="Телефон").value = f"+7999000000{i}"
            _find_button(form, "Сохранить").on_click(None)

        numbers = {row["order_number"] for row in db.get_all_devices()}
        assert len(numbers) == 2, (
            f"ожидались 2 разных номера заказа, получено: {numbers}"
        )
