#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Конфигурация приложения"""

import os
import sys

# Версия приложения
APP_VERSION = "15.0"
APP_NAME = "Сервисный центр"
APP_DESCRIPTION = "Учет ремонта техники"

# Секретный ключ для лицензирования (HMAC)
# Используется в utils/license_manager.py и keygen.py
# Критическое исправление безопасности: ключ должен браться из переменных окружения
# В продакшене задавайте через SERVICEUP_LICENSE_SECRET, иначе будет использоваться дефолтное значение
_LICENSE_SECRET_DEFAULT = b'ServiceUP_2024_License_Secret_Key_v1!'
_env_secret = os.getenv("SERVICEUP_LICENSE_SECRET")
LICENSE_SECRET_KEY = _env_secret.encode() if _env_secret else _LICENSE_SECRET_DEFAULT

# Пути
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "service_center.db")
CONFIG_PATH = os.path.join(BASE_DIR, "service_center.config")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
EXPORT_DIR = os.path.join(BASE_DIR, "exports")
PHOTOS_DIR = os.path.join(BASE_DIR, "client_photos")
THUMBNAILS_DIR = os.path.join(PHOTOS_DIR, "thumbnails")
CLIENTS_DB_DIR = os.path.join(BASE_DIR, "DBClients")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
TEMPLATES_DIR = os.path.join(REPORTS_DIR, "templates")


def ensure_directories():
    """Создание необходимых директорий.
    
    Выносится в отдельную функцию для устранения side effects при импорте.
    """
    for directory in [BACKUP_DIR, EXPORT_DIR, PHOTOS_DIR, THUMBNAILS_DIR, CLIENTS_DB_DIR, REPORTS_DIR, TEMPLATES_DIR]:
        os.makedirs(directory, exist_ok=True)
