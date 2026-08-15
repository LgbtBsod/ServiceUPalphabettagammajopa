"""Пример модуля расширения v24.0

Этот файл демонстрирует, как создать новый модуль для системы.
Просто добавьте папку в /modules/ с такой структурой:

/my_module/
  __init__.py    # этот файл (с метаданными)
  module.py      # логика модуля

Модуль автоматически будет обнаружен и загружен при старте приложения.
"""

from core.module_registry import ModuleBase

# === МЕТАДАННЫЕ МОДУЛЯ ===
MODULE_NAME = "example_module"
MODULE_VERSION = "1.0.0"
MODULE_DESCRIPTION = "Пример модуля для демонстрации архитектуры v24.0"
MODULE_AUTHOR = "Development Team"
MODULE_DEPENDENCIES = []  # Зависимости от других модулей (по имени)


class ExampleModule(ModuleBase):
    """Пример кастомного модуля.

    Этот модуль демонстрирует:
    - Автоматическое логирование через self.log
    - Доступ к сервисам через self.get_service()
    - Доступ к репозиториям через self.get_repository()
    - Жизненный цикл: on_init -> on_start -> on_stop
    """

    name = MODULE_NAME
    version = MODULE_VERSION
    description = MODULE_DESCRIPTION
    author = MODULE_AUTHOR
    dependencies = MODULE_DEPENDENCIES

    def on_init(self):
        """Инициализация модуля"""
        self.log.info(f"🔌 Модуль {self.name} v{self.version} инициализирован")
        self.log.debug(f"Описание: {self.description}")

        # Пример получения сервиса из DI контейнера
        # order_service = self.get_service("order_service")
        # self.log.info(f"Получен сервис заказов: {order_service}")

    def on_start(self):
        """Запуск модуля (вызывается после старта приложения)"""
        self.log.info(f"▶️ Модуль {self.name} запущен")

        # Здесь можно подписаться на события, запустить фоновые задачи и т.д.

    def on_stop(self):
        """Остановка модуля (вызывается перед закрытием приложения)"""
        self.log.info(f"⏹️ Модуль {self.name} остановлен")

        # Очистка ресурсов, закрытие соединений и т.д.

    def register_gui_components(self, gui_factory=None):
        """Регистрация GUI компонентов.

        Вызывается при инициализации GUI.
        Можно добавить свои панели, диалоги, виджеты.
        """
        if gui_factory is None:
            return

        self.log.debug(f"Регистрация GUI компонентов для {self.name}")

        # Пример добавления своей панели:
        # from gui.panels.example_panel import ExamplePanel
        # gui_factory.register_panel("example", ExamplePanel)

    def register_routes(self, router=None):
        """Регистрация API роутов.

        Если в приложении есть HTTP сервер, можно добавить свои endpoints.
        """
        if router is None:
            return

        self.log.debug(f"Регистрация API роутов для {self.name}")

        # Пример добавления роута:
        # @router.get("/api/v1/example/data")
        # async def get_example_data():
        #     return {"status": "ok", "module": self.name}


# Экспорт публичного API модуля
__all__ = ["ExampleModule"]
