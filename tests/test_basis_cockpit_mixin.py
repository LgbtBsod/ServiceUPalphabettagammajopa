#!/usr/bin/env python3

"""Тесты для gui/main_window_parts/basis_cockpit_mixin.py::
BasisCockpitMixin._save_basis_locking_settings() — TTL блокировки заказа
всегда кламп в [120, 3600] секунд, а нечисловой ввод молча заменяется
дефолтом 300, а не роняет сохранение (см. комментарий в самом
basis_cockpit_mixin.py: heartbeat держателя блокировки тикает раз в 60с,
TTL ниже этого интервала ломает UX-индикатор "занято другим").

messagebox.showinfo() здесь всегда замоканы — иначе тест показал бы
настоящее модальное окно на не-headless машине и повесил бы процесс (тот
же риск, что и в tests/test_device_form_defect_tags.py)."""

from __future__ import annotations

import pytest

from gui.main_window_parts.basis_cockpit_mixin import BasisCockpitMixin


class _StubVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


class _StubEntry:
    def __init__(self, text: str):
        self._text = text

    def get(self):
        return self._text


class _StubSettings:
    def __init__(self, **values):
        self._values = dict(values)
        self.saved: list[tuple[str, object]] = []
        self.save_calls = 0

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value):
        self._values[key] = value
        self.saved.append((key, value))

    def save_settings(self):
        self.save_calls += 1


class _App(BasisCockpitMixin):
    def __init__(self, ttl_text: str, *, pessimistic: bool = True):
        self.settings = _StubSettings()
        self.basis_pessimistic_lock_var = _StubVar(pessimistic)
        self.basis_lock_ttl_entry = _StubEntry(ttl_text)


@pytest.fixture(autouse=True)
def _no_real_dialogs(monkeypatch):
    monkeypatch.setattr(
        "gui.main_window_parts.basis_cockpit_mixin.messagebox.showinfo",
        lambda *_a, **_kw: None,
    )
    monkeypatch.setattr(
        "gui.main_window_parts.basis_cockpit_mixin.messagebox.showerror",
        lambda *_a, **_kw: None,
    )


class TestLockTtlClamping:
    def test_value_within_range_is_saved_unchanged(self):
        app = _App("600")

        app._save_basis_locking_settings()

        assert ("lock_ttl_seconds", 600) in app.settings.saved

    def test_value_below_minimum_is_clamped_to_120(self):
        app = _App("10")

        app._save_basis_locking_settings()

        assert ("lock_ttl_seconds", 120) in app.settings.saved

    def test_value_above_maximum_is_clamped_to_3600(self):
        app = _App("999999")

        app._save_basis_locking_settings()

        assert ("lock_ttl_seconds", 3600) in app.settings.saved

    def test_non_numeric_input_falls_back_to_default_300(self):
        app = _App("не число")

        app._save_basis_locking_settings()

        assert ("lock_ttl_seconds", 300) in app.settings.saved

    def test_empty_input_falls_back_to_default_300(self):
        app = _App("")

        app._save_basis_locking_settings()

        assert ("lock_ttl_seconds", 300) in app.settings.saved

    def test_pessimistic_lock_flag_is_saved_alongside_ttl(self):
        app = _App("300", pessimistic=False)

        app._save_basis_locking_settings()

        assert ("pessimistic_locking_enabled", False) in app.settings.saved

    def test_settings_are_persisted_immediately_not_deferred(self):
        app = _App("300")

        app._save_basis_locking_settings()

        assert app.settings.save_calls == 1, (
            "unlike regular user settings (SettingsWindow), the Basis admin "
            "toggle must save immediately, not wait for app close"
        )
