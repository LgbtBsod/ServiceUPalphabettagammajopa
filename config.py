#!/usr/bin/env python3

"""Конфигурация приложения v23.0"""

import os
from pathlib import Path

# Версия приложения
APP_VERSION = "23.0"
APP_NAME = "Сервисный центр"
APP_DESCRIPTION = "Учет ремонта техники"

# Секретный ключ для лицензирования (HMAC)
# Используется в utils/license_manager.py и keygen.py
# Критическое исправление безопасности: ключ должен браться из переменных окружения
# В продакшене задавайте через SERVICEUP_LICENSE_SECRET, иначе будет использоваться дефолтное значение
_LICENSE_SECRET_DEFAULT = b"ServiceUP_2024_License_Secret_Key_v1!"
_env_secret = os.getenv("SERVICEUP_LICENSE_SECRET")
LICENSE_SECRET_KEY = _env_secret.encode() if _env_secret else _LICENSE_SECRET_DEFAULT

# Пути (используем pathlib для современной работы с путями)
# Сначала делаем resolve для __file__, чтобы гарантировать абсолютный путь
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = str(BASE_DIR / "service_center.db")
CONFIG_PATH = str(BASE_DIR / "service_center.config")
BACKUP_DIR = str(BASE_DIR / "backups")
EXPORT_DIR = str(BASE_DIR / "exports")
PHOTOS_DIR = str(BASE_DIR / "client_photos")
THUMBNAILS_DIR = str(BASE_DIR / "client_photos" / "thumbnails")
CLIENTS_DB_DIR = str(BASE_DIR / "DBClients")
REPORTS_DIR = str(BASE_DIR / "reports")
TEMPLATES_DIR = str(BASE_DIR / "reports" / "templates")


def ensure_directories():
    """Создание необходимых директорий.

    Выносится в отдельную функцию для устранения side effects при импорте.
    """
    for directory in [
        BACKUP_DIR,
        EXPORT_DIR,
        PHOTOS_DIR,
        THUMBNAILS_DIR,
        CLIENTS_DB_DIR,
        REPORTS_DIR,
        TEMPLATES_DIR,
    ]:
        directory.mkdir(parents=True, exist_ok=True)
