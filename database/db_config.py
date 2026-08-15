#!/usr/bin/env python3
"""Конфигурация базы данных.

Поддержка различных СУБД через единую конфигурацию.
Для смены БД достаточно изменить DATABASE_CONFIG в settings.json или env переменные.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum


class DatabaseType(StrEnum):
    """Типы поддерживаемых СУБД."""

    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"


@dataclass
class DatabaseConfig:
    """Конфигурация подключения к базе данных.

    Примеры использования:

    SQLite (по умолчанию):
        db_type = sqlite
        database = service_center.db

    PostgreSQL:
        db_type = postgresql
        host = localhost
        port = 5432
        database = service_center
        user = postgres
        password = secret

    MySQL:
        db_type = mysql
        host = localhost
        port = 3306
        database = service_center
        user = root
        password = secret
    """

    db_type: DatabaseType = DatabaseType.SQLITE
    database: str = "service_center.db"
    host: str | None = None
    port: int | None = None
    user: str | None = None
    password: str | None = None
    pool_size: int = 5
    echo: bool = False  # Логирование SQL запросов

    @classmethod
    def from_env(cls) -> DatabaseConfig:
        """Создание конфигурации из переменных окружения."""
        return cls(
            db_type=DatabaseType(os.getenv("DB_TYPE", "sqlite")),
            database=os.getenv("DB_NAME", "service_center.db"),
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", "0")) or None,
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
            echo=os.getenv("DB_ECHO", "false").lower() == "true",
        )

    @classmethod
    def from_dict(cls, data: dict) -> DatabaseConfig:
        """Создание конфигурации из словаря."""
        return cls(
            db_type=DatabaseType(data.get("db_type", "sqlite")),
            database=data.get("database", "service_center.db"),
            host=data.get("host"),
            port=data.get("port"),
            user=data.get("user"),
            password=data.get("password"),
            pool_size=data.get("pool_size", 5),
            echo=data.get("echo", False),
        )

    def to_dict(self) -> dict:
        """Преобразование в словарь."""
        return {
            "db_type": self.db_type.value,
            "database": self.database,
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "pool_size": self.pool_size,
            "echo": self.echo,
        }

    def get_connection_string(self) -> str:
        """Получение строки подключения.

        Returns:
            Строка подключения в формате SQLAlchemy URL.
        """
        if self.db_type == DatabaseType.SQLITE:
            return f"sqlite:///{self.database}"

        if self.db_type == DatabaseType.POSTGRESQL:
            driver = "postgresql+psycopg2"
            return f"{driver}://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

        if self.db_type == DatabaseType.MYSQL:
            driver = "mysql+pymysql"
            return f"{driver}://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

        raise ValueError(f"Неподдерживаемый тип БД: {self.db_type}")

    @property
    def is_sqlite(self) -> bool:
        """Проверка на SQLite."""
        return self.db_type == DatabaseType.SQLITE

    @property
    def is_postgresql(self) -> bool:
        """Проверка на PostgreSQL."""
        return self.db_type == DatabaseType.POSTGRESQL

    @property
    def is_mysql(self) -> bool:
        """Проверка на MySQL."""
        return self.db_type == DatabaseType.MYSQL


# Конфигурация по умолчанию
DEFAULT_DB_CONFIG = DatabaseConfig()


def get_db_config() -> DatabaseConfig:
    """Получение конфигурации БД.

    Приоритет:
    1. Переменные окружения
    2. Значения по умолчанию

    Returns:
        DatabaseConfig: Конфигурация подключения.
    """
    # Проверяем переменные окружения
    if os.getenv("DB_TYPE"):
        return DatabaseConfig.from_env()

    return DEFAULT_DB_CONFIG
