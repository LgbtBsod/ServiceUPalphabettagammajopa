#!/usr/bin/env python3

"""Тесты для core/module_manager.py — регрессия workflow-найденного бага:
get_module_cache()/get_module_singleton_registry() — module-level singleton
getter'ы с unsync check-then-act на _module_cache/_module_singleton_registry,
идентичным паттерном уже пофикшенным (double-checked locking) в
get_core()/get_container()/get_event_bus()/get_plugin_manager(). Оба вызываются
напрямую из ServiceUpCore.__init__ (core/kernel.py:143,146), так что гонка
здесь каскадирует из любой гонки в get_core()."""

from __future__ import annotations

import threading
import time

from core.module_manager import (
    ModuleCache,
    ModuleRegistrySingleton,
    get_module_cache,
    get_module_singleton_registry,
    reset_module_system,
)


class TestGetModuleCacheSingletonIsThreadSafe:
    def test_concurrent_first_access_returns_the_same_instance(self, monkeypatch):
        reset_module_system()
        original_init = ModuleCache.__init__

        def _slow_init(self):
            time.sleep(0.05)
            original_init(self)

        monkeypatch.setattr(ModuleCache, "__init__", _slow_init)
        try:
            results: list[ModuleCache] = []
            barrier = threading.Barrier(10)

            def _worker():
                barrier.wait()
                results.append(get_module_cache())

            threads = [threading.Thread(target=_worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

            assert len({id(r) for r in results}) == 1, (
                "concurrent first-time get_module_cache() calls must all "
                "return the exact same ModuleCache instance"
            )
        finally:
            reset_module_system()


class TestGetModuleSingletonRegistryIsThreadSafe:
    def test_concurrent_first_access_returns_the_same_instance(self, monkeypatch):
        reset_module_system()
        original_init = ModuleRegistrySingleton.__init__

        def _slow_init(self):
            time.sleep(0.05)
            original_init(self)

        monkeypatch.setattr(ModuleRegistrySingleton, "__init__", _slow_init)
        try:
            results: list[ModuleRegistrySingleton] = []
            barrier = threading.Barrier(10)

            def _worker():
                barrier.wait()
                results.append(get_module_singleton_registry())

            threads = [threading.Thread(target=_worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

            assert len({id(r) for r in results}) == 1, (
                "concurrent first-time get_module_singleton_registry() calls "
                "must all return the exact same ModuleRegistrySingleton instance"
            )
        finally:
            reset_module_system()
