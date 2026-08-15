"""Configuration Package - SSOT for all application settings

Centralized configuration management using pydantic-settings (Python 3.14 best practice).
Replaces legacy config.py module with type-safe, validated settings.

Principles applied:
- SSOT (Single Source of Truth): One source for all configuration
- DRY (Don't Repeat Yourself): No duplication of settings
- SOLID: Type-safe, validated configuration objects
"""

from .settings import (
    APP_NAME,
    APP_VERSION,
    BACKUP_DIR,
    BASE_DIR,
    CLIENTS_DB_DIR,
    CONFIG_PATH,
    # Legacy compatibility aliases (deprecated - migrate to new API)
    DB_PATH,
    EXPORT_DIR,
    LICENSE_SECRET_KEY,
    PHOTOS_DIR,
    REPORTS_DIR,
    TEMPLATES_DIR,
    THUMBNAILS_DIR,
    AppSettings,
    DatabaseSettings,
    LicenseSettings,
    NotificationSettings,
    Settings,
    ensure_directories,
    get_app_name,
    get_backup_dir,
    get_clients_db_dir,
    get_config_path,
    get_data_dir,
    get_db_path,
    get_default_language,
    get_export_dir,
    get_license_key_file,
    get_max_workers,
    get_photos_dir,
    # Path helpers - SSOT for directory paths (replaces config.py)
    get_reports_dir,
    get_settings,
    get_templates_dir,
    get_thumbnails_dir,
    get_version,
    is_debug,
    reload_settings,
)

__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "BACKUP_DIR",
    "BASE_DIR",
    "CLIENTS_DB_DIR",
    "CONFIG_PATH",
    # Legacy compatibility (DEPRECATED - will be removed in v20.0)
    "DB_PATH",
    "EXPORT_DIR",
    "LICENSE_SECRET_KEY",
    "PHOTOS_DIR",
    "REPORTS_DIR",
    "TEMPLATES_DIR",
    "THUMBNAILS_DIR",
    "AppSettings",
    "DatabaseSettings",
    "LicenseSettings",
    "NotificationSettings",
    # Core settings classes
    "Settings",
    "ensure_directories",
    "get_app_name",
    "get_backup_dir",
    "get_clients_db_dir",
    "get_config_path",
    "get_data_dir",
    "get_db_path",
    "get_default_language",
    "get_export_dir",
    "get_license_key_file",
    "get_max_workers",
    "get_photos_dir",
    # Path helpers
    "get_reports_dir",
    # Getter functions
    "get_settings",
    "get_templates_dir",
    "get_thumbnails_dir",
    "get_version",
    "is_debug",
    "reload_settings",
]
