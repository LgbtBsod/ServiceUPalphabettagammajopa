#!/usr/bin/env python3
"""BackupMixin — периодический бэкап БД, пока приложение открыто. См.
AUDIT_REPORT_v25.md, Task T (перенесено из main_window.py без изменения
поведения)."""

from __future__ import annotations

import contextlib
import logging

from config import DB_PATH

logger = logging.getLogger(__name__)


class BackupMixin:
    """Требует от финального класса ServiceCenterApp: self.settings,
    self.root, self.backup_manager."""

    def _start_periodic_backup(self):
        """Периодический бэкап раз в backup_interval часов, пока приложение
        открыто — тот же .after()-паттерн, что и _start_auto_sync().

        Раньше backup_interval сохранялся в настройках, но нигде не
        читался: реальный бэкап делался только один раз, при закрытии
        приложения (если включён auto_backup) — подпись поля "Интервал
        (часов)" вводила в заблуждение, см. AUDIT_REPORT_v25.md."""
        self._periodic_backup_after_id = None
        if not self.settings.get("auto_backup", True):
            return
        interval_hours = self.settings.get("backup_interval", 24)
        if not interval_hours or interval_hours <= 0:
            return
        interval_ms = int(interval_hours * 60 * 60 * 1000)

        def _tick():
            try:
                self.backup_manager.create_backup(DB_PATH)
            except Exception as e:
                logger.warning(f"Периодический бэкап не выполнен: {e}")
            self._periodic_backup_after_id = self.root.after(interval_ms, _tick)

        self._periodic_backup_after_id = self.root.after(interval_ms, _tick)

    def _stop_periodic_backup(self):
        """Останавливает периодический бэкап."""
        if getattr(self, "_periodic_backup_after_id", None) is not None:
            with contextlib.suppress(Exception):
                self.root.after_cancel(self._periodic_backup_after_id)
            self._periodic_backup_after_id = None
