"""
Configuration Package - SSOT for all application settings

Centralized configuration management using pydantic-settings (Python 3.14 best practice).
Replaces legacy config.py module with type-safe, validated settings.

Principles applied:
- SSOT (Single Source of Truth): One source for all configuration
- DRY (Don't Repeat Yourself): No duplication of settings
- SOLID: Type-safe, validated configuration objects
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
    # Path helpers - SSOT for directory paths (replaces config.py)
    get_reports_dir,
    get_templates_dir,
    get_photos_dir,
    get_thumbnails_dir,
    get_clients_db_dir,
    get_export_dir,
    get_config_path,
    get_license_key_file,
    # Legacy compatibility aliases (deprecated - migrate to new API)
    DB_PATH,
    CONFIG_PATH,
    BACKUP_DIR,
    EXPORT_DIR,
    PHOTOS_DIR,
    THUMBNAILS_DIR,
    CLIENTS_DB_DIR,
    REPORTS_DIR,
    TEMPLATES_DIR,
    BASE_DIR,
    APP_VERSION,
    APP_NAME,
    LICENSE_SECRET_KEY,
    ensure_directories,
)

__all__ = [
    # Core settings classes
    'Settings',
    'DatabaseSettings',
    'AppSettings',
    'LicenseSettings',
    'NotificationSettings',
    # Getter functions
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
    # Path helpers
    'get_reports_dir',
    'get_templates_dir',
    'get_photos_dir',
    'get_thumbnails_dir',
    'get_clients_db_dir',
    'get_export_dir',
    'get_config_path',
    'get_license_key_file',
    # Legacy compatibility (DEPRECATED - will be removed in v20.0)
    'DB_PATH',
    'CONFIG_PATH',
    'BACKUP_DIR',
    'EXPORT_DIR',
    'PHOTOS_DIR',
    'THUMBNAILS_DIR',
    'CLIENTS_DB_DIR',
    'REPORTS_DIR',
    'TEMPLATES_DIR',
    'BASE_DIR',
    'APP_VERSION',
    'APP_NAME',
    'LICENSE_SECRET_KEY',
    'ensure_directories',
]
