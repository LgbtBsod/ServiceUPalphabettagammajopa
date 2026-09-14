#!/usr/bin/env python3

"""Тесты для core/plugin_system.py::PluginManager — регрессия workflow-
найденного бага: _plugins/_states были обычными dict без какой-либо
блокировки, в отличие от ModuleRegistrySingleton (core/module_manager.py),
который выполняет ту же роль ("process-wide реестр синглтон-подобных
объектов") и оборачивает каждое обращение в `with self._lock:`.

register()/unregister() писали в _plugins И _states двумя раздельными
операциями без атомарности между ними, а list_plugins()/health_check_all()
итерировали self._plugins.items() через comprehension без блокировки —
классический CPython "dictionary changed size during iteration", если в
этот момент конкурентно выполняется register()/unregister()."""

from __future__ import annotations

import sys
import threading

from core.plugin_system import (
    BasePlugin,
    PluginManager,
    PluginMetadata,
    get_plugin_manager,
    reset_plugin_manager,
)


class _DummyPlugin(BasePlugin):
    def __init__(self, name: str):
        super().__init__()
        self._name = name

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(name=self._name, version="1.0.0", description="", author="")

    def get_api(self):
        return None


class TestConcurrentRegisterDoesNotBreakIteration:
    def test_register_unregister_race_with_list_plugins_and_health_check(self):
        manager = PluginManager()
        n = 200
        stop = threading.Event()
        errors: list[Exception] = []

        def _register_unregister_worker():
            for i in range(n):
                plugin = _DummyPlugin(f"plugin_{i}")
                try:
                    manager.register(plugin)
                    manager.unregister(plugin.metadata.name)
                except Exception as e:  # pragma: no cover - failure path
                    errors.append(e)
            stop.set()

        def _reader_worker():
            while not stop.is_set():
                try:
                    manager.list_plugins()
                    manager.health_check_all()
                except Exception as e:  # pragma: no cover - failure path
                    errors.append(e)

        # Пониженный switch-interval расширяет окно гонки check-then-act —
        # тот же приём, которым были эмпирически подтверждены аналогичные
        # баги в DIContainer/EventBus этой же сессии.
        old_interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        try:
            writer = threading.Thread(target=_register_unregister_worker)
            readers = [threading.Thread(target=_reader_worker) for _ in range(4)]
            writer.start()
            for r in readers:
                r.start()
            writer.join(timeout=15)
            stop.set()
            for r in readers:
                r.join(timeout=15)
        finally:
            sys.setswitchinterval(old_interval)

        assert errors == [], (
            f"register()/unregister() racing with list_plugins()/"
            f"health_check_all() must not raise: {errors}"
        )


class TestGetPluginManagerSingletonIsThreadSafe:
    """Тот же check-then-act race, что PluginManager._lock чинит внутри
    самого класса — только для создания process-wide ЭКЗЕМПЛЯРА менеджера
    (get_plugin_manager())."""

    def test_concurrent_first_access_returns_the_same_instance(self):
        reset_plugin_manager()
        try:
            results: list[PluginManager] = []
            barrier = threading.Barrier(10)

            def _worker():
                barrier.wait()
                results.append(get_plugin_manager())

            threads = [threading.Thread(target=_worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

            assert len({id(r) for r in results}) == 1, (
                "concurrent first-time get_plugin_manager() calls must all "
                "return the exact same PluginManager instance"
            )
        finally:
            reset_plugin_manager()
