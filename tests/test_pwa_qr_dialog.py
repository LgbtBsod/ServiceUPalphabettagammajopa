#!/usr/bin/env python3

"""Тесты для gui/dialogs/pwa_qr_dialog.py::PWAQRDialog — закрытие нативной
кнопкой окна (крестик/Alt+F4) не сохраняло геометрию, в отличие от
ActPreviewWindow/ClientHistoryWindow, которые оба переопределяют
WM_DELETE_WINDOW (workflow-найденный баг: диалог никогда не переопределял
этот протокол вовсе, так что закрытие в обход кнопки "✖ Закрыть окно"
уничтожало окно без вызова close_dialog_with_geometry())."""

from __future__ import annotations

import pytest

pytest.importorskip("gui")

from gui.dialogs.pwa_qr_dialog import PWAQRDialog
from utils.colors import get_colors
from utils.window_state import GEOMETRY_KEY


class _FakeSettings:
    def __init__(self):
        self.data: dict[str, object] = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


@pytest.fixture
def dialog(tk_root):
    settings = _FakeSettings()
    dlg = PWAQRDialog(
        tk_root,
        server_url="http://192.168.1.5:8123",
        colors=get_colors("light"),
        settings=settings,
    )
    dlg._test_settings = settings
    yield dlg
    if dlg.winfo_exists():
        dlg.destroy()


class TestNativeCloseSavesGeometry:
    def test_wm_delete_window_protocol_is_registered(self, dialog):
        handler_name = dialog.protocol("WM_DELETE_WINDOW")
        assert handler_name, (
            "WM_DELETE_WINDOW must be explicitly registered — otherwise "
            "closing via the native window control bypasses "
            "close_dialog_with_geometry() entirely"
        )

    def test_native_close_saves_geometry_before_destroying(self, dialog):
        settings = dialog._test_settings
        handler_name = dialog.protocol("WM_DELETE_WINDOW")

        # Симулируем нажатие нативного крестика окна — вызываем ровно тот
        # Tcl-колбэк, который менеджер окон дёрнул бы сам.
        dialog.tk.call(handler_name)

        assert f"{GEOMETRY_KEY}.pwa_qr" in settings.data
