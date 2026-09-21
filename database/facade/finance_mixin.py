#!/usr/bin/env python3
"""FinanceMixin — финансовые записи (доход/расход/прибыль по заказу).
См. AUDIT_REPORT_v25.md, Task T."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, select

from database.facade.shared import logger
from database.sqlalchemy_models import FinanceRecord

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class FinanceMixin:
    """Требует self._session() от финального класса Database."""

    def get_finances(self, period: str = "all") -> list[dict[str, Any]]:
        with self._session() as s:
            stmt = select(FinanceRecord)
            cutoff = self._period_cutoff(period)
            if cutoff:
                stmt = stmt.where(FinanceRecord.completion_date >= cutoff)
            stmt = stmt.order_by(FinanceRecord.completion_date.desc())
            return [
                {
                    "id": r.id,
                    "order_number": r.order_number,
                    "completion_date": r.completion_date,
                    "income": r.income,
                    "expense": r.expense,
                    "profit": r.profit,
                }
                for r in s.execute(stmt).scalars().all()
            ]

    def get_finance_by_order_number(self, order_number: str) -> dict[str, Any] | None:
        """Точечный поиск одной финзаписи по номеру заказа — используется
        gui/main_window_parts/finance_mixin.py::edit_expense() вместо
        get_finances("all") + питон-цикл по ВСЕЙ (растущей без ограничения)
        истории финансов ради одной записи на каждый двойной клик по
        таблице (workflow-найденный баг: тот же класс проблемы, что
        get_all_devices()-сканы, которые уже переведены на AsyncLoadMixin/
        точечные запросы в других местах приложения)."""
        with self._session() as s:
            record = s.execute(
                select(FinanceRecord).where(FinanceRecord.order_number == order_number)
            ).scalar_one_or_none()
            if record is None:
                return None
            return {
                "id": record.id,
                "order_number": record.order_number,
                "completion_date": record.completion_date,
                "income": record.income,
                "expense": record.expense,
                "profit": record.profit,
            }

    def get_finance_summary(self, period: str = "all") -> dict[str, float]:
        with self._session() as s:
            stmt = select(
                func.coalesce(func.sum(FinanceRecord.income), 0.0),
                func.coalesce(func.sum(FinanceRecord.expense), 0.0),
                func.coalesce(func.sum(FinanceRecord.profit), 0.0),
            )
            cutoff = self._period_cutoff(period)
            if cutoff:
                stmt = stmt.where(FinanceRecord.completion_date >= cutoff)
            income, expense, profit = s.execute(stmt).one()
            return {
                "total_income": income,
                "total_expense": expense,
                "total_profit": profit,
            }

    @staticmethod
    def _period_cutoff(period: str) -> str | None:
        if period == "week":
            return (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        if period == "month":
            return (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        return None

    def update_finance_expense(self, order_number: str, expense: float) -> bool:
        try:
            with self._session() as s:
                record = s.execute(
                    select(FinanceRecord).where(
                        FinanceRecord.order_number == order_number
                    )
                ).scalar_one_or_none()
                if record is None:
                    return False
                record.expense = expense
                record.profit = (record.income or 0.0) - expense
                s.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка обновления расхода: {e}", exc_info=True)
            return False

    def _delete_finance_record(self, s: Session, order_number: str) -> None:
        """Удаляет FinanceRecord заказа — вызывается ИЗ delete_device()
        (devices_mixin.py) в той же сессии/транзакции, что и сам Device.

        Workflow-найденный баг: FinanceRecord связан с заказом только по
        order_number (обычная текстовая колонка, НЕ ForeignKey — в отличие
        от work_item_records/photo_records/defect_records/tag_records,
        у которых есть ondelete="CASCADE"), поэтому ORM-каскад при
        s.delete(device) его не трогает вообще. Без этой чистки удалённый
        заказ навсегда оставлял фантомную финзапись, которую
        get_finances()/get_finance_summary() продолжали суммировать —
        необратимо и молча завышая выручку/прибыль магазина."""
        if not order_number:
            return
        s.execute(delete(FinanceRecord).where(FinanceRecord.order_number == order_number))

    def _upsert_finance_record(
        self, s: Session, order_number: str, completion_date: str, income: float, expense: float
    ) -> None:
        record = s.execute(
            select(FinanceRecord).where(FinanceRecord.order_number == order_number)
        ).scalar_one_or_none()
        if record is None:
            record = FinanceRecord(order_number=order_number)
            s.add(record)
        record.completion_date = completion_date
        record.income = income
        record.expense = expense
        record.profit = income - expense
