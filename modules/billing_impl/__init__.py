"""Реализация модуля Billing v1.0.0

Этот модуль демонстрирует новую архитектуру с разделением:
- billing.py - файл-обертка с метаданными (не требует изменений при расширении)
- billing_impl/ - папка с реализацией (можно добавлять файлы по мере роста)

Структура billing_impl/:
- __init__.py - точка входа, класс модуля
- service.py - бизнес-логика биллинга
- exceptions.py - исключения модуля (авто-загружаются в ModuleBase.ModuleError)
- models.py - модели данных
- config.yaml - конфигурация
"""

# ПРОСТОЙ ИМПОРТ ВСЕХ ЗАВИСИМОСТЕЙ ЧЕРЕЗ WRAPPER
from modules._module_call import CoreException, ModuleBase, ServiceException, log


class BillingModule(ModuleBase):
    """Модуль биллинга и платежей"""

    name = "billing"
    version = "1.0.0"
    description = "Модуль биллинга и платежей"
    author = "Development Team"
    dependencies = []

    def on_init(self):
        """Инициализация модуля биллинга"""
        self.log.info(f"💰 Модуль {self.name} v{self.version} инициализирован")

        # Пример использования safe_execute
        result = self.safe_execute(self._load_config, default={}, raise_on_error=False)
        self.log.debug(f"Конфигурация загружена: {result}")

    def _load_config(self):
        """Пример безопасной операции"""
        # Здесь могла бы быть загрузка конфига из БД или файла
        return {"billing_enabled": True}

    def on_start(self):
        """Запуск модуля"""
        self.log.info(f"▶️ Модуль {self.name} запущен")

        # Пример получения сервиса из DI через базовый класс
        # order_service = self.get_service("order_service")

    def on_stop(self):
        """Остановка модуля"""
        self.log.info(f"⏹️ Модуль {self.name} остановлен")


# Экспорт
__all__ = ["BillingModule"]
