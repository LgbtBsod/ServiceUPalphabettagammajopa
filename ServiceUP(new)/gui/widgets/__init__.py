#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Виджеты для интерфейса"""

from gui.widgets.modern import (
    ModernCard, ModernButton, ModernEntry, ModernLabel, 
    ModernCombobox, ModernTextbox, ModernCheckbox, ModernSwitch
)
from gui.widgets.thumbnail import ThumbnailWidget
from gui.widgets.dashboard import PremiumDashboard
from gui.widgets.work_table import WorkItemsTable

__all__ = [
    'ModernCard', 'ModernButton', 'ModernEntry', 'ModernLabel',
    'ModernCombobox', 'ModernTextbox', 'ModernCheckbox', 'ModernSwitch',
    'ThumbnailWidget', 'PremiumDashboard', 'WorkItemsTable'
]
