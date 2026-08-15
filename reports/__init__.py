#!/usr/bin/env python3

"""Модуль для работы с отчетами и актами"""

import os
import sys

# Добавляем родительскую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reports.report_editor import ReportEditor
from reports.report_renderer import PDFRenderer

__all__ = ["PDFRenderer", "ReportEditor"]
