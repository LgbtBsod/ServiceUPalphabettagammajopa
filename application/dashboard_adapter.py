"""Адаптер для получения данных дашборда из слоя репозиториев (SQLAlchemy).
Принципы:
- SRP: Отвечает только за трансформацию данных из БД в DTO.
- DIP: Зависит от абстракций репозиториев, а не от конкретной реализации БД.
- Don't Reinvent the Wheel: Используем возможности SQLAlchemy для агрегации,
  а не пишем циклы на Python.
"""

from datetime import date
from decimal import Decimal
from typing import Protocol

from application.dtos import DashboardResponse, DashboardWidget, MetricPoint


class DashboardFilters:
    """Объект передачи параметров фильтрации (Request Object Pattern)."""

    def __init__(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
        status: str | None = None,
        priority: str | None = None,
        client_id: int | None = None,
    ):
        self.date_from = date_from
        self.date_to = date_to
        self.status = status
        self.priority = priority
        self.client_id = client_id

    def to_dict(self) -> dict:
        """Сериализация фильтров для включения в ответ."""
        return {k: v for k, v in self.__dict__.items() if v is not None}


class IDashboardRepository(Protocol):
    """Абстракция доступа к данным для дашбордов.
    Реализуется в инфраструктурном слое (например, через SQLAlchemy модели).
    """

    def get_kpi_summary(self, filters: DashboardFilters) -> dict[str, Decimal]:
        """Возвращает основные метрики (всего заказов, сумма, среднее время)."""
        ...

    def get_orders_by_status(self, filters: DashboardFilters) -> list[tuple[str, int]]:
        """Группировка заказов по статусам."""
        ...

    def get_revenue_dynamics(
        self, filters: DashboardFilters
    ) -> list[tuple[date, Decimal]]:
        """Динамика выручки по дням/месяцам."""
        ...


class DashboardAdapter:
    """Адаптер приложения.
    Преобразует сырые данные из репозитория в стандартизированный JSON-compatible DTO.
    """

    def __init__(self, repository: IDashboardRepository):
        self.repository = repository

    def build_dashboard(self, filters: DashboardFilters) -> DashboardResponse:
        """Собирает полный дашборд из различных виджетов.
        Логика сборки вынесена сюда, чтобы не засорять контроллеры или UI.
        """
        widgets: list[DashboardWidget] = []

        # Виджет 1: KPI Карточки
        kpi_data = self.repository.get_kpi_summary(filters)
        widgets.append(
            DashboardWidget(
                widget_id="kpi_summary",
                title="Ключевые показатели",
                widget_type="kpi_card",
                data=[{"label": k, "value": float(v)} for k, v in kpi_data.items()],
                config={"layout": "horizontal"},
            )
        )

        # Виджет 2: График по статусам
        status_data = self.repository.get_orders_by_status(filters)
        widgets.append(
            DashboardWidget(
                widget_id="orders_by_status",
                title="Заказы по статусам",
                widget_type="chart_bar",
                data=[
                    MetricPoint(label=status, value=Decimal(count))
                    for status, count in status_data
                ],
                config={"color_palette": "blue"},
            )
        )

        # Виджет 3: Динамика выручки
        revenue_data = self.repository.get_revenue_dynamics(filters)
        widgets.append(
            DashboardWidget(
                widget_id="revenue_dynamics",
                title="Динамика выручки",
                widget_type="chart_line",
                data=[
                    MetricPoint(label=d.isoformat(), value=amount)
                    for d, amount in revenue_data
                ],
                config={"show_points": True},
            )
        )

        return DashboardResponse(
            generated_at=date.today(),
            filters_applied=filters.to_dict(),
            widgets=widgets,
            summary=kpi_data,
        )
