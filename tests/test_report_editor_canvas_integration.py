#!/usr/bin/env python3

"""Интеграционные тесты для reports/report_editor.py::ActPanel — проводка
свободного макета (canvas layout_mode) между режимом-переключателем,
ActCanvasEditor и импортом файла (apply_imported_suggestion).

Использует реальный (скрытый) Tk root — см. tests/conftest.py::tk_root —
вместо стабов: ActPanel — это реальный customtkinter-виджет, и только его
конструирование уже проверяет реальный Tk-API. Шаблоны читаются/пишутся из
reports/templates/*.json (см. report_editor.load_template_data) — эти файлы
уже существуют в репозитории, тесты используют monkeypatch на
_templates_dir(), чтобы гарантированно НЕ трогать отслеживаемые файлы."""

from __future__ import annotations

import customtkinter as ctk
import pytest

pytest.importorskip("gui")  # обход циклического импорта, как в test_act_importer.py

from reports import report_editor


@pytest.fixture(autouse=True)
def _isolated_templates_dir(tmp_path, monkeypatch):
    """Перенаправляет _templates_dir() во временную папку — конструирование
    ActPanel читает/при первом запуске пишет receipt_act.json/
    completion_act.json, и без этой изоляции затронуло бы отслеживаемые
    файлы в reports/templates/. Каталог создаём сами — оригинальная
    _templates_dir() тоже делает os.makedirs(..., exist_ok=True) как часть
    своего контракта."""
    target = tmp_path / "templates"
    target.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(report_editor, "_templates_dir", lambda: str(target))


@pytest.fixture
def act_panel(tk_root):
    ctk.set_appearance_mode("light")
    from utils.colors import get_colors

    tk_root.colors = get_colors("light")
    master_tab = ctk.CTkFrame(tk_root)
    master_tab.pack()
    panel = report_editor.ActPanel(master_tab, tk_root, "receipt")
    yield panel


def _click_layout_toggle(panel, value: str) -> None:
    """Симулирует реальный клик по self.layout_mode_toggle: сначала виджет
    сам обновляет своё состояние (как CTkSegmentedButton делает при клике
    ДО вызова command=), потом срабатывает обработчик. Вызов одного
    _on_layout_mode_changed() без .set() расходится с реальным кликом —
    sync_template_from_ui() читает актуальное состояние через
    layout_mode_toggle.get(), а не то, что передали в обработчик."""
    panel.layout_mode_toggle.set(value)
    panel._on_layout_mode_changed(value)


class TestLayoutModeToggle:
    def test_starts_in_flow_mode_with_no_canvas_editor(self, act_panel):
        assert act_panel.template_data.get("layout_mode") != "canvas"
        assert act_panel.canvas_editor is None

    def test_switching_to_canvas_mode_builds_editor_with_default_layout(self, act_panel):
        _click_layout_toggle(act_panel, "🖼 Свободный макет")
        assert act_panel.template_data["layout_mode"] == "canvas"
        assert act_panel.canvas_editor is not None
        # default_canvas_layout() всегда заполняет хотя бы шапку/заголовок —
        # переключение в canvas не должно давать пустой макет.
        assert act_panel.template_data["canvas_fields"]

    def test_switching_back_to_flow_mode_tears_down_editor(self, act_panel):
        _click_layout_toggle(act_panel, "🖼 Свободный макет")
        _click_layout_toggle(act_panel, "📋 Список полей")
        assert act_panel.template_data["layout_mode"] == "flow"
        assert act_panel.canvas_editor is None

    def test_dragging_a_field_persists_into_template_data_via_on_change(self, act_panel):
        _click_layout_toggle(act_panel, "🖼 Свободный макет")
        editor = act_panel.canvas_editor
        editor._add_field("client_name")
        # _add_field уже вызывает on_change (_on_canvas_changed), но
        # проверяем именно то, что ActPanel реально видит актуальный layout —
        # не устаревший снимок с момента переключения режима.
        assert "client_name" in act_panel.template_data["canvas_fields"]


class TestApplyImportedSuggestionWithCanvasLayout:
    def test_no_canvas_layout_keeps_flow_mode(self, act_panel):
        suggestion = {
            "suggested_fields": ["client_name", "phone"],
            "header_text_guess": "АКТ",
            "match_count": 2,
            "known_count": 10,
        }
        act_panel.apply_imported_suggestion(suggestion, canvas_layout=None)
        assert act_panel.template_data.get("layout_mode") != "canvas"
        assert act_panel.canvas_editor is None

    def test_canvas_layout_switches_mode_and_places_fields(self, act_panel):
        suggestion = {
            "suggested_fields": ["client_name", "phone"],
            "header_text_guess": "ИМПОРТИРОВАННЫЙ АКТ",
            "match_count": 2,
            "known_count": 10,
        }
        canvas_layout = {
            "client_name": {"x_mm": 10.0, "y_mm": 20.0, "w_mm": 80.0},
            "phone": {"x_mm": 10.0, "y_mm": 30.0, "w_mm": 80.0},
        }
        act_panel.apply_imported_suggestion(suggestion, canvas_layout=canvas_layout)

        assert act_panel.template_data["layout_mode"] == "canvas"
        assert act_panel.template_data["canvas_fields"] == canvas_layout
        assert act_panel.canvas_editor is not None
        assert act_panel.canvas_editor.get_canvas_fields() == canvas_layout
        assert act_panel.layout_mode_toggle.get() == "🖼 Свободный макет"
        assert act_panel.header_entry.get() == "ИМПОРТИРОВАННЫЙ АКТ"


class TestSyncTemplateFromUiIncludesCanvasState:
    def test_sync_persists_layout_mode_and_live_canvas_positions(self, act_panel):
        _click_layout_toggle(act_panel, "🖼 Свободный макет")
        act_panel.canvas_editor._add_field("phone")
        act_panel.canvas_editor.fields["phone"]["x_mm"] = 42.0

        act_panel.sync_template_from_ui()

        assert act_panel.template_data["layout_mode"] == "canvas"
        assert act_panel.template_data["canvas_fields"]["phone"]["x_mm"] == 42.0
