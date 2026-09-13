#!/usr/bin/env python3

"""Тесты для core/plugin_system.py::PluginManager.enable()/disable() —
регрессия workflow-найденного бага: enable() пускал дальше ТОЛЬКО из
PluginState.UNLOADED, а disable() оставляет плагин в PluginState.DISABLED
(не в UNLOADED) — однажды отключённый плагин нельзя было включить обратно
никогда через публичный enable()/enable_plugin()."""

from __future__ import annotations

from core.plugin_system import BasePlugin, PluginManager, PluginMetadata, PluginState


class _DummyPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self.init_count = 0

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(name="dummy", version="1.0.0", description="", author="")

    def on_initialize(self, context) -> bool:
        self.init_count += 1
        return True

    def get_api(self):
        return None


class TestPluginEnableDisableCycle:
    def test_enable_after_disable_succeeds(self):
        manager = PluginManager()
        plugin = _DummyPlugin()
        manager.register(plugin)

        assert manager.load("dummy") is True
        assert manager._states["dummy"] == PluginState.ACTIVE

        manager.disable("dummy")
        assert manager._states["dummy"] == PluginState.DISABLED

        assert manager.enable("dummy") is True, "плагин не смог включиться обратно после disable()"
        assert manager._states["dummy"] == PluginState.ACTIVE
        assert plugin.init_count == 2, "повторный enable() должен снова вызвать on_initialize()"

    def test_enable_from_unloaded_still_works(self):
        manager = PluginManager()
        plugin = _DummyPlugin()
        manager.register(plugin)

        assert manager._states["dummy"] == PluginState.UNLOADED
        assert manager.enable("dummy") is True
        assert manager._states["dummy"] == PluginState.ACTIVE

    def test_enable_already_active_is_a_noop_true(self):
        manager = PluginManager()
        plugin = _DummyPlugin()
        manager.register(plugin)
        manager.load("dummy")

        assert manager.enable("dummy") is True
        assert plugin.init_count == 1, "уже активный плагин не должен переинициализироваться"

    def test_enable_while_loading_is_refused(self):
        manager = PluginManager()
        plugin = _DummyPlugin()
        manager.register(plugin)
        manager._states["dummy"] = PluginState.LOADING

        assert manager.enable("dummy") is False
