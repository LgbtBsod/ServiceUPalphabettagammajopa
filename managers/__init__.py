#!/usr/bin/env python3

"""Менеджеры приложения"""

from .backup import BackupManager
from .integrations import IntegrationManager
from .photo_manager import PhotoManager
from .reports import ReportGenerator
from .settings import SettingsManager

__all__ = [
    "BackupManager",
    "IntegrationManager",
    "PhotoManager",
    "ReportGenerator",
    "SettingsManager",
]
