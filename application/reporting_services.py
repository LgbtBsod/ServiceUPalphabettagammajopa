"""Reporting Application Services - Use Cases для генерации отчетов.

Следует принципам:
- SRP: каждый метод решает одну задачу
- Strategy Pattern: разные стратегии генерации отчетов
- Multi-threading: параллельная генерация отчетов
"""

from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol

from shared.kernel import UnitOfWork

logger = logging.getLogger(__name__)


class UnitOfWorkFactory(Protocol):
    """Протокол фабрики Unit of Work."""

    def __call__(self) -> UnitOfWork: ...


@dataclass(slots=True)
class ReportResult:
    """Результат генерации отчета."""

    report_id: str
    file_path: str
    success: bool
    message: str = ""
    generated_at: datetime = None

    def __post_init__(self):
        if self.generated_at is None:
            object.__setattr__(self, "generated_at", datetime.now())


@dataclass(slots=True)
class DashboardData:
    """Данные для дашборда."""

    total_orders_today: int
    total_revenue_today: float
    orders_in_progress: int
    ready_orders: int
    revenue_by_status: dict[str, float]
    top_clients: list[dict[str, Any]]


class ReportingService:
    """Сервис приложения для генерации отчетов и статистики.

    Поддерживает:
    - PDF отчеты (акты, квитанции)
    - Excel экспорт
    - Дашборд статистика
    - Асинхронная генерация
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        export_dir: str,
        max_workers: int = 2,
    ):
        self._uow_factory = uow_factory
        self._export_dir = Path(export_dir)
        self._export_dir.mkdir(parents=True, exist_ok=True)
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def get_dashboard_data(self) -> DashboardData:
        """Получение данных для дашборда (Query).

        Returns:
            Актуальные метрики для отображения на дашборде.
        """
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        with self._uow_factory() as uow:
            stats = uow.devices.get_dashboard_stats(today_start)

            return DashboardData(
                total_orders_today=stats.get("orders_today", 0),
                total_revenue_today=float(stats.get("revenue_today", 0)),
                orders_in_progress=stats.get("in_progress", 0),
                ready_orders=stats.get("ready", 0),
                revenue_by_status=stats.get("revenue_by_status", {}),
                top_clients=stats.get("top_clients", []),
            )

    def generate_period_report(
        self,
        date_from: date,
        date_to: date,
        report_type: str = "summary",
    ) -> Future[ReportResult]:
        """Асинхронная генерация периодического отчета (Command).

        Args:
            date_from: Дата начала периода.
            date_to: Дата окончания периода.
            report_type: Тип отчета (summary, detailed, financial).

        Returns:
            Future с результатом генерации.
        """
        return self._executor.submit(
            self._generate_report_sync,
            date_from,
            date_to,
            report_type,
        )

    def _generate_report_sync(
        self,
        date_from: date,
        date_to: date,
        report_type: str,
    ) -> ReportResult:
        """Синхронная генерация отчета (внутренний метод)."""
        try:
            report_id = f"RPT_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            with self._uow_factory() as uow:
                # Получение данных для отчета
                orders = uow.devices.get_orders_by_date_range(date_from, date_to)

                # Генерация файла в зависимости от типа
                if report_type == "excel":
                    file_path = self._generate_excel_report(report_id, orders)
                else:
                    file_path = self._generate_pdf_report(
                        report_id, orders, report_type
                    )

                return ReportResult(
                    report_id=report_id,
                    file_path=str(file_path),
                    success=True,
                )

        except Exception as e:
            logger.error(f"Ошибка генерации отчета: {e}", exc_info=True)
            return ReportResult(
                report_id="",
                file_path="",
                success=False,
                message=str(e),
            )

    def _generate_pdf_report(
        self,
        report_id: str,
        orders: list[dict[str, Any]],
        report_type: str,
    ) -> Path:
        """Генерация PDF отчета."""
        from reports.report_renderer import PDFRenderer

        filename = f"{report_id}_{report_type}.pdf"
        file_path = self._export_dir / filename

        renderer = PDFRenderer()
        renderer.render_report(str(file_path), orders, report_type)

        logger.info(f"PDF отчет создан: {file_path}")
        return file_path

    def _generate_excel_report(
        self,
        report_id: str,
        orders: list[dict[str, Any]],
    ) -> Path:
        """Генерация Excel отчета."""
        try:
            from openpyxl import Workbook

            filename = f"{report_id}_export.xlsx"
            file_path = self._export_dir / filename

            wb = Workbook()
            ws = wb.active
            ws.title = "Заказы"

            # Заголовки
            headers = ["ID", "Номер", "Клиент", "Устройство", "Статус", "Сумма", "Дата"]
            ws.append(headers)

            # Данные
            for order in orders:
                ws.append(
                    [
                        order.get("id"),
                        order.get("order_number"),
                        order.get("client_name"),
                        order.get("device_name"),
                        order.get("status"),
                        order.get("total_amount", 0),
                        order.get("receipt_date"),
                    ]
                )

            wb.save(str(file_path))
            logger.info(f"Excel отчет создан: {file_path}")
            return file_path

        except ImportError:
            logger.warning("openpyxl не установлен, экспортируем в CSV")
            return self._generate_csv_report(report_id, orders)

    def _generate_csv_report(
        self,
        report_id: str,
        orders: list[dict[str, Any]],
    ) -> Path:
        """Генерация CSV отчета (fallback)."""
        import csv

        filename = f"{report_id}_export.csv"
        file_path = self._export_dir / filename

        with open(file_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["ID", "Номер", "Клиент", "Устройство", "Статус", "Сумма", "Дата"]
            )

            for order in orders:
                writer.writerow(
                    [
                        order.get("id"),
                        order.get("order_number"),
                        order.get("client_name"),
                        order.get("device_name"),
                        order.get("status"),
                        order.get("total_amount", 0),
                        order.get("receipt_date"),
                    ]
                )

        logger.info(f"CSV отчет создан: {file_path}")
        return file_path

    def export_order_act(self, order_id: int) -> Path | None:
        """Экспорт акта выполненных работ для заказа.

        Args:
            order_id: ID заказа.

        Returns:
            Путь к файлу акта или None при ошибке.
        """
        with self._uow_factory() as uow:
            order = uow.devices.get_by_id(order_id)
            if not order:
                logger.warning(f"Заказ {order_id} не найден")
                return None

            # Генерация акта через существующий сервис
            from reports.report_editor import ReportEditor

            editor = ReportEditor()
            act_data = editor.generate_act(order)

            filename = f"ACT_{order.get('order_number')}.pdf"
            file_path = self._export_dir / filename

            # Сохранение
            with open(file_path, "wb") as f:
                f.write(act_data)

            logger.info(f"Акт создан: {file_path}")
            return file_path

    def shutdown(self) -> None:
        """Корректное завершение работы сервиса."""
        self._executor.shutdown(wait=True)
