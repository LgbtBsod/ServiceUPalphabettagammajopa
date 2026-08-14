"""
Analytics Service - Business Intelligence & Reporting

SRP: Handles data aggregation, metrics calculation, and report generation.
Supports: Dashboard metrics, trend analysis, export to various formats.

Uses Repository Pattern for data access.
Uses Strategy Pattern for different export formats.
"""

from .analytics_service import AnalyticsService
from .dashboard_metrics import DashboardMetrics
from .report_generator import ReportGenerator

__all__ = [
    'AnalyticsService',
    'DashboardMetrics',
    'ReportGenerator',
]
