#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Менеджеры приложения"""

from .settings import SettingsManager
from .backup import BackupManager
from .integrations import IntegrationManager
from .reports import ReportGenerator
from .photo_manager import PhotoManager

__all__ = ['SettingsManager', 'BackupManager', 'IntegrationManager', 'ReportGenerator', 'PhotoManager']
