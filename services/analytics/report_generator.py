"""Report Generator - Strategy Pattern for Export Formats"""

import logging
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class ExportStrategy(Protocol):
    """Protocol for export strategies (Strategy Pattern)"""

    def export(self, data: list[dict[str, Any]], file_path: Path) -> Path:
        """Export data to file"""
        ...


class PDFExportStrategy:
    """PDF export strategy"""

    def export(self, data: list[dict[str, Any]], file_path: Path) -> Path:
        """Export to PDF using reportlab or similar"""
        try:
            from reports.report_renderer import PDFRenderer

            renderer = PDFRenderer()
            renderer.render_report(str(file_path), data, "summary")
            logger.info(f"PDF report created: {file_path}")
            return file_path
        except Exception as e:
            logger.exception(f"PDF export failed: {e}")
            raise


class ExcelExportStrategy:
    """Excel export strategy using openpyxl"""

    def export(self, data: list[dict[str, Any]], file_path: Path) -> Path:
        """Export to Excel"""
        try:
            from openpyxl import Workbook

            wb = Workbook()
            ws = wb.active
            ws.title = "Report"

            if not data:
                wb.save(str(file_path))
                return file_path

            # Headers
            headers = list(data[0].keys())
            ws.append(headers)

            # Data rows
            for row in data:
                ws.append([row.get(h) for h in headers])

            wb.save(str(file_path))
            logger.info(f"Excel report created: {file_path}")
            return file_path
        except ImportError:
            logger.warning("openpyxl not installed, falling back to CSV")
            return CSVExportStrategy().export(data, file_path.with_suffix(".csv"))


class CSVExportStrategy:
    """CSV export strategy (fallback)"""

    def export(self, data: list[dict[str, Any]], file_path: Path) -> Path:
        """Export to CSV"""
        import csv

        with open(file_path, "w", encoding="utf-8", newline="") as f:
            if not data:
                return file_path

            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)

        logger.info(f"CSV report created: {file_path}")
        return file_path


class ReportGenerator:
    """Report generator with pluggable export strategies.

    Features:
    - Strategy pattern for format selection
    - Automatic fallback to CSV
    - Period-based report generation
    """

    def __init__(self):
        self.strategies: dict[str, ExportStrategy] = {
            "pdf": PDFExportStrategy(),
            "excel": ExcelExportStrategy(),
            "csv": CSVExportStrategy(),
        }

    def generate_report(
        self,
        data: list[dict[str, Any]],
        output_dir: Path,
        report_type: str = "pdf",
        filename_prefix: str = "report",
    ) -> Path:
        """Generate report in specified format.

        Args:
            data: Report data
            output_dir: Directory to save report
            report_type: Format type (pdf, excel, csv)
            filename_prefix: Prefix for filename

        Returns:
            Path to generated report
        """
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_prefix}_{timestamp}"

        strategy = self.strategies.get(report_type.lower(), self.strategies["csv"])
        file_path = output_dir / f"{filename}.{report_type.lower()}"

        output_dir.mkdir(parents=True, exist_ok=True)

        return strategy.export(data, file_path)
