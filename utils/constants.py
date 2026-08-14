#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Константы приложения - DEPRECATED.

Этот модуль устарел и будет удален в версии 20.0.
Используйте:
    - domain.constants для бизнес-констант (STATUSES, PRIORITIES и т.д.)
    - config.settings для настроек приложения (DEFAULT_SETTINGS)

Principles applied:
- SSOT: Constants moved to domain.constants
- DRY: Re-export from single source
"""

from __future__ import annotations
import warnings

# Import from single source of truth in domain layer
from domain.constants import (
    STATUSES,
    DEFAULT_STATUS,
    PRIORITIES,
    DEFAULT_PRIORITY,
    CLIENT_STATUSES,
    WARRANTIES,
    DICTIONARY_TYPES,
)

# Import default settings from config (application settings, not domain constants)
from config.settings import get_settings


def _get_default_settings() -> dict:
    """Get default settings from pydantic-settings config.
    
    Returns a dict compatible with legacy DEFAULT_SETTINGS usage.
    """
    settings = get_settings()
    return {
        'theme': 'light',
        'accent_color': '#0078d4',
        'fullscreen': False,
        'confirm_delete': True,
        'confirm_exit': False,
        'auto_save_on_close': True,
        'default_status': DEFAULT_STATUS,
        'default_priority': DEFAULT_PRIORITY,
        'remind_overdue': True,
        'overdue_days': 14,
        'notify_on_ready': settings.notification.push_enabled,
        'auto_backup': True,
        'backup_interval': 24,
        'backup_count': 10,
        'backup_path': '',
        'compress_backups': True,
        'photo_quality': 85,
        'create_thumbnails': True,
        'window_width': 1280,
        'window_height': 720,
        'window_x': None,
        'window_y': None,
        'show_completed': True,
        'transparency': False,
        'transparency_alpha': 1.0,
        'window_geometry': {},
        'pwa': {
            'port': 5000,
            'auto_start': False,
            'auto_sync': True,
            'sync_interval': 30,
        },
    }


# Legacy compatibility - will be removed in v20.0
warnings.warn(
    "utils.constants is deprecated. "
    "Use 'domain.constants' for business constants and 'config.settings' for app settings. "
    "This module will be removed in version 20.0.",
    DeprecationWarning,
    stacklevel=2
)

DEFAULT_SETTINGS = _get_default_settings()


__all__ = [
    'STATUSES',
    'PRIORITIES',
    'CLIENT_STATUSES',
    'WARRANTIES',
    'DICTIONARY_TYPES',
    'DEFAULT_SETTINGS',
    'DEFAULT_STATUS',
    'DEFAULT_PRIORITY',
]
