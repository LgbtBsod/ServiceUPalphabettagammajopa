#!/usr/bin/env python3

"""Regression test for gui/main_window_parts/widgets_mixin.py::refresh_ui()
— Workflow-found bug: refresh_ui() (called from update_theme() whenever the
user changes theme/accent color in Settings) captured the active
status/priority/device_type/brand filters, rebuilt the whole UI, restored
the filter combos' displayed text via .set() (which does NOT fire
CTkComboBox's command=), and then called self.load_devices() — which only
honors hide_completed_var, silently ignoring status/priority/device_type/
brand. A user with e.g. status="В ремонте" filtered would see the dropdown
still showing "В ремонте" after a theme change, but the table would
silently repopulate with ALL orders. Fixed by calling self.apply_filters()
instead, the same method real filter-combo selections already use.

This test stubs out create_widgets()/apply_filters()/load_devices() rather
than building a real ServiceCenterApp main window (heavy, many
dependencies) — it only needs to prove WHICH of the two methods refresh_ui()
calls once real filters are active, not exercise the widgets themselves."""

from __future__ import annotations

import pytest

pytest.importorskip("gui")

from gui.main_window_parts.widgets_mixin import WidgetsMixin


class _FakeVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


class _FakeRoot:
    def winfo_children(self):
        return []


class _FakeApp(WidgetsMixin):
    """create_widgets/apply_filters/load_devices are overridden here —
    WidgetsMixin's own create_widgets() builds the real (heavy) main
    window, which this test has no need to exercise."""

    def __init__(self, *, with_filters: bool):
        self.root = _FakeRoot()
        self.apply_filters_calls = 0
        self.load_devices_calls = 0
        if with_filters:
            self.status_filter = _FakeVar("В ремонте")
            self.priority_filter = _FakeVar("Обычный")
            self.device_type_filter = _FakeVar("Ноутбук")
            self.brand_filter = _FakeVar("Apple")
            self.hide_completed_var = _FakeVar(True)

    def create_widgets(self):
        # Реалистично: create_widgets() пересоздаёт комбобоксы дефолтными
        # ("Все"), как и в реальном WidgetsMixin.create_widgets().
        if hasattr(self, "status_filter"):
            self.status_filter = _FakeVar("Все")
            self.priority_filter = _FakeVar("Все")
            self.device_type_filter = _FakeVar("Все")
            self.brand_filter = _FakeVar("Все")
            self.hide_completed_var = _FakeVar(True)

    def apply_filters(self):
        self.apply_filters_calls += 1

    def load_devices(self):
        self.load_devices_calls += 1


class TestRefreshUiReappliesActiveFilters:
    def test_refresh_ui_calls_apply_filters_not_load_devices_when_filters_exist(self):
        app = _FakeApp(with_filters=True)

        app.refresh_ui()

        assert app.apply_filters_calls == 1
        assert app.load_devices_calls == 0

    def test_refresh_ui_restores_the_filter_values_before_reapplying(self):
        app = _FakeApp(with_filters=True)

        app.refresh_ui()

        assert app.status_filter.get() == "В ремонте"
        assert app.priority_filter.get() == "Обычный"
        assert app.device_type_filter.get() == "Ноутбук"
        assert app.brand_filter.get() == "Apple"

    def test_refresh_ui_falls_back_to_load_devices_without_filter_widgets(self):
        """Defensive fallback for any state where the filter combos don't
        exist yet — must not raise AttributeError."""
        app = _FakeApp(with_filters=False)

        app.refresh_ui()

        assert app.load_devices_calls == 1
        assert app.apply_filters_calls == 0
