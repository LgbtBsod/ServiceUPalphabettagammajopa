"""Контроллер (ViewModel) для GUI. Связывает сервис и представление.
Принципы:
- SRP: Управляет потоком данных между Service и View.
- DIP: Зависит от абстракции сервиса.
"""

import tkinter as tk

from application.dashboard_service import DashboardService
from application.dtos import DashboardResponse
from presentation.gui_view import DashboardGUIView


class DashboardController:
    """Контроллер для Desktop приложения.
    Инициализирует сервис, получает данные и передает их во View.
    """

    def __init__(self, service: DashboardService):
        self.service = service
        self.root = tk.Tk()

        # Передаем метод получения данных во View через callback
        self.view = DashboardGUIView(self.root, on_refresh=self._fetch_dashboard)

    def _fetch_dashboard(self) -> DashboardResponse:
        """Callback для View. Вызывает сервис с текущими параметрами."""
        # Здесь можно добавить логику получения параметров из UI фильтров
        return self.service.get_dashboard_data()

    def run(self):
        """Запуск приложения."""
        # Первичная загрузка данных
        self.view.refresh_data()
        self.root.mainloop()
