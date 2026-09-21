#!/usr/bin/env python3

"""Тесты чистой логики gui_flet/views_act_builder.py::ActBuilderView —
свободный (canvas) макет акта в Flet-оболочке.

Как и в tests/test_gui_flet.py — без поднятия реальной страницы/сессии
(Control-дерево Flet, как и Tk-виджеты, не тестируется через реальный
рендер headless). Драг/резайз-обработчики — чистые методы Python,
принимающие событие; читают из него только e.global_delta.x/.y (см.
docstring views_act_builder.py — global_delta это смещение С НАЧАЛА
жеста), так что синтетическое событие — просто SimpleNamespace с этим
одним полем, без нужды в настоящих Flet dataclass'ах события."""

from __future__ import annotations

import os
import types

import pytest

import gui  # noqa: F401 — обход циклического импорта managers/__init__.py
from gui_flet.theme import colors
from gui_flet.views_act_builder import (
    PAGE_W_MM,
    PX_PER_MM,
    ActBuilderView,
    _clamp,
    _palette_keys,
)
from reports import report_editor
from reports.report_renderer import ActPDFGenerator
from utils.messages import Msg


@pytest.fixture(autouse=True)
def _isolated_templates_dir(tmp_path, monkeypatch):
    """См. tests/test_report_editor_canvas_integration.py — load_template_data/
    save_template_data читают/пишут reports/templates/*.json; без изоляции
    тест затронул бы отслеживаемые файлы репозитория."""
    target = tmp_path / "templates"
    target.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(report_editor, "_templates_dir", lambda: str(target))


class _FakePage:
    def __init__(self):
        self.services = []
        self.dialogs = []

    def update(self):
        pass

    def run_task(self, coro_fn, *args, **kwargs):
        """Реальный Page.run_task планирует корутину в уже крутящемся
        asyncio-цикле Flet — здесь такого цикла нет, а синхронный тест,
        вызвавший код, ведущий сюда, ждёт результата синхронно.
        asyncio.run() даёт то же самое "к моменту возврата всё уже
        случилось" — тот же приём, что и в tests/test_gui_flet.py::
        _FakePage.run_task() (см. там же за обсуждением, когда так делать
        не стоит — настоящий конкурентный async вроде pick_files(),
        ожидающего реальный Flet-клиент, по-прежнему не тестируется тут)."""
        import asyncio

        asyncio.run(coro_fn(*args, **kwargs))

    def show_dialog(self, dialog):
        self.dialogs.append(dialog)

    def pop_dialog(self):
        if self.dialogs:
            self.dialogs.pop()


class _FakeApp:
    def __init__(self):
        self.colors = colors("light")
        self.page = _FakePage()
        self.snackbars = []
        self.rerender_calls = 0

    def show_snackbar(self, message, error=False):
        self.snackbars.append((message, error))

    def rerender(self):
        self.rerender_calls += 1


@pytest.fixture
def app():
    return _FakeApp()


@pytest.fixture
def view(app):
    return ActBuilderView(app)


def _drag_event(dx: float, dy: float):
    return types.SimpleNamespace(global_delta=types.SimpleNamespace(x=dx, y=dy))


class TestFieldsDefaultToNonEmptyLayout:
    def test_fresh_template_gets_default_canvas_layout(self, view):
        fields = view._fields()
        assert fields
        assert "header" in fields or "title" in fields

    def test_receipt_and_completion_have_independent_layouts(self, view):
        receipt_fields = view._fields()
        view.act_type = "completion"
        completion_fields = view._fields()
        assert "defect_box" not in completion_fields
        assert "works_table" in completion_fields
        # Изменение одного не должно задевать другой (общий словарь по
        # ссылке — реальный класс бага для двух типов акта в одной вью).
        receipt_fields["phone"] = {"x_mm": 1.0, "y_mm": 1.0, "w_mm": 10.0}
        assert "phone" not in view._fields()


class TestPaletteKeys:
    def test_composite_fields_filtered_by_act_type(self):
        assert "defect_box" in _palette_keys("receipt")
        assert "works_table" not in _palette_keys("receipt")
        assert "works_table" in _palette_keys("completion")
        assert "defect_box" not in _palette_keys("completion")


class TestAddRemoveSelect:
    def test_add_field_places_it_and_selects_it(self, view):
        before = set(view._fields().keys())
        view._add_field("phone")
        assert "phone" not in before
        assert "phone" in view._fields()
        assert view.selected_key == "phone"
        assert view.app.rerender_calls >= 1

    def test_remove_selected_clears_field_and_selection(self, view):
        view._add_field("phone")
        view._remove_selected()
        assert "phone" not in view._fields()
        assert view.selected_key is None

    def test_select_without_rerender_does_not_call_app_rerender(self, view):
        calls_before = view.app.rerender_calls
        view._select("header", rerender=False)
        assert view.selected_key == "header"
        assert view.app.rerender_calls == calls_before


class TestMoveDrag:
    def test_move_updates_position_from_start_plus_cumulative_delta(self, view):
        view._fields()["client_name"] = {"x_mm": 10.0, "y_mm": 10.0, "w_mm": 60.0}
        view._build_canvas()  # заполняет _body_ctrls/_handle_ctrls

        view._on_move_start(None, "client_name")
        view._on_move_update(_drag_event(dx=20 * PX_PER_MM, dy=5 * PX_PER_MM), "client_name")
        view._on_move_end(None, "client_name")

        cfg = view._fields()["client_name"]
        assert cfg["x_mm"] == pytest.approx(30.0, abs=0.5)
        assert cfg["y_mm"] == pytest.approx(15.0, abs=0.5)

    def test_move_is_clamped_to_page_bounds(self, view):
        view._fields()["client_name"] = {"x_mm": 10.0, "y_mm": 10.0, "w_mm": 60.0}
        view._build_canvas()

        view._on_move_start(None, "client_name")
        view._on_move_update(_drag_event(dx=-10_000, dy=-10_000), "client_name")
        view._on_move_end(None, "client_name")

        cfg = view._fields()["client_name"]
        assert cfg["x_mm"] == 0.0
        assert cfg["y_mm"] == 0.0

    def test_move_never_pushes_box_past_right_edge(self, view):
        view._fields()["client_name"] = {"x_mm": 10.0, "y_mm": 10.0, "w_mm": 60.0}
        view._build_canvas()

        view._on_move_start(None, "client_name")
        view._on_move_update(_drag_event(dx=10_000, dy=0), "client_name")
        view._on_move_end(None, "client_name")

        cfg = view._fields()["client_name"]
        max_x_mm = PAGE_W_MM - cfg["w_mm"]
        assert cfg["x_mm"] == pytest.approx(max_x_mm, abs=0.5)

    def test_move_update_for_a_different_key_than_the_active_drag_is_ignored(self, view):
        """Защита от гонки: если пришёл update для НЕ того ключа, который
        сейчас реально тащат (устаревший колбэк), позиция не должна
        измениться — раньше это защищалось только совпадением по факту
        единственного активного драга, но явная проверка нужна на случай
        гонки двух почти одновременных жестов."""
        view._fields()["a"] = {"x_mm": 10.0, "y_mm": 10.0, "w_mm": 60.0}
        view._fields()["b"] = {"x_mm": 20.0, "y_mm": 20.0, "w_mm": 60.0}
        view._build_canvas()

        view._on_move_start(None, "a")
        view._on_move_update(_drag_event(dx=50, dy=50), "b")  # чужой ключ

        assert view._body_ctrls["b"].left == 20.0 * PX_PER_MM

    def test_move_snaps_imprecise_position_to_grid(self, view):
        """GRID_MM=5 — курсор при драге никогда не бывает пиксель-точным;
        итоговая позиция должна округляться к ближайшей линии сетки."""
        view._fields()["client_name"] = {"x_mm": 10.0, "y_mm": 10.0, "w_mm": 60.0}
        view._build_canvas()

        view._on_move_start(None, "client_name")
        # +23мм — заведомо не кратно GRID_MM (5) — ожидаем округление до 35.
        view._on_move_update(_drag_event(dx=23 * PX_PER_MM, dy=0), "client_name")
        view._on_move_end(None, "client_name")

        from gui_flet.views_act_builder import GRID_MM

        cfg = view._fields()["client_name"]
        assert cfg["x_mm"] % GRID_MM == 0
        assert cfg["x_mm"] == pytest.approx(35.0, abs=0.01)

    def test_dragging_a_different_field_refreshes_screen_by_drag_end(self, view):
        """Regression: _on_move_start выбирает новое поле через
        _select(key, rerender=False) (намеренно — полный rerender()
        посреди активного жеста мог бы сбить распознаватель drag у
        GestureDetector), но раньше НИЧТО не вызывало app.rerender() до
        конца драга вообще. Значит после перетаскивания поля 'b' (пока
        было выбрано поле 'a') экран продолжал показывать 'a' выделенным
        (граница + панель свойств), хотя view.selected_key уже стало 'b' —
        клик "Убрать с макета" в этот момент удалил бы 'b', а не то поле,
        что видно выделенным на экране."""
        view._fields()["a"] = {"x_mm": 10.0, "y_mm": 10.0, "w_mm": 60.0}
        view._fields()["b"] = {"x_mm": 20.0, "y_mm": 20.0, "w_mm": 60.0}
        view._build_canvas()

        view._select("a")
        calls_before_drag = view.app.rerender_calls

        view._on_move_start(None, "b")
        assert view.selected_key == "b"
        # На старте драга rerender НЕ должен вызываться — это ожидаемо
        # (см. докстринг выше), а не часть бага.
        assert view.app.rerender_calls == calls_before_drag

        view._on_move_update(_drag_event(dx=5, dy=5), "b")
        view._on_move_end(None, "b")

        assert view.app.rerender_calls > calls_before_drag, (
            "screen must refresh (border + props panel) by the time the "
            "drag ends, so it matches the new selected_key before any "
            "delete action can act on the stale selection"
        )


class TestResizeDrag:
    def test_resize_changes_width_not_position(self, view):
        view._fields()["client_name"] = {"x_mm": 10.0, "y_mm": 10.0, "w_mm": 60.0}
        view._build_canvas()

        view._on_resize_start(None, "client_name")
        view._on_resize_update(_drag_event(dx=20 * PX_PER_MM, dy=0), "client_name")
        view._on_resize_end(None, "client_name")

        cfg = view._fields()["client_name"]
        assert cfg["w_mm"] == pytest.approx(80.0, abs=0.5)
        assert cfg["x_mm"] == 10.0

    def test_resize_snaps_width_to_grid(self, view):
        view._fields()["client_name"] = {"x_mm": 10.0, "y_mm": 10.0, "w_mm": 60.0}
        view._build_canvas()

        view._on_resize_start(None, "client_name")
        # +17мм — не кратно 5 — ожидаем округление до 60+15=75.
        view._on_resize_update(_drag_event(dx=17 * PX_PER_MM, dy=0), "client_name")
        view._on_resize_end(None, "client_name")

        from gui_flet.views_act_builder import GRID_MM

        cfg = view._fields()["client_name"]
        assert cfg["w_mm"] % GRID_MM == 0
        assert cfg["w_mm"] == pytest.approx(75.0, abs=0.01)

    def test_resize_never_below_minimum_width(self, view):
        view._fields()["client_name"] = {"x_mm": 10.0, "y_mm": 10.0, "w_mm": 60.0}
        view._build_canvas()

        view._on_resize_start(None, "client_name")
        view._on_resize_update(_drag_event(dx=-10_000, dy=0), "client_name")
        view._on_resize_end(None, "client_name")

        from gui_flet.views_act_builder import MIN_WIDTH_MM

        assert view._fields()["client_name"]["w_mm"] == MIN_WIDTH_MM

    def test_resize_never_extends_past_page_edge(self, view):
        view._fields()["client_name"] = {"x_mm": 100.0, "y_mm": 10.0, "w_mm": 30.0}
        view._build_canvas()

        view._on_resize_start(None, "client_name")
        view._on_resize_update(_drag_event(dx=10_000, dy=0), "client_name")
        view._on_resize_end(None, "client_name")

        cfg = view._fields()["client_name"]
        assert cfg["x_mm"] + cfg["w_mm"] <= PAGE_W_MM + 0.01

    def test_resize_without_end_call_leaves_field_dict_untouched(self, view):
        """on_pan_end не пришёл (например, событие потерялось) — визуальное
        состояние контрола уже поехало, но self.fields не должен меняться
        до явного _on_resize_end (иначе get_canvas_fields()/Сохранить видят
        рассинхронизированное значение)."""
        view._fields()["client_name"] = {"x_mm": 10.0, "y_mm": 10.0, "w_mm": 60.0}
        view._build_canvas()

        view._on_resize_start(None, "client_name")
        view._on_resize_update(_drag_event(dx=20 * PX_PER_MM, dy=0), "client_name")

        assert view._fields()["client_name"]["w_mm"] == 60.0


class TestImportFileErrorHandling:
    """Regression: pick_files() сидел ВНЕ try/except, охватывающего
    остальной _on_import_click() (тот начинается только с проверки
    picked.bytes) — а page.run_task() отдаёт исключения таска только
    дефолтному (консольному) обработчику asyncio, никакого snackbar
    пользователь не видел. Кнопка "📥 Импорт из файла" при сбое пикера
    (разрыв сессии, таймаут, нет zenity на Linux-десктопе) выглядела как
    ничего не делающая."""

    def test_pick_files_failure_shows_error_snackbar_not_a_silent_crash(self, view):
        async def _raise(*_args, **_kwargs):
            raise RuntimeError("picker disconnected")

        view._file_picker.pick_files = _raise

        view._on_import_click()  # не должно бросить исключение наружу

        assert view.app.snackbars, (
            "a failed file-picker call must surface visible feedback, "
            "not disappear silently"
        )
        _message, is_error = view.app.snackbars[-1]
        assert is_error is True


class TestActTypeSwitch:
    def test_switching_resets_selection_and_rerenders(self, view):
        view._add_field("client_name")
        assert view.selected_key == "client_name"

        e = types.SimpleNamespace(control=types.SimpleNamespace(selected=["completion"]))
        view._on_act_type_change(e)

        assert view.act_type == "completion"
        assert view.selected_key is None


class TestSave:
    def test_save_persists_layout_mode_and_fields_to_disk(self, view, app):
        view._add_field("client_name")
        view._fields()["client_name"]["x_mm"] = 42.0

        view._on_save_click()

        assert app.snackbars and app.snackbars[-1][1] is False  # error=False
        saved = report_editor.load_template_data("receipt")
        assert saved["layout_mode"] == "canvas"
        assert saved["canvas_fields"]["client_name"]["x_mm"] == 42.0


class TestExactPdfPreview:
    """Regression (workflow architecture audit): _on_exact_pdf_click() used
    to generate the PDF and launch the system viewer synchronously right
    in the click handler, freezing the whole Flet page for the duration —
    now wrapped in page.run_task()/asyncio.to_thread(), the same pattern
    as _print_act() (views_orders.py) and _on_import_click() above."""

    @pytest.fixture(autouse=True)
    def _no_real_viewer_launch(self, monkeypatch):
        monkeypatch.setattr(os, "startfile", lambda path: None, raising=False)

    def test_success_opens_the_generated_pdf(self, view, app):
        view._on_exact_pdf_click()

        assert app.snackbars
        message, is_error = app.snackbars[-1]
        assert is_error is False
        assert message == Msg.Act.PREVIEW_OPENED

    def test_generation_failure_shows_error_without_raising(self, view, app, monkeypatch):
        monkeypatch.setattr(
            ActPDFGenerator, "generate_receipt_pdf", lambda self, path, device: False
        )

        view._on_exact_pdf_click()

        assert app.snackbars
        message, is_error = app.snackbars[-1]
        assert is_error is True
        assert message == Msg.Act.PREVIEW_GENERATE_FAILED

    def test_exception_during_generation_shows_error_without_raising(
        self, view, app, monkeypatch
    ):
        def _boom(self, path, device):
            raise RuntimeError("boom")

        monkeypatch.setattr(ActPDFGenerator, "generate_receipt_pdf", _boom)

        view._on_exact_pdf_click()

        assert app.snackbars
        message, is_error = app.snackbars[-1]
        assert is_error is True
        assert "boom" in message


class TestClampHelper:
    def test_clamp_within_range_unchanged(self):
        assert _clamp(50, 0, 100) == 50

    def test_clamp_below_range(self):
        assert _clamp(-10, 0, 100) == 0

    def test_clamp_above_range(self):
        assert _clamp(150, 0, 100) == 100
