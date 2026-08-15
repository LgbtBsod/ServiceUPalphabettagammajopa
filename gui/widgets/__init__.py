#!/usr/bin/env python3

"""Виджеты для интерфейса"""

from gui.widgets.dashboard import PremiumDashboard
from gui.widgets.modern import (
    ModernButton,
    ModernCard,
    ModernCheckbox,
    ModernCombobox,
    ModernEntry,
    ModernLabel,
    ModernSwitch,
    ModernTextbox,
)
from gui.widgets.thumbnail import ThumbnailWidget
from gui.widgets.work_table import WorkItemsTable

__all__ = [
    "ModernButton",
    "ModernCard",
    "ModernCheckbox",
    "ModernCombobox",
    "ModernEntry",
    "ModernLabel",
    "ModernSwitch",
    "ModernTextbox",
    "PremiumDashboard",
    "ThumbnailWidget",
    "WorkItemsTable",
]
