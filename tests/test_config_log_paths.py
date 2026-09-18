#!/usr/bin/env python3

"""Regression test for config/settings.py::get_log_dir()/get_log_file() —
live report: a frozen --windowed Windows build has NO console at all, so a
startup crash (e.g. Flet failing to bind its local web server) left the
user staring at nothing, and there was no log file to diagnose it either —
core/logging/logger.py::setup_logging() already supported a rotating file
handler, it was simply never wired to a real path/called anywhere. Mirrors
the existing _writable_root()/frozen pattern used by get_config_path()/
get_license_key_file()."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from config.settings import ensure_directories, get_log_dir, get_log_file


@pytest.fixture
def not_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)


@pytest.fixture
def frozen_with_localappdata(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    return tmp_path


class TestGetLogDirSource:
    def test_resolves_under_repo_root_when_not_frozen(self, not_frozen):
        log_dir = get_log_dir()
        assert log_dir.name == "logs"
        assert log_dir.parent == Path(__file__).resolve().parent.parent


class TestGetLogDirFrozen:
    def test_resolves_under_local_appdata_when_frozen(self, frozen_with_localappdata):
        log_dir = get_log_dir()
        assert log_dir == frozen_with_localappdata / "ServiceUP" / "logs"

    def test_same_writable_root_as_license_file(self, frozen_with_localappdata):
        """get_log_dir() must live next to .license/backups (survives
        updates, never roamed/cloud-synced) - not wherever the frozen exe
        happens to be extracted this run."""
        from config.settings import get_license_key_file

        log_dir = get_log_dir()
        license_file = get_license_key_file()
        assert log_dir.parent == license_file.parent


class TestGetLogFile:
    def test_is_inside_log_dir(self, not_frozen):
        assert get_log_file().parent == get_log_dir()
        assert get_log_file().name == "serviceup.log"


class TestEnsureDirectoriesCreatesLogDir:
    def test_ensure_directories_creates_the_log_dir(self, not_frozen, tmp_path, monkeypatch):
        import config.settings as settings_module

        monkeypatch.setattr(settings_module, "_writable_root", lambda: tmp_path)
        log_dir = tmp_path / "logs"
        assert not log_dir.exists()

        ensure_directories()

        assert log_dir.is_dir()
