#!/usr/bin/env python3

"""Тесты для core/events/event_bus.py::EventBus — регрессия workflow-
найденного бага: _subscriptions/_event_history/_dead_letter_queue были
обычными dict/list без какой-либо блокировки, в отличие от всех соседних
общих классов в этом слое (ModuleCache/ModuleRegistrySingleton,
ThreadManager/WorkerPool/TaskScheduler), которые используют RLock именно
потому что доступны из нескольких потоков (GUI + PWA Flask-сервер
threaded=True + фоновые worker'ы через core.create_thread).

subscribe() делал classic check-then-act: "if event_type not in
_subscriptions: _subscriptions[event_type] = []" отдельными операциями от
.append()/.sort() — при живом эмпирическом воспроизведении (пониженный
sys.setswitchinterval) это давало не только потерю подписок, но и
ValueError "list modified during sort" при гонке с конкурентным
subscribe()."""

from __future__ import annotations

import sys
import threading

import pytest

from core.events.event_bus import Event, EventBus, get_event_bus, reset_event_bus


class TestConcurrentSubscribeDoesNotLoseSubscriptions:
    def test_many_threads_subscribing_to_the_same_new_event_type(self):
        bus = EventBus()
        n = 20
        barrier = threading.Barrier(n)
        errors: list[Exception] = []
        fired: list[int] = []

        def _make_handler(i: int):
            def _handler(_event: Event) -> None:
                fired.append(i)

            return _handler

        def _worker(i: int):
            barrier.wait()
            try:
                bus.subscribe("same_new_event", _make_handler(i))
            except Exception as e:
                errors.append(e)

        # Пониженный switch-interval расширяет окно гонки check-then-act —
        # тот же приём, которым баг был впервые эмпирически подтверждён.
        old_interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        try:
            threads = [threading.Thread(target=_worker, args=(i,)) for i in range(n)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)
        finally:
            sys.setswitchinterval(old_interval)

        assert errors == [], f"subscribe() must not raise under concurrency: {errors}"
        assert bus.subscription_count == n, (
            f"ожидалось {n} подписок на 'same_new_event', сохранилось "
            f"{bus.subscription_count} — конкурентные subscribe() затёрли "
            f"друг друга"
        )

        bus.publish(Event(event_type="same_new_event"))
        assert len(fired) == n, (
            f"ожидалось {n} сработавших обработчиков, сработало {len(fired)}"
        )


class TestGetEventBusSingletonIsThreadSafe:
    def test_concurrent_first_access_returns_the_same_instance(self):
        reset_event_bus()
        try:
            results: list[EventBus] = []
            barrier = threading.Barrier(10)

            def _worker():
                barrier.wait()
                results.append(get_event_bus())

            threads = [threading.Thread(target=_worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

            assert len({id(r) for r in results}) == 1, (
                "concurrent first-time get_event_bus() calls must all "
                "return the exact same EventBus instance"
            )
        finally:
            reset_event_bus()


@pytest.fixture(autouse=True)
def _reset_bus_after_each_test():
    yield
    reset_event_bus()
