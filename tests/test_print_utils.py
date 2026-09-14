#!/usr/bin/env python3

"""Тесты для reports/print_utils.py::_wait_for_unlock_or_timeout — раньше
print_act_pdf()/open_act_pdf() удаляли временный PDF после БЕЗУСЛОВНОЙ
фиксированной задержки, без проверки, освободил ли просмотрщик/спулер файл
(см. workflow-найденный баг: медленная печать/большой акт могли не
уложиться в задержку, файл удалялся во время чтения)."""

from __future__ import annotations

import sys
import time

import pytest

from reports import print_utils
from reports.print_utils import _wait_for_unlock_or_timeout


class TestWaitForUnlockOrTimeout:
    def test_returns_immediately_when_file_is_free(self, tmp_path):
        path = tmp_path / "act.pdf"
        path.write_bytes(b"%PDF-1.4")

        start = time.monotonic()
        _wait_for_unlock_or_timeout(str(path), timeout_sec=5, poll_interval=0.1)
        assert time.monotonic() - start < 1.0

    @pytest.mark.skipif(
        sys.platform != "win32",
        reason="os.rename(path, path) is a no-op lock probe only on Windows -- "
        "POSIX freely renames files with open handles, see print_utils.py's own "
        "docstring on why this mechanism is only ever invoked on win32",
    )
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

    @pytest.mark.skipif(
        sys.platform != "win32",
        reason="os.rename(path, path) is a no-op lock probe only on Windows -- "
        "POSIX freely renames files with open handles, see print_utils.py's own "
        "docstring on why this mechanism is only ever invoked on win32",
    )
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


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Grace period only applies to the win32 lock-check branch — see "
    "print_utils._STARTUP_GRACE_SEC docstring.",
)
class TestStartupGracePeriod:
    """Workflow-found race: os.startfile() returns as soon as the app is
    LAUNCHED, not once it has actually opened the file. Without an initial
    grace period, the cleanup thread's first lock-probe can run before a
    cold-starting print/viewer app has opened the PDF — finds it "free",
    and deletes it out from under the job that was about to read it."""

    def test_print_act_pdf_sleeps_a_grace_period_before_the_first_lock_check(
        self, tmp_path, monkeypatch
    ):
        pdf_path = str(tmp_path / "act.pdf")
        monkeypatch.setattr(print_utils.os, "startfile", lambda *a, **k: None)
        monkeypatch.setattr(print_utils.os.path, "exists", lambda p: False)

        call_order = []
        monkeypatch.setattr(
            print_utils.time, "sleep", lambda s: call_order.append(("sleep", s))
        )
        monkeypatch.setattr(
            print_utils,
            "_wait_for_unlock_or_timeout",
            lambda *a, **k: call_order.append(("wait_for_unlock", None)),
        )
        captured = {}
        monkeypatch.setattr(
            print_utils, "_start_cleanup_thread", lambda cleanup: captured.__setitem__("cleanup", cleanup)
        )

        print_utils.print_act_pdf(pdf_path, delete_after=True, delay_sec=60)
        captured["cleanup"]()  # выполняем захваченный колбэк синхронно, без реального потока

        assert call_order[0] == ("sleep", print_utils._STARTUP_GRACE_SEC), (
            "первым действием должен быть grace-period sleep, "
            "ДО первой проверки блокировки файла"
        )
        assert call_order[1] == ("wait_for_unlock", None)

    def test_open_act_pdf_sleeps_a_grace_period_before_the_first_lock_check(
        self, tmp_path, monkeypatch
    ):
        pdf_path = str(tmp_path / "act.pdf")
        monkeypatch.setattr(print_utils.os, "startfile", lambda *a, **k: None)
        monkeypatch.setattr(print_utils.os.path, "exists", lambda p: False)

        call_order = []
        monkeypatch.setattr(
            print_utils.time, "sleep", lambda s: call_order.append(("sleep", s))
        )
        monkeypatch.setattr(
            print_utils,
            "_wait_for_unlock_or_timeout",
            lambda *a, **k: call_order.append(("wait_for_unlock", None)),
        )
        captured = {}
        monkeypatch.setattr(
            print_utils, "_start_cleanup_thread", lambda cleanup: captured.__setitem__("cleanup", cleanup)
        )

        print_utils.open_act_pdf(pdf_path, delete_after=True, delay_sec=60)
        captured["cleanup"]()

        assert call_order[0] == ("sleep", print_utils._STARTUP_GRACE_SEC)
        assert call_order[1] == ("wait_for_unlock", None)
