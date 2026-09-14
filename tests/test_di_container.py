#!/usr/bin/env python3

"""Тесты для core/di/container.py::DIContainer — регрессия workflow-
найденного бага: _resolution_stack был обычным list на экземпляре
контейнера, а DIContainer — процесс-широкий singleton (get_container()),
к которому могут одновременно обращаться разные потоки (GUI + PWA Flask-
сервер threaded=True + фоновые worker'ы). Обнаружение циклических
зависимостей — по своей природе состояние ОДНОЙ цепочки вызовов ОДНОГО
потока: с общим list два потока, одновременно конструирующих (через
_create_instance()) один и тот же — совершенно нециклический — класс,
видели push друг друга в стеке и один из них мог ловить ложный
CircularDependencyError."""

from __future__ import annotations

import threading
import time

from core.di.container import (
    CircularDependencyError,
    DIContainer,
    get_container,
    reset_container,
)


class _SlowConstruct:
    """Специально медленный __init__ — расширяет окно гонки, в течение
    которого класс "числится" в _resolution_stack одного потока, пока
    другой поток пытается сконструировать тот же класс независимо."""

    def __init__(self):
        time.sleep(0.05)


class _NoDeps:
    pass


class TestResolutionStackIsPerThread:
    def test_concurrent_create_of_same_class_does_not_false_positive_cycle(self):
        container = DIContainer()
        errors: list[Exception] = []
        results: list[object] = []
        barrier = threading.Barrier(2)

        def _worker():
            barrier.wait()
            try:
                results.append(container.create(_SlowConstruct))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert errors == [], (
            f"независимое конкурентное конструирование одного и того же "
            f"класса из разных потоков не должно падать: {errors}"
        )
        assert len(results) == 2
        assert all(isinstance(r, _SlowConstruct) for r in results)

    def test_resolution_stack_is_empty_after_create_on_each_thread(self):
        """_resolution_stack — приватная деталь реализации, но её "утечка"
        (не опустошается после успешного _create_instance) сломала бы
        обнаружение РЕАЛЬНЫХ циклов при следующем вызове в том же потоке."""
        container = DIContainer()
        container.create(_NoDeps)
        assert container._resolution_stack == []

    def test_real_circular_dependency_still_detected_within_one_thread(self):
        """Позитивный контроль: thread-local не должен маскировать
        настоящий цикл внутри ОДНОЙ цепочки вызовов одного потока."""
        container = DIContainer()
        # Симулируем то же состояние, что _create_instance видит в середине
        # рекурсивного разрешения зависимостей одного вызова.
        container._resolution_stack.append(_NoDeps)
        try:
            import pytest

            with pytest.raises(CircularDependencyError):
                container._create_instance(_NoDeps)
        finally:
            container._resolution_stack.pop()


class _SlowSingletonService:
    """Медленный __init__ + счётчик конструирований на классе — расширяет
    окно гонки check-then-act в resolve() и делает двойное конструирование
    (если оно случится) наблюдаемым."""

    construct_count = 0
    _count_lock = threading.Lock()

    def __init__(self):
        with self._count_lock:
            type(self).construct_count += 1
        time.sleep(0.05)


class TestResolveSingletonCacheIsThreadSafe:
    """Workflow-найденный баг: resolve() читал/писал descriptor.instance без
    блокировки — check (`instance is not None`), затем (на миссе) построение
    через _resolve_service()/_create_instance(), затем запись `instance =
    ...` — три раздельных шага без синхронизации между ними. Два потока,
    одновременно резолвящие один и тот же ещё не построенный SINGLETON,
    могли оба увидеть instance is None и оба сконструировать его заново
    (двойной вызов конструктора и его побочных эффектов), после чего
    последняя запись молча "побеждала", а другой поток держал ссылку на
    осиротевший дубликат — нарушение самого контракта singleton."""

    def test_concurrent_resolve_of_same_singleton_constructs_exactly_once(self):
        container = DIContainer()
        container.register_singleton(_SlowSingletonService)
        _SlowSingletonService.construct_count = 0

        results: list[object] = []
        errors: list[Exception] = []
        barrier = threading.Barrier(2)

        def _worker():
            barrier.wait()
            try:
                results.append(container.resolve(_SlowSingletonService))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert errors == []
        assert len(results) == 2
        assert _SlowSingletonService.construct_count == 1, (
            f"singleton constructor ran {_SlowSingletonService.construct_count} "
            f"times — two threads resolving the same singleton concurrently "
            f"must not both construct it"
        )
        assert results[0] is results[1], (
            "both threads must receive the exact same singleton instance"
        )


class TestGetContainerSingletonIsThreadSafe:
    """Тот же check-then-act race, что resolve() чинит блокировкой внутри
    самого класса — только для создания process-wide ЭКЗЕМПЛЯРА контейнера
    (get_container())."""

    def test_concurrent_first_access_returns_the_same_instance(self):
        reset_container()
        try:
            results: list[DIContainer] = []
            barrier = threading.Barrier(10)

            def _worker():
                barrier.wait()
                results.append(get_container())

            threads = [threading.Thread(target=_worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

            assert len({id(r) for r in results}) == 1, (
                "concurrent first-time get_container() calls must all "
                "return the exact same DIContainer instance"
            )
        finally:
            reset_container()
