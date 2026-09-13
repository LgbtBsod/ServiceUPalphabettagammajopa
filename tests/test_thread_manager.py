#!/usr/bin/env python3

"""Тесты для core/threading/manager.py::ThreadManager — регрессия
workflow-найденного бага: wrapped_target()'s finally безусловно
перезаписывал status в STOPPED следом за except-блоком, который только что
выставил ERROR — ни один вызывающий get_thread_status()/get_all_statuses()
не мог увидеть, что поток реально упал (.error при этом сохранялся
корректно, только status врал)."""

from __future__ import annotations

import time

from core.threading.manager import ThreadManager, ThreadStatus


def _wait_until_stopped(manager: ThreadManager, name: str, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = manager.get_thread_status(name)
        if status in (ThreadStatus.STOPPED, ThreadStatus.ERROR):
            return
        time.sleep(0.01)


class TestThreadStatusAfterFailure:
    def test_failed_target_leaves_status_as_error_not_stopped(self):
        manager = ThreadManager()

        def _boom():
            raise RuntimeError("boom")

        manager.create_thread("failing", _boom)
        manager.start_thread("failing")
        _wait_until_stopped(manager, "failing")

        assert manager.get_thread_status("failing") == ThreadStatus.ERROR

    def test_error_field_still_populated(self):
        manager = ThreadManager()

        def _boom():
            raise ValueError("specific failure")

        manager.create_thread("failing2", _boom)
        manager.start_thread("failing2")
        _wait_until_stopped(manager, "failing2")

        info = manager._threads["failing2"]
        assert isinstance(info.error, ValueError)
        assert str(info.error) == "specific failure"

    def test_successful_target_still_reports_stopped(self):
        """Позитивный контроль: обычное успешное завершение по-прежнему
        должно давать STOPPED, а не что-то ещё."""
        manager = ThreadManager()

        def _ok():
            pass

        manager.create_thread("ok", _ok)
        manager.start_thread("ok")
        _wait_until_stopped(manager, "ok")

        assert manager.get_thread_status("ok") == ThreadStatus.STOPPED
