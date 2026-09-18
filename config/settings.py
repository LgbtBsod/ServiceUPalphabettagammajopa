"""Configuration Management Module
Uses pydantic-settings for robust configuration management (SSOT principle)
Replaces manual .ini/.json parsing with standard best-practice library
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _resource_root() -> Path:
    """Корень для ЧТЕНИЯ бандленных ресурсов (gui/assets, reports/templates).

    Из исходников — корень репозитория. Во frozen (PyInstaller --onefile)
    сборке — sys._MEIPASS, временная папка распаковки текущего запуска."""
    if _frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).parent.parent


def _writable_root() -> Path:
    """Корень для ЗАПИСИ (БД, бэкапы, фото, экспорт, конфиг).

    Раньше все эти пути (DatabaseSettings.path, AppSettings.data_dir/backup_dir,
    get_config_path, BASE_DIR) резолвились через Path(__file__).parent.parent —
    для frozen --onefile сборки (build.py) это тот же
    sys._MEIPASS, который PyInstaller УДАЛЯЕТ при выходе из процесса. Итог:
    БД клиента, бэкапы и сгенерированные акты создавались в эфемерной папке и
    пропадали между запусками (единственное, что уже переживало обновление —
    get_license_key_file(), который явно вынесен в %LOCALAPPDATA%). Теперь
    записываемые пути идут туда же, рядом с .license."""
    if _frozen():
        local_appdata = os.environ.get("LOCALAPPDATA")
        base = Path(local_appdata) / "ServiceUP" if local_appdata else Path(sys.executable).parent
        base.mkdir(parents=True, exist_ok=True)
        return base
    return Path(__file__).parent.parent


def _read_version_file() -> str:
    """version.txt — SSOT версии приложения.

    Раньше AppSettings.version хардкодил "23.0" прямо в поле, а version.txt
    лежал рядом неиспользуемым (разошёлся: файл говорил 23.0, pyproject.toml —
    25.0.0) — ни CI, ни апдейтер не могли свериться с единым источником.
    Теперь version.txt — то, что читает и апдейтер (utils/update_manager.py,
    сверка с тегом релиза), и CI (version.txt должен совпадать с тегом
    перед публикацией). Читаем из _resource_root() (не _writable_root()) —
    это версия ИСПОЛНЯЕМОГО КОДА, бандлится PyInstaller'ом рядом с exe
    (--add-data "version.txt;."), а не пользовательские данные."""
    try:
        text = (_resource_root() / "version.txt").read_text(encoding="utf-8")
        return text.strip().lstrip("vV").strip(". \t\r\n") or "0.0.0"
    except OSError:
        return "0.0.0"


class DatabaseSettings(BaseSettings):
    """Database configuration settings"""

    model_config = SettingsConfigDict(env_prefix="DB_", env_file=".env", extra="ignore")

    path: Path = Field(
        default=Path("data/serviceup.db"), description="Path to SQLite database"
    )
    echo: bool = Field(default=False, description="Echo SQL queries for debugging")
    pool_size: int = Field(default=5, description="Connection pool size")
    max_overflow: int = Field(default=10, description="Max overflow connections")

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str | Path) -> Path:
        """Ensure database directory exists and return absolute Path"""
        db_path = Path(v) if isinstance(v, str) else v
        # Make path absolute relative to the writable root (project root from
        # source, %LOCALAPPDATA%\ServiceUP when frozen — see _writable_root()).
        if not db_path.is_absolute():
            db_path = _writable_root() / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return db_path


class AppSettings(BaseSettings):
    """Application general settings"""

    model_config = SettingsConfigDict(
        env_prefix="APP_", env_file=".env", extra="ignore"
    )

    name: str = Field(default="ServiceUP", description="Application name")
    version: str = Field(
        default_factory=_read_version_file, description="Application version"
    )
    debug: bool = Field(default=False, description="Debug mode")
    language: str = Field(default="ru_RU", description="Default language code")
    data_dir: Path = Field(default=Path("data"), description="Data directory")
    backup_dir: Path = Field(default=Path("backups"), description="Backup directory")
    log_level: str = Field(default="INFO", description="Logging level")
    max_workers: int = Field(default=4, description="Max thread pool workers")

    @field_validator("data_dir", "backup_dir")
    @classmethod
    def validate_dirs(cls, v: str | Path) -> Path:
        """Ensure directories are absolute paths"""
        dir_path = Path(v) if isinstance(v, str) else v
        # Make path absolute relative to the writable root (see _writable_root()).
        if not dir_path.is_absolute():
            dir_path = _writable_root() / dir_path
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v.upper()


class Settings(BaseSettings):
    """Main Settings class - SSOT for all application configuration
    Combines all sub-settings into one unified interface
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # Nested settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    app: AppSettings = Field(default_factory=AppSettings)

    # Direct access shortcuts for common settings
    debug: bool = Field(default=False)
    environment: str = Field(default="development")

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        valid_envs = ["development", "staging", "production"]
        if v.lower() not in valid_envs:
            raise ValueError(f"Invalid environment: {v}. Must be one of {valid_envs}")
        return v.lower()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance (Singleton pattern)
    Uses LRU cache for performance - settings loaded only once
    Thread-safe by default in Python 3.14+

    Returns:
        Settings: Unified settings instance
    """
    return Settings()


def reload_settings() -> Settings:
    """Force reload settings (clears cache)
    Use when .env file changes at runtime

    Returns:
        Settings: Fresh settings instance
    """
    get_settings.cache_clear()
    return get_settings()


# Convenience functions for quick access (DRY principle)
def get_app_name() -> str:
    """Get application name"""
    return get_settings().app.name


def get_version() -> str:
    """Get application version"""
    return get_settings().app.version


def is_debug() -> bool:
    """Check if debug mode is enabled"""
    return get_settings().debug or get_settings().app.debug


def get_db_path() -> Path:
    """Get database path as Path object"""
    return Path(get_settings().database.path)


def get_data_dir() -> Path:
    """Get data directory as Path object"""
    return Path(get_settings().app.data_dir)


def get_backup_dir() -> Path:
    """Get backup directory as Path object"""
    return Path(get_settings().app.backup_dir)


def get_max_workers() -> int:
    """Get max thread pool workers"""
    return get_settings().app.max_workers


def get_default_language() -> str:
    """Get default language code"""
    return get_settings().app.language


# =============================================================================
# PATH HELPERS - SSOT for all directory paths (replaces legacy config.py)
# =============================================================================


def get_reports_dir() -> Path:
    """Get reports directory as Path object"""
    return get_data_dir() / "reports"


def get_templates_dir() -> Path:
    """Get templates directory as Path object"""
    return get_reports_dir() / "templates"


def get_photos_dir() -> Path:
    """Get client photos directory as Path object"""
    return get_data_dir() / "client_photos"


def get_thumbnails_dir() -> Path:
    """Get thumbnails directory as Path object"""
    return get_photos_dir() / "thumbnails"


def get_clients_db_dir() -> Path:
    """Get clients database directory as Path object"""
    return get_data_dir() / "DBClients"


def get_export_dir() -> Path:
    """Get export directory as Path object"""
    return get_data_dir() / "exports"


def get_config_path() -> Path:
    """Get main config file path (absolute).

    Пользовательский (перезаписываемый) файл — не бандленный ресурс, поэтому
    идёт через _writable_root(), а не _resource_root() (см. модульный
    docstring про frozen --onefile и sys._MEIPASS)."""
    return _writable_root() / "service_center.config"


def get_log_dir() -> Path:
    """Get log directory as Path object (writable root, same as backups/config).

    Регрессия (живой отчёт): frozen --windowed сборка на Windows не имеет
    консоли вообще (build.py: `--windowed` на win32) — весь print()/
    logger.error() без файлового handler'а улетает в никуда, и при падении
    на старте (например, Flet не смог поднять локальный веб-сервер)
    пользователь не видит АБСОЛЮТНО ничего, а без лога это невозможно
    диагностировать удалённо. core/logging/logger.py::setup_logging() уже
    умеет писать ротируемый файл — не хватало только пути и самого вызова
    на старте (main.py)."""
    return _writable_root() / "logs"


def get_log_file() -> Path:
    """Get the main application log file path (see get_log_dir())."""
    return get_log_dir() / "serviceup.log"


def get_license_key_file() -> Path:
    """Get license key file path.

    ВНЕ BASE_DIR намеренно (раньше было Path(data_dir).parent / ".license" —
    внутри корня проекта, который в реальной эксплуатации нередко лежит
    внутри OneDrive/Dropbox: облачная синхронизация периодически держит
    файл залоченным, из-за чего запись падала PermissionError — найдено
    живым прогоном main.py, см. AUDIT_REPORT_v25.md). %LOCALAPPDATA%
    специально не роумится/не синхронизируется никаким клиентом облака —
    стандартное место для такого рода файлов состояния приложения на
    Windows. utils/license_manager.py переносит существующий файл из
    старого расположения при первом запуске после обновления."""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "ServiceUP" / ".license"
    # Не Windows / LOCALAPPDATA не выставлен — прежнее поведение как fallback.
    return Path(get_settings().app.data_dir).parent / ".license"


# =============================================================================
# LEGACY COMPATIBILITY ALIASES (DEPRECATED - migrate to new API)
# These maintain backward compatibility with old config.py usage.
# =============================================================================
# Legacy compatibility aliases (DEPRECATED - will be removed in v25.0)
# Will be removed in version 25.0 - update your code to use the new functions above.
# =============================================================================

BASE_DIR: Path = _resource_root()  # корень для бандленных ресурсов (см. модульный docstring)
APP_VERSION: str = get_version()
APP_NAME: str = get_app_name()
DB_PATH: Path = get_db_path()
CONFIG_PATH: Path = get_config_path()
BACKUP_DIR: Path = get_backup_dir()
EXPORT_DIR: Path = get_export_dir()
PHOTOS_DIR: Path = get_photos_dir()
THUMBNAILS_DIR: Path = get_thumbnails_dir()
CLIENTS_DB_DIR: Path = get_clients_db_dir()
REPORTS_DIR: Path = get_reports_dir()
TEMPLATES_DIR: Path = get_templates_dir()


# License secret key - loaded from environment or default
_LICENSE_SECRET_DEFAULT = b"ServiceUP_2024_License_Secret_Key_v1!"
_env_secret = os.getenv("SERVICEUP_LICENSE_SECRET")
LICENSE_SECRET_KEY: bytes = (
    _env_secret.encode() if _env_secret else _LICENSE_SECRET_DEFAULT
)


def ensure_directories() -> None:
    """Create all necessary directories.

    This function ensures all application directories exist.
    Uses pathlib for modern, cross-platform path handling.
    """
    directories = [
        get_backup_dir(),
        get_export_dir(),
        get_photos_dir(),
        get_thumbnails_dir(),
        get_clients_db_dir(),
        get_reports_dir(),
        get_templates_dir(),
        get_log_dir(),
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


# Export public API
__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "BACKUP_DIR",
    # Legacy compatibility (DEPRECATED)
    "BASE_DIR",
    "CLIENTS_DB_DIR",
    "CONFIG_PATH",
    "DB_PATH",
    "EXPORT_DIR",
    "LICENSE_SECRET_KEY",
    "PHOTOS_DIR",
    "REPORTS_DIR",
    "TEMPLATES_DIR",
    "THUMBNAILS_DIR",
    "AppSettings",
    "DatabaseSettings",
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
    "get_log_dir",
    "get_log_file",
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
