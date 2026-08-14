"""
Configuration Package
Centralized configuration management using pydantic-settings
"""

from .settings import (
    Settings,
    DatabaseSettings,
    AppSettings,
    LicenseSettings,
    NotificationSettings,
    get_settings,
    reload_settings,
    get_app_name,
    get_version,
    is_debug,
    get_db_path,
    get_data_dir,
    get_backup_dir,
    get_max_workers,
    get_default_language,
)

__all__ = [
    'Settings',
    'DatabaseSettings',
    'AppSettings',
    'LicenseSettings',
    'NotificationSettings',
    'get_settings',
    'reload_settings',
    'get_app_name',
    'get_version',
    'is_debug',
    'get_db_path',
    'get_data_dir',
    'get_backup_dir',
    'get_max_workers',
    'get_default_language',
]
