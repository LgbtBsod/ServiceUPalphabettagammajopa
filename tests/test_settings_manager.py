#!/usr/bin/env python3

"""Тесты для managers/settings.py::SettingsManager — не имел ни одного
теста, несмотря на то что backs каждое чтение/запись настроек в обеих
оболочках (например gui/main_window_parts/pwa_mixin.py читает
settings.get("pwa.port", ...)) — dotted-path обход в get()/set(),
merge_settings() и fallback load_settings() на битый JSON ни разу не были
проверены."""

import json
import os
import tempfile

import pytest

from managers.settings import SettingsManager
from utils.constants import DEFAULT_SETTINGS


@pytest.fixture
def config_path():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(path)  # SettingsManager должен уметь стартовать БЕЗ файла
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def manager(config_path) -> SettingsManager:
    return SettingsManager(config_file=config_path)


class TestGetSet:
    def test_simple_key_roundtrip(self, manager):
        manager.set("theme", "dark")
        assert manager.get("theme") == "dark"

    def test_dotted_key_roundtrip(self, manager):
        manager.set("pwa.port", 5000)
        assert manager.get("pwa.port") == 5000

    def test_get_missing_key_returns_default(self, manager):
        assert manager.get("does_not_exist", "fallback") == "fallback"

    def test_get_dotted_path_missing_intermediate_returns_default_not_raise(self, manager):
        """Промежуточного ключа "nope" нет вообще — get() должен вернуть
        default, а не бросить KeyError/TypeError на попытке .get() у None."""
        assert manager.get("nope.deeper", "fallback") == "fallback"

    def test_set_creates_missing_intermediate_dict(self, manager):
        manager.set("brand_new_section.field", 42)
        assert manager.get("brand_new_section.field") == 42
        assert isinstance(manager.settings["brand_new_section"], dict)

    def test_set_on_scalar_intermediate_replaces_it_instead_of_raising(self, manager):
        """Регрессия: если промежуточный сегмент пути уже хранит скаляр
        (устаревший/повреждённый config.json), set() раньше падал с
        TypeError на попытке индексировать этот скаляр — теперь он
        молча замещается пустым словарём и запись проходит."""
        manager.settings["pwa"] = "5000"  # раньше был бы вложенный dict

        manager.set("pwa.port", 6000)

        assert manager.get("pwa.port") == 6000
        assert isinstance(manager.settings["pwa"], dict)


class TestMergeSettings:
    def test_merges_partial_saved_config_over_defaults(self, manager):
        merged = manager.merge_settings(
            {"theme": "light", "pwa": {"port": 5000, "enabled": False}},
            {"theme": "dark"},
        )
        assert merged["theme"] == "dark"
        assert merged["pwa"] == {"port": 5000, "enabled": False}

    def test_merges_nested_dict_recursively(self, manager):
        merged = manager.merge_settings(
            {"pwa": {"port": 5000, "enabled": False}},
            {"pwa": {"enabled": True}},
        )
        assert merged["pwa"] == {"port": 5000, "enabled": True}

    def test_ignores_unknown_keys_from_loaded_config(self, manager):
        merged = manager.merge_settings({"theme": "light"}, {"theme": "dark", "ghost_key": 1})
        assert merged == {"theme": "dark"}


class TestLoadSettings:
    def test_missing_config_file_falls_back_to_defaults(self, config_path):
        assert not os.path.exists(config_path)
        mgr = SettingsManager(config_file=config_path)
        assert mgr.settings == DEFAULT_SETTINGS

    def test_valid_config_file_is_merged_over_defaults(self, config_path):
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({"theme": "dark"}, f)
        mgr = SettingsManager(config_file=config_path)
        assert mgr.settings["theme"] == "dark"
        assert mgr.settings["backup_count"] == DEFAULT_SETTINGS["backup_count"]

    def test_corrupt_json_falls_back_to_defaults_instead_of_raising(self, config_path):
        with open(config_path, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        mgr = SettingsManager(config_file=config_path)
        assert mgr.settings == DEFAULT_SETTINGS


class TestSaveSettings:
    def test_set_persists_to_disk(self, config_path):
        mgr = SettingsManager(config_file=config_path)
        mgr.set("theme", "dark")

        reloaded = SettingsManager(config_file=config_path)
        assert reloaded.get("theme") == "dark"


class TestResetToDefaults:
    def test_reset_restores_defaults_and_saves(self, manager):
        manager.set("theme", "dark")
        manager.reset_to_defaults()
        assert manager.settings == DEFAULT_SETTINGS

        reloaded = SettingsManager(config_file=manager.config_file)
        assert reloaded.settings["theme"] == DEFAULT_SETTINGS["theme"]
