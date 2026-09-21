#!/usr/bin/env python3

"""Тесты для gui/main_window_parts/backup_mixin.py::BackupMixin —
периодический бэкап БД по таймеру Tk (self.root.after()).

Как и tests/test_async_load_mixin.py — без реального Tk mainloop:
_StubRoot.after()/after_cancel() просто записывают вызовы вместо
реального планирования, тест сам "тикает" колбэк, когда нужно
проверить переустановку таймера на следующий цикл."""

from __future__ import annotations

from config import DB_PATH
from gui.main_window_parts.backup_mixin import BackupMixin


class _StubRoot:
    def __init__(self):
        self.scheduled: list = []  # [(delay_ms, fn), ...]
        self.cancelled: list = []

    def after(self, delay_ms, fn):
        token = len(self.scheduled)
        self.scheduled.append((delay_ms, fn))
        return token

    def after_cancel(self, token):
        self.cancelled.append(token)


class _StubBackupManager:
    def __init__(self, *, raises: bool = False):
        self.raises = raises
        self.calls: list = []

    def create_backup(self, db_path):
        self.calls.append(db_path)
        if self.raises:
            raise RuntimeError("disk full")


class _StubSettings:
    def __init__(self, **values):
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)


class _App(BackupMixin):
    def __init__(self, settings, backup_manager=None):
        self.settings = settings
        self.root = _StubRoot()
        self.backup_manager = backup_manager or _StubBackupManager()


class TestStartPeriodicBackupScheduling:
    def test_disabled_auto_backup_schedules_nothing(self):
        app = _App(_StubSettings(auto_backup=False, backup_interval=24))

        app._start_periodic_backup()

        assert not app.root.scheduled
        assert app._periodic_backup_after_id is None

    def test_zero_interval_schedules_nothing(self):
        app = _App(_StubSettings(auto_backup=True, backup_interval=0))

        app._start_periodic_backup()

        assert not app.root.scheduled

    def test_negative_interval_schedules_nothing(self):
        app = _App(_StubSettings(auto_backup=True, backup_interval=-5))

        app._start_periodic_backup()

        assert not app.root.scheduled

    def test_enabled_schedules_at_the_configured_interval(self):
        app = _App(_StubSettings(auto_backup=True, backup_interval=2))

        app._start_periodic_backup()

        assert len(app.root.scheduled) == 1
        delay_ms, _fn = app.root.scheduled[0]
        assert delay_ms == 2 * 60 * 60 * 1000
        assert app._periodic_backup_after_id is not None

    def test_tick_creates_a_backup_and_reschedules_itself(self):
        backup_manager = _StubBackupManager()
        app = _App(_StubSettings(auto_backup=True, backup_interval=1), backup_manager)
        app._start_periodic_backup()

        _delay_ms, tick = app.root.scheduled[0]
        tick()

        assert backup_manager.calls == [DB_PATH]
        assert len(app.root.scheduled) == 2, (
            "a tick must re-arm the timer, otherwise periodic backup "
            "silently stops after running exactly once"
        )

    def test_tick_reschedules_even_when_backup_fails(self):
        backup_manager = _StubBackupManager(raises=True)
        app = _App(_StubSettings(auto_backup=True, backup_interval=1), backup_manager)
        app._start_periodic_backup()

        _delay_ms, tick = app.root.scheduled[0]
        tick()  # не должен бросить наружу

        assert len(app.root.scheduled) == 2, (
            "a failed backup attempt must not stop future scheduled attempts"
        )


class TestStopPeriodicBackup:
    def test_cancels_the_scheduled_timer(self):
        app = _App(_StubSettings(auto_backup=True, backup_interval=1))
        app._start_periodic_backup()
        token = app._periodic_backup_after_id

        app._stop_periodic_backup()

        assert app.root.cancelled == [token]
        assert app._periodic_backup_after_id is None

    def test_stopping_when_never_started_is_a_no_op(self):
        app = _App(_StubSettings(auto_backup=True, backup_interval=1))

        app._stop_periodic_backup()

        assert not app.root.cancelled

    def test_after_cancel_raising_does_not_propagate(self):
        class _BrokenRoot(_StubRoot):
            def after_cancel(self, token):
                raise RuntimeError("already destroyed")

        app = _App(_StubSettings(auto_backup=True, backup_interval=1))
        app.root = _BrokenRoot()
        app._start_periodic_backup()

        app._stop_periodic_backup()  # не должен бросить

        assert app._periodic_backup_after_id is None
