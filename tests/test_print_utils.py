#!/usr/bin/env python3

"""Тесты для reports/print_utils.py::_wait_for_unlock_or_timeout — раньше
print_act_pdf()/open_act_pdf() удаляли временный PDF после БЕЗУСЛОВНОЙ
фиксированной задержки, без проверки, освободил ли просмотрщик/спулер файл
(см. workflow-найденный баг: медленная печать/большой акт могли не
уложиться в задержку, файл удалялся во время чтения)."""

from __future__ import annotations

import time

from reports.print_utils import _wait_for_unlock_or_timeout


class TestWaitForUnlockOrTimeout:
    def test_returns_immediately_when_file_is_free(self, tmp_path):
        path = tmp_path / "act.pdf"
        path.write_bytes(b"%PDF-1.4")

        start = time.monotonic()
        _wait_for_unlock_or_timeout(str(path), timeout_sec=5, poll_interval=0.1)
        assert time.monotonic() - start < 1.0

    def test_returns_once_lock_is_released(self, tmp_path):
        path = tmp_path / "act.pdf"
        path.write_bytes(b"%PDF-1.4")

        handle = open(path, "r+b")  # noqa: SIM115 — держим лок вручную для теста
        try:
            import threading

            def _release_after_delay():
                time.sleep(0.3)
                handle.close()

            threading.Thread(target=_release_after_delay, daemon=True).start()

            start = time.monotonic()
            _wait_for_unlock_or_timeout(str(path), timeout_sec=5, poll_interval=0.05)
            elapsed = time.monotonic() - start
            assert 0.25 <= elapsed < 5.0, "не дождался разблокировки или прождал слишком долго"
        finally:
            if not handle.closed:
                handle.close()

    def test_gives_up_after_timeout_if_never_unlocked(self, tmp_path):
        path = tmp_path / "act.pdf"
        path.write_bytes(b"%PDF-1.4")

        handle = open(path, "r+b")  # noqa: SIM115 — держим лок на весь тест
        try:
            start = time.monotonic()
            _wait_for_unlock_or_timeout(str(path), timeout_sec=0.3, poll_interval=0.05)
            elapsed = time.monotonic() - start
            assert elapsed >= 0.3, "вернулся раньше таймаута, хотя файл всё ещё занят"
        finally:
            handle.close()

    def test_missing_file_does_not_hang(self, tmp_path):
        """Открытие несуществующего файла тоже бросает OSError — цикл
        должен корректно завершиться по таймауту, а не зависнуть."""
        path = tmp_path / "no_such_file.pdf"
        start = time.monotonic()
        _wait_for_unlock_or_timeout(str(path), timeout_sec=0.2, poll_interval=0.05)
        assert time.monotonic() - start < 2.0
