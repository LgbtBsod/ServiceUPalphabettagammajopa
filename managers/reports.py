#!/usr/bin/env python3

"""Генератор отчетов и актов - делегирует логику в ReportRenderer"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from config import REPORTS_DIR
from reports.report_renderer import ActPDFGenerator

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Класс для генерации отчетов и актов - тонкая обертка над ActPDFRenderer"""

    def __init__(self):
        self.reports_dir = Path(REPORTS_DIR)
        self.create_reports_directory()
        self.pdf_generator = ActPDFGenerator()

    def create_reports_directory(self):
        """Создание директории для отчетов"""
        try:
            if not self.reports_dir.exists():
                self.reports_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Ошибка создания директории: {e}", exc_info=True)
            self.reports_dir = Path(".")

    def generate_receipt_act(self, device: dict[str, Any]) -> str | None:
        """Генерация акта приема - теперь только PDF через ReportRenderer"""
        try:
            order_number = str(device.get("order_number", "")).strip()
            safe_order = "".join(
                c for c in order_number if c.isalnum() or c in ("-", "_")
            )
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self.reports_dir / f"receipt_act_{safe_order}_{timestamp}.pdf"

            success = self.pdf_generator.generate_receipt_pdf(str(filename), device)
            if success:
                logger.info(f"Создан акт приема: {filename}")
                return str(filename)
            else:
                logger.error(f"Не удалось создать акт приема: {filename}")
                return None
        except Exception as e:
            logger.error(f"Ошибка создания акта приема: {e}", exc_info=True)
            return None

    def generate_completion_act(self, device: dict[str, Any]) -> str | None:
        """Генерация акта выполненных работ - теперь только PDF через ReportRenderer"""
        try:
            order_number = str(device.get("order_number", "")).strip()
            safe_order = "".join(
                c for c in order_number if c.isalnum() or c in ("-", "_")
            )
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self.reports_dir / f"completion_act_{safe_order}_{timestamp}.pdf"

            success = self.pdf_generator.generate_completion_pdf(str(filename), device)
            if success:
                logger.info(f"Создан акт выполненных работ: {filename}")
                return str(filename)
            else:
                logger.error(f"Не удалось создать акт выполненных работ: {filename}")
                return None
        except Exception as e:
            logger.error(f"Ошибка создания акта выполненных работ: {e}", exc_info=True)
            return None
