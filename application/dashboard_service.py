"""Сервис дашбордов. Оркестрирует получение данных и отдачу результата.
Принципы:
- SRP: Содержит бизнес-логику формирования дашборда, но не знает про UI или БД напрямую.
- DIP: Зависит от адаптера (абстракции), а не от реализации репозитория.
"""

from application.dashboard_adapter import DashboardAdapter, DashboardFilters
from application.dtos import DashboardResponse


class DashboardService:
    """Высокоуровневый сервис для работы с дашбордами.
    Используется контроллерами (GUI или Web).
    """

    def __init__(self, adapter: DashboardAdapter):
        self.adapter = adapter

    def get_dashboard_data(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        client_id: int | None = None,
    ) -> DashboardResponse:
        """Публичный API сервиса.
        Принимает примитивы (строки, int), валидирует и собирает дашборд.
        Возвращает готовый DTO, который можно сериализовать в JSON.
        """
        # Парсинг дат (можно вынести в отдельный валидатор)
        from datetime import date

        d_from = date.fromisoformat(date_from) if date_from else None
        d_to = date.fromisoformat(date_to) if date_to else None

        filters = DashboardFilters(
            date_from=d_from,
            date_to=d_to,
            status=status,
            priority=priority,
            client_id=client_id,
        )

        return self.adapter.build_dashboard(filters)
