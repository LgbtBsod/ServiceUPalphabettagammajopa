#!/usr/bin/env python3

"""Настройки приложения по умолчанию (DEFAULT_SETTINGS).

Раньше этот модуль ещё и реэкспортировал бизнес-константы (STATUSES,
PRIORITIES и т.д.) из domain.constants "для обратной совместимости", но
все живые потребители уже импортируют их напрямую из domain.constants —
см. AUDIT_REPORT_v21.md. Единственное, что здесь остаётся не дублировано
нигде больше — сборка DEFAULT_SETTINGS (объединяет domain-константы и
config.settings в словарь, совместимый с managers.settings.SettingsManager).
"""

from __future__ import annotations

from config.settings import get_settings
from domain.constants import DEFAULT_PRIORITY, DEFAULT_STATUS


def _get_default_settings() -> dict:
    """Get default settings from pydantic-settings config.

    Returns a dict compatible with legacy DEFAULT_SETTINGS usage.
    """
    settings = get_settings()
    return {
        "theme": "light",
        "accent_color": "#0078d4",
        "fullscreen": False,
        "confirm_delete": True,
        "confirm_exit": False,
        "auto_save_on_close": True,
        "default_status": DEFAULT_STATUS,
        "default_priority": DEFAULT_PRIORITY,
        "remind_overdue": True,
        "overdue_days": 14,
        "notify_on_ready": settings.notification.push_enabled,
        "auto_backup": True,
        "backup_interval": 24,
        "backup_count": 10,
        "backup_path": "",
        "compress_backups": True,
        "photo_quality": 85,
        "create_thumbnails": True,
        "window_width": 1280,
        "window_height": 720,
        "window_x": None,
        "window_y": None,
        "show_completed": True,
        "transparency": False,
        "transparency_alpha": 1.0,
        "window_geometry": {},
        "pwa": {
            "port": 5000,
            "auto_start": False,
            "auto_sync": True,
            "sync_interval": 30,
        },
    }


DEFAULT_SETTINGS = _get_default_settings()


__all__ = ["DEFAULT_SETTINGS"]
