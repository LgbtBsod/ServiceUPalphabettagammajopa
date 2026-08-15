"""Акт взаимодействия: Ядро → Генератор отчётов → DB Access

Документ описывает поток данных при генерации отчётов.
Все обращения к данным идут ЧЕРЕЗ DataAccessManager.
"""

import logging
from datetime import datetime
from typing import Any

from core.analytics import get_analytics, track_db_access
from core.base import BaseService
from infrastructure.db_access import DatabaseConfig, get_db_access

logger = logging.getLogger(__name__)


class ReportDataGenerator(BaseService):
    """Генератор данных для отчётов.

    Использует ТОЛЬКО DataAccessManager для получения данных.
    Никаких прямых SQL запросов!
    """

    def __init__(self, db_config: DatabaseConfig | None = None):
        super().__init__()
        self.db_access = get_db_access()

        if db_config:
            from infrastructure.db_access import initialize_db_access

            initialize_db_access(db_config)

        self.analytics = get_analytics()

    @track_db_access(operation_type="Query", table_name="orders")
    def get_orders_for_report(
        self, start_date: datetime, end_date: datetime, status: str | None = None
    ) -> list[dict[str, Any]]:
        """Получение данных заказов для отчёта.

        Поток:
        1. Ядро вызывает ReportDataGenerator.get_orders_for_report()
        2. Генератор запрашивает данные через DataAccessManager
        3. DataAccessManager выполняет запрос через SQLAlchemy
        4. Аналитика записывает метрику обращения
        5. Данные возвращаются в ядро
        """
        from infrastructure.sqlalchemy_models import Order

        filters = {"created_at__gte": start_date, "created_at__lte": end_date}

        if status:
            filters["status"] = status

        # Запрос через DataAccessManager (никакого raw SQL!)
        orders = self.db_access.get_all(
            table=Order, filters=filters, order_by=Order.created_at
        )

        self.logger.info(f"Получено {len(orders)} заказов для отчёта")
        return orders

    @track_db_access(operation_type="Query", table_name="clients")
    def get_clients_for_report(self, active_only: bool = True) -> list[dict[str, Any]]:
        """Получение данных клиентов для отчёта"""
        from infrastructure.sqlalchemy_models import Client

        filters = {}
        if active_only:
            filters["is_active"] = True

        clients = self.db_access.get_all(
            table=Client, filters=filters, order_by=Client.name
        )

        self.logger.info(f"Получено {len(clients)} клиентов для отчёта")
        return clients

    @track_db_access(operation_type="Query", table_name="work_items")
    def get_work_items_for_report(
        self, order_id: int | None = None
    ) -> list[dict[str, Any]]:
        """Получение данных выполненных работ для отчёта"""
        from infrastructure.sqlalchemy_models import WorkItem

        filters = {}
        if order_id:
            filters["order_id"] = order_id

        work_items = self.db_access.get_all(
            table=WorkItem, filters=filters, order_by=WorkItem.created_at
        )

        self.logger.info(f"Получено {len(work_items)} работ для отчёта")
        return work_items

    @track_db_access(operation_type="Query", table_name="revenue")
    def get_revenue_summary(
        self, start_date: datetime, end_date: datetime
    ) -> dict[str, Any]:
        """Получение сводки по выручке.

        Возвращает агрегированные данные:
        - Общая сумма
        - Количество заказов
        - Средний чек
        """
        orders = self.get_orders_for_report(start_date, end_date)

        total_revenue = sum(float(o.get("total", 0)) for o in orders)
        order_count = len(orders)
        avg_check = total_revenue / order_count if order_count > 0 else 0

        summary = {
            "total_revenue": total_revenue,
            "order_count": order_count,
            "avg_check": avg_check,
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
        }

        self.logger.info(f"Выручка за период: {total_revenue:.2f} руб.")
        return summary

    def generate_full_report(
        self, start_date: datetime, end_date: datetime
    ) -> dict[str, Any]:
        """Генерация полного отчёта.

        Поток данных:
        Ядро → ReportDataGenerator → DataAccessManager → БД
        """
        self.logger.info(f"Генерация полного отчёта: {start_date} - {end_date}")

        # Сбор данных через единый интерфейс
        orders = self.get_orders_for_report(start_date, end_date)
        clients = self.get_clients_for_report(active_only=True)
        work_items = self.get_work_items_for_report()
        revenue = self.get_revenue_summary(start_date, end_date)

        report = {
            "generated_at": datetime.now().isoformat(),
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "summary": revenue,
            "data": {"orders": orders, "clients": clients, "work_items": work_items},
        }

        # Экспорт статистики обращений к БД
        db_stats = self.analytics.export_report()
        report["db_analytics"] = db_stats

        self.logger.info("Отчёт успешно сгенерирован")
        return report


# ========== ПРИМЕР ИСПОЛЬЗОВАНИЯ ==========


def example_usage():
    """Пример использования из ядра приложения.

    Ядро НЕ работает с БД напрямую!
    Ядро → Генератор → DB Access → БД
    """
    from config.settings import get_settings

    # 1. Получение настроек из ядра
    settings = get_settings()
    db_config = DatabaseConfig.from_settings(settings.dict())

    # 2. Создание генератора (ядро не знает про БД)
    generator = ReportDataGenerator(db_config=db_config)

    # 3. Запрос данных (ядро получает готовые данные)
    from datetime import datetime, timedelta

    report = generator.generate_full_report(
        start_date=datetime.now() - timedelta(days=30), end_date=datetime.now()
    )

    # 4. Использование отчёта в ядре
    print(f"Выручка: {report['summary']['total_revenue']:.2f} руб.")
    print(f"Заказов: {report['summary']['order_count']}")

    # 5. Проверка аналитики обращений
    analytics = get_analytics()
    stats = analytics.export_report()

    print("\nСтатистика обращений к БД:")
    print(f"Всего запросов: {stats['summary']['total_calls']}")
    print(f"Уникальных таблиц: {stats['summary']['unique_tables']}")
    print(f"Кэш хиты: {stats['cache']['hit_rate']:.1f}%")


if __name__ == "__main__":
    example_usage()
