#!/usr/bin/env python3

"""Тесты для core/threading/worker.py::WorkerPool.get_task_result() —
регрессия workflow-найденного бага: параметр timeout полностью
игнорировался — функция проверяла статус ровно один раз и, если задача
ещё не завершилась, сразу возвращала None, неотличимо от "задача
выполнилась и вернула None". Сейчас ни один вызывающий код этим методом
не пользуется, но публичный контракт (docstring обещает ожидание) должен
быть честным для любого будущего потребителя."""

from __future__ import annotations

import time

import pytest

from core.threading.worker import WorkerPool


@pytest.fixture
def pool():
    p = WorkerPool(max_workers=2, name="test-pool")
    p.start()
    yield p
    p.shutdown(wait=True)


class TestGetTaskResultTimeout:
    def test_waits_for_slow_task_up_to_timeout(self, pool):
        def _slow():
            time.sleep(0.2)
            return 42

        pool.submit("slow", _slow)
        result = pool.get_task_result("slow", timeout=2.0)
        assert result == 42

    def test_returns_none_if_still_pending_after_timeout_elapses(self, pool):
        def _slow():
            time.sleep(1.0)
            return "too-late"

        pool.submit("slow2", _slow)
        start = time.monotonic()
        result = pool.get_task_result("slow2", timeout=0.1)
        elapsed = time.monotonic() - start

        assert result is None
        assert elapsed < 0.5, "не должен был ждать дольше собственного timeout"

    def test_returns_immediately_for_already_completed_task(self, pool):
        def _fast():
            return "done"

        pool.submit("fast", _fast)
        # Дать задаче реально завершиться перед проверкой.
        pool.get_task_result("fast", timeout=2.0)

        start = time.monotonic()
        result = pool.get_task_result("fast", timeout=5.0)
        elapsed = time.monotonic() - start

        assert result == "done"
        assert elapsed < 0.5, "уже завершённая задача не должна ждать"

    def test_raises_task_exception_after_waiting(self, pool):
        def _boom():
            time.sleep(0.1)
            raise ValueError("task failure")

        pool.submit("boom", _boom)
        with pytest.raises(ValueError, match="task failure"):
            pool.get_task_result("boom", timeout=2.0)

    def test_unknown_task_id_returns_none_without_waiting(self, pool):
        start = time.monotonic()
        result = pool.get_task_result("does-not-exist", timeout=2.0)
        elapsed = time.monotonic() - start

        assert result is None
        assert elapsed < 0.5
