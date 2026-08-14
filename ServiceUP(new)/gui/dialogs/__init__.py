#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Диалоговые окна"""

from gui.dialogs.work_item_dialog import WorkItemDialog
from gui.dialogs.device_form import DeviceFormDialog
from gui.dialogs.client_history import ClientHistoryWindow
from gui.dialogs.photo_viewer import PhotoViewerWindow
from gui.dialogs.act_preview import ActPreviewWindow
from gui.dialogs.settings import SettingsWindow
from gui.dialogs.dictionaries import DictionariesManagerWindow

__all__ = [
    'WorkItemDialog', 'DeviceFormDialog', 'ClientHistoryWindow',
    'PhotoViewerWindow', 'ActPreviewWindow', 'SettingsWindow', 'DictionariesManagerWindow'
]
