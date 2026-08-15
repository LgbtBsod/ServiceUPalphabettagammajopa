#!/usr/bin/env python3

"""Тесты для core/kernel.py::ServiceUpCore — центрального ядра/медиатора.

До этих тестов вся живая архитектура (Kernel, DI-контейнер, реестр модулей,
плагины, facade БД), построенная в этой сессии, не имела покрытия вовсе —
существующие database/tests/test_repositories.py и services/test_services.py
тестировали только неиспользуемый мёртвый стек (database/repositories/,
services/, specifications/), который удалён вместе с самими этими тестами,
см. AUDIT_REPORT_v21.md.
"""

import uuid

import pytest

from core.kernel import ServiceUpCore, get_core, reset_core


@pytest.fixture
def core():
    """Свежее, изолированное от других тестов ядро."""
    reset_core()
    c = get_core()
    c.initialize()
    yield c
    reset_core()


class TestServiceUpCoreLifecycle:
    def test_get_core_is_singleton(self):
        reset_core()
        a = get_core()
        b = get_core()
        assert a is b
        reset_core()

    def test_not_initialized_before_initialize(self):
        reset_core()
        c = get_core()
        assert c.is_initialized is False
        reset_core()

    def test_initialize_sets_flag_and_is_idempotent(self, core):
        assert core.is_initialized is True
        # Повторный initialize() не должен падать и не должен пересоздавать сервисы
        core.initialize()
        assert core.is_initialized is True

    def test_services_property_requires_initialization(self):
        reset_core()
        c = ServiceUpCore()
        with pytest.raises(RuntimeError):
            _ = c.services

    def test_shutdown_resets_initialized_flag(self, core):
        core.shutdown()
        assert core.is_initialized is False
        # Возвращаем в инициализированное состояние, чтобы fixture teardown не упал
        core.initialize()


class TestModuleRegistry:
    """Модули регистрируются по имени и доступны ТОЛЬКО через API ядра —
    это единственный разрешённый способ межмодульного взаимодействия
    (см. правило проекта: 'модули не должны получать доступ друг к другу
    напрямую, только через ядро')."""

    def test_register_and_get_module_api(self, core):
        class FakeService:
            def ping(self) -> str:
                return "pong"

        svc = FakeService()
        core.register_module("fake", svc, FakeService, api=svc)

        api = core.get_module_api("fake")
        assert api is svc
        assert api.ping() == "pong"

    def test_call_module_method_routes_through_registry(self, core):
        class Calculator:
            def add(self, a: int, b: int) -> int:
                return a + b

        calc = Calculator()
        core.register_module("calc", calc, Calculator, api=calc)

        result = core.call_module_method("calc", "add", 2, 3)
        assert result == 5

    def test_unregistered_module_api_is_none(self, core):
        assert core.get_module_api("does-not-exist") is None


class TestDIContainer:
    """Отдельный от реестра модулей, типобезопасный DI-контейнер
    (core.register_service/get_service) — используется bootstrap.py для
    Database/менеджеров, см. core/di/container.py."""

    def test_register_and_resolve_service(self, core):
        class Widget:
            pass

        instance = Widget()
        core.register_service(Widget, instance)

        resolved = core.get_service(Widget)
        assert resolved is instance

    def test_get_service_requires_initialization(self):
        reset_core()
        c = ServiceUpCore()
        with pytest.raises(RuntimeError):
            c.get_service(object)


class TestKernelCache:
    """Глобальный кэш ядра (core.cache_*) — часть исходной 5-пунктной спецификации
    ('ядро управляет многопоточностью и кэшем')."""

    def test_cache_roundtrip(self, core):
        key = f"test:{uuid.uuid4()}"
        core.cache_set(key, {"value": 42})
        assert core.cache_get(key) == {"value": 42}

    def test_cache_get_missing_returns_default(self, core):
        assert core.cache_get(f"missing:{uuid.uuid4()}", default="fallback") == "fallback"

    def test_cache_delete(self, core):
        key = f"test:{uuid.uuid4()}"
        core.cache_set(key, "value")
        assert core.cache_delete(key) is True
        assert core.cache_get(key) is None


class TestKernelThreading:
    """Ядро — единственная точка управления потоками (core.create_thread/
    stop_thread), см. AUDIT_REPORT_v21.md о регрессии повторного старта
    PWA-сервера, которую этот тест закрывает."""

    def test_create_start_stop_thread(self, core):
        import threading as _threading

        name = f"test-thread-{uuid.uuid4()}"
        ran = _threading.Event()

        thread_id = core.create_thread(name=name, target=ran.set, daemon=True)
        assert thread_id == name

        assert core.start_thread(thread_id) is True
        assert ran.wait(timeout=5.0) is True

        # Поток уже завершился сам — stop_thread должен вернуть True и
        # освободить имя для повторного использования (см. docstring
        # ServiceUpCore.stop_thread).
        core.stop_thread(thread_id, timeout=2.0)

        # Имя должно быть снова доступно для create_thread с тем же именем —
        # это и есть регрессия, зафиксированная в AUDIT_REPORT_v21.md (PWA-сервер
        # не мог перезапуститься, т.к. ThreadManager не освобождал имя).
        second_id = core.create_thread(name=name, target=lambda: None, daemon=True)
        assert second_id == name
        core.start_thread(second_id)
        core.stop_thread(second_id, timeout=2.0)

    def test_stop_unknown_thread_returns_false_not_raises(self, core):
        assert core.stop_thread(f"unknown-{uuid.uuid4()}", timeout=0.1) is False
