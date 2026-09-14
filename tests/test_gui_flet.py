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

import flet as ft
import pytest

import gui  # noqa: F401 — обход циклического импорта managers/__init__.py
from database.db_config import DatabaseConfig
from database.engines.sqlite_engine import SQLiteEngine
from database.sqlalchemy_database import Database
from domain.constants import PRIORITIES, STATUS_ISSUED, STATUSES, WARRANTIES
from gui_flet.theme import card_border, colors
from gui_flet.views_orders import (
    OrdersView,
    _dropdown_options_with_fallback,
    _opt,
    _print_act,
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


class TestDeleteOrder:
    """Regression (Flet/classic parity gap): the classic GUI's only delete
    path — gui/main_window_parts/devices_table_mixin.py::_quick_delete_selected(),
    bound to the Delete key with an askyesno confirm — had NO equivalent
    anywhere in gui_flet (a grep for 'delete'/'Удал' across gui_flet/
    returned zero matches). A mistaken/duplicate/test order created via
    the Flet GUI could only be removed by switching to the classic
    interface."""

    def _card_delete_button(self, view, db):
        rows = view._fetch_rows()
        card = view._order_card(rows[0])
        return _find(card, tooltip="Удалить заказ")

    def test_delete_button_opens_confirm_dialog_without_deleting_yet(self, db):
        device_id = db.add_device(
            {"order_number": "1", "client_name": "Иван", "phone": "+79990000000"}
        )
        app = _FakeApp(db)
        view = OrdersView(app)

        delete_btn = self._card_delete_button(view, db)
        assert delete_btn is not None
        delete_btn.on_click(None)

        assert db.get_device(device_id) is not None, (
            "clicking the delete icon must not delete immediately — a "
            "confirmation dialog must appear first"
        )
        assert app.page.dialogs, "clicking delete must open a confirm dialog"

    def test_confirming_the_dialog_deletes_the_order(self, db):
        device_id = db.add_device(
            {"order_number": "1", "client_name": "Иван", "phone": "+79990000000"}
        )
        app = _FakeApp(db)
        view = OrdersView(app)

        self._card_delete_button(view, db).on_click(None)
        dialog = app.page.dialogs[-1]
        confirm_btn = next(a for a in dialog.actions if a.content == "Удалить")

        confirm_btn.on_click(None)

        assert db.get_device(device_id) is None

    def test_cancelling_the_dialog_keeps_the_order(self, db):
        device_id = db.add_device(
            {"order_number": "1", "client_name": "Иван", "phone": "+79990000000"}
        )
        app = _FakeApp(db)
        view = OrdersView(app)

        self._card_delete_button(view, db).on_click(None)
        dialog = app.page.dialogs[-1]
        cancel_btn = next(a for a in dialog.actions if a.content == "Отмена")

        cancel_btn.on_click(None)

        assert db.get_device(device_id) is not None


class TestOrderCardLayoutIsRobustToNarrowWidths:
    """Regression: a live run at a perfectly ordinary desktop window width
    (900px) showed the order card's title/subtitle Text exploding into one
    character per line, ballooning the card to fill the whole screen. The
    info Column used expand=True with no overflow protection on its Text
    controls — the row's other, fixed-width chrome (status color bar,
    priority badge, price, a 190px status Dropdown, four IconButtons) adds
    up to more than 900px on its own, so Flutter squeezed the expand=True
    column to (near-)zero width, and Text with no max_lines/overflow set
    wraps at effectively 0 characters per line in that situation. Fixed by
    giving the info Column a fixed width (so it can never be squeezed to
    zero) with max_lines=1 + overflow=ELLIPSIS on both Text controls (so a
    still-too-long value truncates instead of wrapping), and adding
    scroll=ft.ScrollMode.AUTO to the outer Row so the whole card scrolls
    horizontally on narrow viewports instead of any element collapsing."""

    def test_title_and_subtitle_are_single_line_with_ellipsis_overflow(self, db):
        db.add_device({
            "order_number": "1", "client_name": "Иван", "phone": "+79990000000",
        })
        app = _FakeApp(db)
        view = OrdersView(app)
        rows = view._fetch_rows()

        card = view._order_card(rows[0])
        row = card.content
        info_column = row.controls[1]
        title_text, subtitle_text = info_column.controls

        assert title_text.max_lines == 1
        assert title_text.overflow == ft.TextOverflow.ELLIPSIS
        assert subtitle_text.max_lines == 1
        assert subtitle_text.overflow == ft.TextOverflow.ELLIPSIS

    def test_info_column_has_a_fixed_width_not_unbounded_expand(self, db):
        db.add_device({
            "order_number": "1", "client_name": "Иван", "phone": "+79990000000",
        })
        app = _FakeApp(db)
        view = OrdersView(app)
        rows = view._fetch_rows()

        card = view._order_card(rows[0])
        info_column = card.content.controls[1]

        assert info_column.width is not None and info_column.width > 0, (
            "the info Column must have a fixed width — expand=True with no "
            "floor lets it be squeezed to zero on narrow viewports"
        )

    def test_card_row_scrolls_horizontally_instead_of_collapsing(self, db):
        db.add_device({
            "order_number": "1", "client_name": "Иван", "phone": "+79990000000",
        })
        app = _FakeApp(db)
        view = OrdersView(app)
        rows = view._fetch_rows()

        card = view._order_card(rows[0])

        assert card.content.scroll == ft.ScrollMode.AUTO, (
            "the card's Row must scroll horizontally so its fixed-width "
            "controls stay visible (via scroll) instead of being squeezed "
            "off narrow viewports"
        )


class TestPrintCompletionActPromptsMarkIssued:
    """Regression (Flet/classic parity gap): classic's
    gui/main_window_parts/acts_mixin.py::print_completion_act() asks to
    flip status to STATUS_ISSUED ("Выдан клиенту") right after printing —
    printing that act = handing the device back to the client. gui_flet's
    _print_act() for act_type='completion' only built the PDF and
    os.startfile()d it, never touching status at all — orders printed and
    handed over via Flet could silently stay in an earlier status,
    skewing dashboard/finance figures that key off status."""

    @pytest.fixture(autouse=True)
    def _no_real_viewer_launch(self, monkeypatch):
        # _print_act() imports os/subprocess locally, but that's still the
        # same os/subprocess module object — patching here reaches it.
        monkeypatch.setattr(os, "startfile", lambda path: None, raising=False)

    def _generated_paths(self, monkeypatch):
        paths = []
        real_mkstemp = tempfile.mkstemp

        def _tracked_mkstemp(*args, **kwargs):
            fd, path = real_mkstemp(*args, **kwargs)
            paths.append(path)
            return fd, path

        monkeypatch.setattr(tempfile, "mkstemp", _tracked_mkstemp)
        return paths

    def test_completion_print_prompts_to_mark_issued(self, db, monkeypatch):
        paths = self._generated_paths(monkeypatch)
        device_id = db.add_device({
            "order_number": "1", "client_name": "Иван", "phone": "+79990000000",
            "status": STATUSES[0],
        })
        app = _FakeApp(db)

        _print_act(app, db.get_device(device_id), "completion")

        assert app.page.dialogs, (
            "printing the completion act must prompt to mark the order issued"
        )
        for p in paths:
            if os.path.exists(p):
                os.remove(p)

    def test_confirming_the_prompt_updates_status(self, db, monkeypatch):
        paths = self._generated_paths(monkeypatch)
        device_id = db.add_device({
            "order_number": "1", "client_name": "Иван", "phone": "+79990000000",
            "status": STATUSES[0],
        })
        app = _FakeApp(db)

        _print_act(app, db.get_device(device_id), "completion")
        dialog = app.page.dialogs[-1]
        confirm_btn = next(a for a in dialog.actions if a.content == "Да")
        confirm_btn.on_click(None)

        assert db.get_device(device_id)["status"] == STATUS_ISSUED
        for p in paths:
            if os.path.exists(p):
                os.remove(p)

    def test_cancelling_the_prompt_keeps_the_prior_status(self, db, monkeypatch):
        paths = self._generated_paths(monkeypatch)
        device_id = db.add_device({
            "order_number": "1", "client_name": "Иван", "phone": "+79990000000",
            "status": STATUSES[0],
        })
        app = _FakeApp(db)

        _print_act(app, db.get_device(device_id), "completion")
        dialog = app.page.dialogs[-1]
        cancel_btn = next(a for a in dialog.actions if a.content == "Отмена")
        cancel_btn.on_click(None)

        assert db.get_device(device_id)["status"] == STATUSES[0]
        for p in paths:
            if os.path.exists(p):
                os.remove(p)

    def test_receipt_print_never_prompts(self, db, monkeypatch):
        paths = self._generated_paths(monkeypatch)
        device_id = db.add_device({
            "order_number": "1", "client_name": "Иван", "phone": "+79990000000",
        })
        app = _FakeApp(db)

        _print_act(app, db.get_device(device_id), "receipt")

        assert not app.page.dialogs
        for p in paths:
            if os.path.exists(p):
                os.remove(p)

    def test_already_issued_device_is_not_prompted_again(self, db, monkeypatch):
        paths = self._generated_paths(monkeypatch)
        device_id = db.add_device({
            "order_number": "1", "client_name": "Иван", "phone": "+79990000000",
            "status": STATUS_ISSUED,
        })
        app = _FakeApp(db)

        _print_act(app, db.get_device(device_id), "completion")

        assert not app.page.dialogs
        for p in paths:
            if os.path.exists(p):
                os.remove(p)


class TestPrintActDoesNotLeakTempFiles:
    """Regression: _print_act() mkstemp()'d a new temp PDF on every click
    and never removed it — repeated printing from Flet accumulated one
    orphaned temp file per click for the life of the process, unlike
    gui/dialogs/act_preview.py which always cleans up the previous temp
    file before creating the next. Fixed with the same asymmetric
    cleanup (delete-previous-before-creating-next) via
    app._last_act_print_path."""

    @pytest.fixture(autouse=True)
    def _no_real_viewer_launch(self, monkeypatch):
        monkeypatch.setattr(os, "startfile", lambda path: None, raising=False)

    def test_second_print_removes_the_first_temp_pdf(self, db):
        device_id = db.add_device({
            "order_number": "1", "client_name": "Иван", "phone": "+79990000000",
        })
        app = _FakeApp(db)

        _print_act(app, db.get_device(device_id), "receipt")
        first_path = app._last_act_print_path
        assert first_path is not None
        assert os.path.exists(first_path)

        _print_act(app, db.get_device(device_id), "receipt")
        second_path = app._last_act_print_path
        assert second_path is not None
        assert second_path != first_path
        assert not os.path.exists(first_path), (
            "the temp PDF from the first print must be removed once the "
            "second print starts, instead of accumulating forever"
        )

        if os.path.exists(second_path):
            os.remove(second_path)
