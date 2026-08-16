#!/usr/bin/env python3

"""Менеджеры приложения"""

from .analytics import AnalyticsRequest, AnalyticsResult, AnalyticsService
from .backup import BackupManager
from .integrations import IntegrationManager
from .locking import LockManager, LockResult
from .photo_manager import PhotoManager
from .reports import ReportGenerator
from .settings import SettingsManager

__all__ = [
    "AnalyticsRequest",
    "AnalyticsResult",
    "AnalyticsService",
    "BackupManager",
    "IntegrationManager",
    "LockManager",
    "LockResult",
    "PhotoManager",
    "ReportGenerator",
    "SettingsManager",
]
