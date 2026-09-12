"""Orders Plugin — swappable repository seam over the existing Device/order
persistence (database/facade/devices_mixin.py), NOT a rewrite of it.

Контекст: обзор SRP/DRY-кандидатов на плагин (2026-09) нашёл, что среди 11
оставшихся SQLAlchemy-моделей только Device реально удовлетворяет тому же
критерию, что оправдывал plugins/clients и plugins/employees — "владеет
своей таблицей И выиграла бы от подменяемой за интерфейсом реализации".
Остальные 10 (RecordLock, WorkTemplate, Settings, Counter, DictionaryItem,
FinanceRecord, WorkItemRecord, PhotoRecord, CompletedRepair,
RepairHistoryMain) — либо мёртвые таблицы, либо простое внутреннее
служебное состояние, либо dual-write дети Device без независимого
жизненного цикла; форсировать для них плагин было бы искусственной
абстракцией без реальной пользы.

Но Device используется в ~150+ местах кода (GUI/PWA/reports) — полный
перенос вызывающего кода на core.get_module_api("orders") сам по себе
многодневная задача, не этот шаг. Здесь заводится только сама точка
расширения: IOrderRepository описывает контракт,
plugins/orders/repository.py::SqlAlchemyOrderRepository реализует его,
ДЕЛЕГИРУЯ в уже работающий Database facade (см. репозиторий за
объяснением, почему не повторной SQLAlchemy-реализацией с нуля, как у
clients/employees). Существующие вызывающие места продолжают работать как
раньше, напрямую через core.get_db_access()/Database — ничего не сломано и
не обязано мигрировать сразу. Новый код может по желанию получать тот же
функционал и через core.get_module_api("orders")/core.call_module_method().
"""

from abc import abstractmethod
from typing import Any

from core.base import BaseRepository
from core.plugin_system import BasePlugin, PluginMetadata, get_plugin_manager


class IOrderRepository(BaseRepository[dict[str, Any]]):
    """Контракт доступа к заказам (Device) — см. docstring модуля.

    @abstractmethod на каждом методе — без этого ABCMeta не блокирует
    конструирование неполной реализации (та же причина, что у
    IClientRepository/IEmployeeRepository, см. AUDIT_REPORT_v25.md)."""

    @abstractmethod
    def get_next_order_number(self) -> int:
        """Выдать следующий номер заказа И увеличить счётчик."""

    @abstractmethod
    def peek_next_order_number(self) -> int:
        """Подсмотреть следующий номер заказа БЕЗ инкремента (для UI-превью)."""

    @abstractmethod
    def add_device(self, device_data: dict[str, Any]) -> int | None:
        """Создать заказ. Возвращает id новой записи или None при ошибке."""

    @abstractmethod
    def update_device(self, device_id: int, device_data: dict[str, Any]) -> bool:
        """Обновить заказ. Может бросить OptimisticLockError
        (database/facade/shared.py) при конфликте версий (_expected_version
        в device_data)."""

    @abstractmethod
    def update_device_status(
        self, device_id: int, status: str, completion_date: str | None = None
    ) -> bool:
        """Быстрая смена статуса без полной формы (PWA/кнопка "выдать")."""

    @abstractmethod
    def delete_device(self, device_id: int) -> bool:
        """Удалить заказ (каскадно удаляет дочерние work_items/photos)."""

    @abstractmethod
    def get_all_devices(self, include_completed: bool = True) -> list[dict[str, Any]]:
        """Все заказы, новые первыми."""

    @abstractmethod
    def get_device(self, device_id: int) -> dict[str, Any] | None:
        """Заказ по id."""

    @abstractmethod
    def get_device_by_order_number(self, order_number: str) -> dict[str, Any] | None:
        """Заказ по номеру."""

    @abstractmethod
    def get_device_id_by_order_number(self, order_number: str) -> int | None:
        """id заказа по номеру."""

    @abstractmethod
    def search_devices(
        self, search_text: str, include_completed: bool = True
    ) -> list[dict[str, Any]]:
        """Поиск по имени клиента/телефону/номеру заказа."""

    @abstractmethod
    def get_devices_by_filters(
        self,
        status_filter: str,
        priority_filter: str,
        include_completed: bool = True,
        device_type_filter: str = "Все",
        brand_filter: str = "Все",
    ) -> list[dict[str, Any]]:
        """Заказы по статусу/приоритету/типу/бренду ("Все" — фильтр не применяется)."""

    @abstractmethod
    def get_statistics(self) -> dict[str, int]:
        """total/in_repair/ready/total_income."""


class OrdersPlugin(BasePlugin):
    """Orders feature plugin.

    В отличие от ClientsPlugin/EmployeesPlugin здесь нет отдельного Service
    поверх репозитория: вся бизнес-логика (BOBF change detection,
    оптимистичная блокировка, dual-write в Finance/WorkItem/Photo,
    публикация DeviceStatusChangedEvent) уже живёт в Database/
    devices_mixin.py, которую репозиторий просто оборачивает — заводить
    пустой Service-слой без единой строчки добавленной логики было бы
    искусственной абстракцией (см. правило проекта: "три похожие строки
    лучше преждевременной абстракции")."""

    def __init__(self):
        super().__init__()
        self._repository: IOrderRepository | None = None

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="orders",
            version="1.0.0",
            description="Order/device access behind a swappable repository interface",
            author="ServiceUp Team",
            dependencies=[],
            min_core_version="25.0",
            standalone=True,
        )

    def on_initialize(self, context) -> bool:
        """Initialize orders plugin through Core (context)."""
        self.logger.info("Initializing Orders Plugin")

        self._repository = context.get_service(IOrderRepository)
        context.register_module("orders", self, OrdersPlugin, api=self._repository)

        self.logger.info("Orders Plugin initialized successfully via Core")
        return True

    def shutdown(self) -> None:
        """Cleanup orders plugin resources."""
        self.logger.info("Shutting down Orders Plugin")
        self._repository = None
        super().shutdown()

    def get_api(self) -> IOrderRepository | None:
        """Return orders repository API.

        Другие модули получают доступ к заказам через этот API, используя
        core.call_module_method(), как альтернативу прямому
        core.get_db_access()."""
        return self._repository

    def configure(self, config: dict) -> None:
        """Configure orders plugin."""
        self.logger.info(f"Configuring Orders Plugin: {config}")


def register_plugin():
    """Register the Orders plugin with the plugin manager."""
    plugin_manager = get_plugin_manager()
    plugin = OrdersPlugin()
    plugin_manager.register(plugin)
    return plugin


__all__ = [
    "IOrderRepository",
    "OrdersPlugin",
    "register_plugin",
]
