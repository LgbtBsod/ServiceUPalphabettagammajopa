#!/usr/bin/env python3

"""Модуль для работы с отчетами и актами.

Ленивый ре-экспорт (PEP 562). ``ReportEditor`` — это customtkinter-окно, оно
тянет ``gui.widgets.modern`` -> весь пакет ``gui`` -> ... -> ``managers``.
Раньше ``reports/__init__.py`` импортировал его на уровне модуля, из-за чего
``from reports.report_renderer import ActPDFGenerator`` (в ``managers/reports.py``,
и он GUI не требует) при первом импорте протаскивал весь ``gui`` и падал
циклическим импортом, когда ``managers`` инициализировался раньше ``gui``
(``bootstrap.initialize_kernel()`` -> ``from managers import ...``). Теперь
``report_editor`` подгружается только при реальном обращении к
``reports.ReportEditor`` — цепочка managers -> reports больше не касается gui.
Прямой импорт ``from reports.report_editor import ReportEditor`` по-прежнему
работает и используется в gui-коде.
"""

import os
import sys
from typing import Any

# Добавляем родительскую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reports.report_renderer import PDFRenderer

__all__ = ["PDFRenderer", "ReportEditor"]


def __getattr__(name: str) -> Any:
    if name == "ReportEditor":
        from reports.report_editor import ReportEditor

        return ReportEditor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
