"""Analytics Service - Business Intelligence Layer"""

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Protocol

from .dashboard_metrics import DashboardMetrics
from .report_generator import ReportGenerator

logger = logging.getLogger(__name__)


class AnalyticsRepository(Protocol):
    """Protocol for analytics data access (Repository Pattern)"""

    def get_orders_by_date_range(
        self, date_from: date, date_to: date
    ) -> list[dict[str, Any]]:
        """Get orders within date range"""
        ...

    def get_dashboard_stats(self, today_start: Any) -> dict[str, Any]:
        """Get aggregated dashboard statistics"""
        ...

    def get_revenue_by_status(self, date_from: date, date_to: date) -> dict[str, float]:
        """Get revenue breakdown by order status"""
        ...

    def get_top_clients(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get top clients by revenue"""
        ...


class AnalyticsService:
    """Analytics service for business intelligence.

    Responsibilities:
    - Calculate dashboard metrics
    - Generate period reports
    - Trend analysis
    - Data aggregation

    Dependencies:
    - AnalyticsRepository (abstraction)
    - ReportGenerator (strategy pattern)
    """

    def __init__(
        self,
        repository: AnalyticsRepository,
        export_dir: str | None = None,
    ):
        self._repository = repository
        self._export_dir = Path(export_dir) if export_dir else Path.cwd() / "exports"
        self._export_dir.mkdir(parents=True, exist_ok=True)
        self._report_generator = ReportGenerator()

    def get_dashboard_metrics(self) -> DashboardMetrics:
        """Get current dashboard metrics.

        Returns:
            DashboardMetrics with aggregated data
        """
        from datetime import datetime

        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        try:
            stats = self._repository.get_dashboard_stats(today_start)

            return DashboardMetrics(
                total_orders_today=stats.get("orders_today", 0),
                total_revenue_today=float(stats.get("revenue_today", 0)),
                orders_in_progress=stats.get("in_progress", 0),
                ready_orders=stats.get("ready", 0),
                revenue_by_status=stats.get("revenue_by_status", {}),
                top_clients=stats.get("top_clients", []),
                period_start=today_start,
                period_end=datetime.now(),
            )
        except Exception as e:
            logger.exception(f"Failed to get dashboard metrics: {e}")
            return DashboardMetrics()

    def generate_period_report(
        self,
        date_from: date,
        date_to: date,
        report_type: str = "pdf",
        filename_prefix: str = "period_report",
    ) -> Path:
        """Generate report for specified period.

        Args:
            date_from: Start date
            date_to: End date
            report_type: Export format (pdf, excel, csv)
            filename_prefix: Filename prefix

        Returns:
            Path to generated report file
        """
        try:
            data = self._repository.get_orders_by_date_range(date_from, date_to)

            return self._report_generator.generate_report(
                data=data,
                output_dir=self._export_dir,
                report_type=report_type,
                filename_prefix=filename_prefix,
            )
        except Exception as e:
            logger.exception(f"Failed to generate period report: {e}")
            raise

    def get_revenue_trend(
        self,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Get revenue trend for last N days.

        Args:
            days: Number of days to analyze

        Returns:
            List of daily revenue data points
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        try:
            revenue_by_status = self._repository.get_revenue_by_status(
                start_date, end_date
            )

            # Simplified trend calculation
            total_revenue = sum(revenue_by_status.values())
            avg_daily = total_revenue / days if days > 0 else 0

            return [
                {
                    "date": (start_date + timedelta(days=i)).isoformat(),
                    "revenue": avg_daily,
                }
                for i in range(days)
            ]
        except Exception as e:
            logger.exception(f"Failed to calculate revenue trend: {e}")
            return []

    def get_client_analytics(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get client analytics data.

        Args:
            limit: Number of top clients to return

        Returns:
            List of client analytics data
        """
        try:
            return self._repository.get_top_clients(limit)
        except Exception as e:
            logger.exception(f"Failed to get client analytics: {e}")
            return []
