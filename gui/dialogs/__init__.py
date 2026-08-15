#!/usr/bin/env python3

"""Диалоговые окна"""

from gui.dialogs.act_preview import ActPreviewWindow
from gui.dialogs.client_history import ClientHistoryWindow
from gui.dialogs.device_form import DeviceFormDialog
from gui.dialogs.dictionaries import DictionariesManagerWindow
from gui.dialogs.photo_viewer import PhotoViewerWindow
from gui.dialogs.settings import SettingsWindow
from gui.dialogs.work_item_dialog import WorkItemDialog

__all__ = [
    "ActPreviewWindow",
    "ClientHistoryWindow",
    "DeviceFormDialog",
    "DictionariesManagerWindow",
    "PhotoViewerWindow",
    "SettingsWindow",
    "WorkItemDialog",
]
