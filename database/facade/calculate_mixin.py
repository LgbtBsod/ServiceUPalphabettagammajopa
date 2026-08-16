#!/usr/bin/env python3
"""CalculateMixin — Calculation Offloading: тяжёлые агрегации на стороне
SQL вместо питоновских циклов (see AUDIT_REPORT_v25.md, Task T)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from database.facade.shared import OVERDUE_THRESHOLD_DAYS, device_to_row
from database.sqlalchemy_models import Device as DeviceModel
from domain.constants import CLOSED_STATUSES as _CLOSED_STATUSES


class CalculateMixin:
    """Требует self._session() и self.get_statistics() (DevicesMixin) от
    финального класса Database."""

    def _calculation_handlers(self) -> dict[str, Any]:
        """SSOT для имён вычислений: и calculate(), и list_calculations()
        читают ОДИН и тот же словарь — раньше managers/analytics.py::_REPORTS
        дублировал этот список руками, без способа проверить, что оба списка
        не разошлись (см. AUDIT_REPORT_v25.md, Task P: 'найдено:
        _REPORTS дублирует calculate()-whitelist без интроспекции'). Метод,
        а не атрибут класса — хендлеры это bound-методы self."""
        return {
            "overdue_count": self._calc_overdue_count,
            "overdue_orders": self._calc_overdue_orders,
            "dashboard_stats": self._calc_dashboard_stats,
            "status_breakdown": self._calc_status_breakdown,
            "priority_breakdown": self._calc_priority_breakdown,
        }

    def list_calculations(self) -> list[str]:
        """Имена, которые calculate() готов принять — интроспекция вместо
        того, чтобы вызывающий код (managers/analytics.py) держал свой
        отдельный список и надеялся, что он не разойдётся с этим."""
        return sorted(self._calculation_handlers())

    def calculate(self, name: str, **params: Any) -> Any:
        """Тяжёлые агрегации на стороне SQL вместо питоновских циклов.

        Поддерживаемые name — см. list_calculations(). Основа для
        managers.analytics — отдельный модуль, который строит
        параметризированные запросы к db_access ТОЛЬКО через ядро (не
        держит своего движка БД), см. managers/analytics.py.
        """
        handler = self._calculation_handlers().get(name)
        if handler is None:
            raise ValueError(f"Неизвестное вычисление: {name!r}")
        return handler(**params)

    def _calc_status_breakdown(self) -> list[dict[str, Any]]:
        """Количество устройств по каждому статусу — GROUP BY на стороне SQL."""
        with self._session() as s:
            rows = s.execute(
                select(DeviceModel.status, func.count(DeviceModel.id))
                .group_by(DeviceModel.status)
                .order_by(func.count(DeviceModel.id).desc())
            ).all()
            return [{"status": status, "count": count} for status, count in rows]

    def _calc_priority_breakdown(self) -> list[dict[str, Any]]:
        """Количество устройств по каждому приоритету — GROUP BY на стороне SQL."""
        with self._session() as s:
            rows = s.execute(
                select(DeviceModel.priority, func.count(DeviceModel.id))
                .group_by(DeviceModel.priority)
                .order_by(func.count(DeviceModel.id).desc())
            ).all()
            return [{"priority": priority, "count": count} for priority, count in rows]

    def _calc_overdue_count(self, threshold_days: int = OVERDUE_THRESHOLD_DAYS) -> int:
        with self._session() as s:
            cutoff = (datetime.now() - timedelta(days=threshold_days)).strftime("%Y-%m-%d")
            return s.execute(
                select(func.count(DeviceModel.id)).where(
                    DeviceModel.status.notin_(_CLOSED_STATUSES),
                    DeviceModel.receipt_date < cutoff,
                )
            ).scalar() or 0

    def _calc_overdue_orders(
        self, threshold_days: int = OVERDUE_THRESHOLD_DAYS
    ) -> list[dict[str, Any]]:
        with self._session() as s:
            cutoff = (datetime.now() - timedelta(days=threshold_days)).strftime("%Y-%m-%d")
            stmt = (
                select(DeviceModel)
                .where(
                    DeviceModel.status.notin_(_CLOSED_STATUSES),
                    DeviceModel.receipt_date < cutoff,
                )
                .order_by(DeviceModel.receipt_date)
            )
            return [device_to_row(d) for d in s.execute(stmt).scalars().all()]

    def _calc_dashboard_stats(
        self, threshold_days: int = OVERDUE_THRESHOLD_DAYS
    ) -> dict[str, Any]:
        """threshold_days по умолчанию — захардкоженная константа, а не
        пользовательская настройка "overdue_days" (Database-facade намеренно
        ничего не знает про SettingsManager — settings-осведомлённость живёт
        в вызывающем слое, см. AnalyticsService.run_report()). Раньше
        параметра не было вовсе — эту настройку через calculate() нельзя
        было передать в принципе, из-за чего desktop-дашборд (сам читает
        overdue_days и зовёт calculate("overdue_count", threshold_days=...))
        и PWA/AnalyticsService (звали dashboard_stats без параметра) при
        нестандартном overdue_days показывали два разных числа
        просроченных заказов, см. AUDIT_REPORT_v25.md."""
        stats = self.get_statistics()
        stats["overdue"] = self._calc_overdue_count(threshold_days=threshold_days)
        return stats
