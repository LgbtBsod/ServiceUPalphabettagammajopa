"""
Configuration Management Module
Uses pydantic-settings for robust configuration management (SSOT principle)
Replaces manual .ini/.json parsing with standard best-practice library
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Optional, List
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database configuration settings"""
    
    model_config = SettingsConfigDict(env_prefix="DB_", env_file=".env", extra='ignore')
    
    path: str = Field(default="data/serviceup.db", description="Path to SQLite database")
    echo: bool = Field(default=False, description="Echo SQL queries for debugging")
    pool_size: int = Field(default=5, description="Connection pool size")
    max_overflow: int = Field(default=10, description="Max overflow connections")
    
    @field_validator('path')
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Ensure database directory exists"""
        db_path = Path(v)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return str(db_path)


class AppSettings(BaseSettings):
    """Application general settings"""
    
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra='ignore')
    
    name: str = Field(default="ServiceUP", description="Application name")
    version: str = Field(default="20.0.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode")
    language: str = Field(default="ru_RU", description="Default language code")
    data_dir: str = Field(default="data", description="Data directory")
    backup_dir: str = Field(default="backups", description="Backup directory")
    log_level: str = Field(default="INFO", description="Logging level")
    max_workers: int = Field(default=4, description="Max thread pool workers")
    
    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v.upper()


class LicenseSettings(BaseSettings):
    """License configuration settings"""
    
    model_config = SettingsConfigDict(env_prefix="LIC_", env_file=".env", extra='ignore')
    
    key_file: str = Field(default="license.key", description="License key file path")
    hmac_secret: str = Field(default="change_this_secret_key_in_production", description="HMAC secret for license validation")
    trial_days: int = Field(default=14, description="Trial period in days")


class NotificationSettings(BaseSettings):
    """Notification service settings"""
    
    model_config = SettingsConfigDict(env_prefix="NOTIF_", env_file=".env", extra='ignore')
    
    sms_enabled: bool = Field(default=False, description="Enable SMS notifications")
    email_enabled: bool = Field(default=False, description="Enable email notifications")
    telegram_enabled: bool = Field(default=False, description="Enable Telegram notifications")
    push_enabled: bool = Field(default=False, description="Enable push notifications")
    
    # SMTP settings
    smtp_host: Optional[str] = Field(default=None, description="SMTP server host")
    smtp_port: int = Field(default=587, description="SMTP server port")
    smtp_user: Optional[str] = Field(default=None, description="SMTP username")
    smtp_password: Optional[str] = Field(default=None, description="SMTP password")
    
    # Telegram settings
    telegram_bot_token: Optional[str] = Field(default=None, description="Telegram bot token")
    telegram_chat_id: Optional[str] = Field(default=None, description="Telegram chat ID")


class Settings(BaseSettings):
    """
    Main Settings class - SSOT for all application configuration
    Combines all sub-settings into one unified interface
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra='ignore'
    )
    
    # Nested settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    app: AppSettings = Field(default_factory=AppSettings)
    license: LicenseSettings = Field(default_factory=LicenseSettings)
    notification: NotificationSettings = Field(default_factory=NotificationSettings)
    
    # Direct access shortcuts for common settings
    debug: bool = Field(default=False)
    environment: str = Field(default="development")
    
    @field_validator('environment')
    @classmethod
    def validate_environment(cls, v: str) -> str:
        valid_envs = ["development", "staging", "production"]
        if v.lower() not in valid_envs:
            raise ValueError(f"Invalid environment: {v}. Must be one of {valid_envs}")
        return v.lower()


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance (Singleton pattern)
    Uses LRU cache for performance - settings loaded only once
    Thread-safe by default in Python 3.14+
    
    Returns:
        Settings: Unified settings instance
    """
    return Settings()


def reload_settings() -> Settings:
    """
    Force reload settings (clears cache)
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


def get_db_path() -> str:
    """Get database path"""
    return get_settings().database.path


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


# Export public API
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
