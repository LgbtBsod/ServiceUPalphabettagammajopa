#!/usr/bin/env python3

"""Regression test for bootstrap.py::check_dependencies() — live report from
a fresh git checkout (no .venv) confirmed `python main.py --ui=flet` raised
a raw `ModuleNotFoundError: No module named 'flet'` traceback instead of the
same clean "Отсутствуют обязательные пакеты" message the classic GUI gets
for a missing customtkinter/PIL: the check only ever validated
customtkinter/PIL, never flet, even though main.py can route to the Flet
GUI via --ui=flet or the interactive chooser dialog."""

from __future__ import annotations

import builtins

import pytest

from bootstrap import check_dependencies

_REAL_IMPORT = builtins.__import__


def _block(*blocked_names: str):
    """Monkeypatch-friendly __import__ that raises ImportError for any of
    blocked_names (top-level module name only) and defers to the real
    import otherwise."""

    def _fake_import(name, *args, **kwargs):
        if name in blocked_names:
            raise ImportError(f"No module named {name!r}")
        return _REAL_IMPORT(name, *args, **kwargs)

    return _fake_import


class TestFletRequiredWhenReachable:
    def test_missing_flet_fails_with_no_ui_override(self, monkeypatch):
        """No --ui= means the interactive chooser could still route to
        Flet — a missing flet must be caught here, not surfaced as a raw
        traceback later."""
        monkeypatch.setattr(builtins, "__import__", _block("flet"))
        assert check_dependencies(None) is False

    def test_missing_flet_fails_with_explicit_ui_flet(self, monkeypatch):
        monkeypatch.setattr(builtins, "__import__", _block("flet"))
        assert check_dependencies("flet") is False

    def test_missing_flet_reports_the_pip_extras_spec(self, monkeypatch, capsys):
        monkeypatch.setattr(builtins, "__import__", _block("flet"))
        check_dependencies("flet")
        assert "flet[web]" in capsys.readouterr().out


class TestFletNotRequiredForClassicOnly:
    def test_missing_flet_does_not_fail_explicit_ui_classic(self, monkeypatch):
        """--ui=classic never reaches gui_flet - a missing flet must not
        block someone who only wants the classic interface."""
        monkeypatch.setattr(builtins, "__import__", _block("flet"))
        assert check_dependencies("classic") is True


class TestCustomtkinterAlwaysRequired:
    """customtkinter/PIL are used for the license/update dialogs
    (ctk.CTk()) regardless of which order-management UI is chosen -
    main.py imports/uses them even under --ui=flet."""

    @pytest.mark.parametrize("ui_mode", [None, "classic", "flet"])
    def test_missing_customtkinter_fails_regardless_of_ui_mode(self, monkeypatch, ui_mode):
        monkeypatch.setattr(builtins, "__import__", _block("customtkinter"))
        assert check_dependencies(ui_mode) is False

    @pytest.mark.parametrize("ui_mode", [None, "classic", "flet"])
    def test_missing_pillow_fails_regardless_of_ui_mode(self, monkeypatch, ui_mode):
        monkeypatch.setattr(builtins, "__import__", _block("PIL"))
        assert check_dependencies(ui_mode) is False


class TestPydanticAndSqlalchemyAlwaysRequired:
    """config/settings.py (pydantic) and database/ (sqlalchemy) are
    imported in main.py before any --ui= branching (ensure_directories(),
    initialize_kernel()) - a missing one must be caught here too, not
    surface as a raw traceback partway through startup."""

    @pytest.mark.parametrize("ui_mode", [None, "classic", "flet"])
    def test_missing_pydantic_fails_regardless_of_ui_mode(self, monkeypatch, ui_mode):
        monkeypatch.setattr(builtins, "__import__", _block("pydantic"))
        assert check_dependencies(ui_mode) is False

    @pytest.mark.parametrize("ui_mode", [None, "classic", "flet"])
    def test_missing_sqlalchemy_fails_regardless_of_ui_mode(self, monkeypatch, ui_mode):
        monkeypatch.setattr(builtins, "__import__", _block("sqlalchemy"))
        assert check_dependencies(ui_mode) is False


class TestAllPresent:
    @pytest.mark.parametrize("ui_mode", [None, "classic", "flet"])
    def test_returns_true_when_everything_importable(self, ui_mode):
        assert check_dependencies(ui_mode) is True
