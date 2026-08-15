"""ServiceUP Core - Центральное ядро системы.

Ядро предоставляет:
- Доступ ко всем сервисам и репозиториям через единый интерфейс
- Управление жизненным циклом плагинов и модулей
- Dependency Injection контейнер
- Систему событий
- Логирование и мониторинг
- Управление потоками (ThreadManager, WorkerPool, TaskScheduler)

Принципы:
- Single Entry Point - все взаимодействия через ядро
- Facade Pattern - упрощение сложной системы
- Dependency Inversion - зависимость от абстракций
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.base import LoggableMixin
from core.di.container import DIContainer, get_container
from core.events import EventBus, get_event_bus
from core.plugin_system import IPlugin, PluginManager, get_plugin_manager
from core.threading import ThreadManager, WorkerPool, TaskScheduler
from core.module_manager import (
    ModuleCache,
    ModuleRegistrySingleton,
    get_module_cache,
    get_module_singleton_registry,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType


@dataclass
class CoreServices:
    """Сервисы ядра, доступные всем модулям."""

    container: DIContainer
    event_bus: EventBus
    plugin_manager: PluginManager
    thread_manager: ThreadManager
    worker_pool: WorkerPool
    task_scheduler: TaskScheduler
    module_cache: ModuleCache
    module_registry: ModuleRegistrySingleton
    logger: Any = None


class ServiceUpCore(LoggableMixin):
    """Центральное ядро системы ServiceUP.
    
    Все модули и плагины получают доступ к функциональности через ядро.
    
    Пример использования:
        # Инициализация
        core = ServiceUpCore()
        core.initialize()
        
        # Регистрация плагина
        core.register_plugin(MyPlugin())
        
        # Получение сервиса через ядро
        order_service = core.get_service(OrderService)
        
        # Подписка на события
        core.subscribe(OrderCreatedEvent, handler)
        
        # Вызов метода другого модуля через API
        result = core.call_module_method('billing', 'calculate_total', order_id=123)
    """

    def __init__(self):
        super().__init__()
        self._initialized = False
        self._container: DIContainer | None = None
        self._event_bus: EventBus | None = None
        self._plugin_manager: PluginManager | None = None
        self._thread_manager: ThreadManager | None = None
        self._worker_pool: WorkerPool | None = None
        self._task_scheduler: TaskScheduler | None = None
        self._module_cache: ModuleCache | None = None
        self._module_registry: ModuleRegistrySingleton | None = None
        self._module_apis: dict[str, Any] = {}
        self._services: dict[str, Any] = {}

    @property
    def is_initialized(self) -> bool:
        """True, если initialize() уже был вызван для этого ядра."""
        return self._initialized

    @property
    def services(self) -> CoreServices:
        """Возвращает сервисы ядра."""
        if not self._initialized:
            raise RuntimeError("Core not initialized. Call initialize() first.")
        
        return CoreServices(
            container=self._container,
            event_bus=self._event_bus,
            plugin_manager=self._plugin_manager,
            thread_manager=self._thread_manager,
            worker_pool=self._worker_pool,
            task_scheduler=self._task_scheduler,
            module_cache=self._module_cache,
            module_registry=self._module_registry,
            logger=self.logger,
        )

    def initialize(self) -> None:
        """Инициализирует ядро системы."""
        if self._initialized:
            self.logger.warning("Core already initialized")
            return

        self.logger.info("Initializing ServiceUP Core...")

        # Инициализация DI контейнера
        self._container = get_container()
        self._register_core_services()

        # Инициализация шины событий
        self._event_bus = get_event_bus()

        # Инициализация менеджера плагинов
        self._plugin_manager = get_plugin_manager()

        # Инициализация менеджера потоков
        self._thread_manager = ThreadManager.get_instance()

        # Инициализация пула работников
        self._worker_pool = WorkerPool(max_workers=4, name="CoreWorkerPool")
        self._worker_pool.start()

        # Инициализация планировщика задач
        self._task_scheduler = TaskScheduler(name="CoreTaskScheduler")
        self._task_scheduler.start()

        # Инициализация кэша модулей
        self._module_cache = get_module_cache()

        # Инициализация реестра синглетонов модулей
        self._module_registry = get_module_singleton_registry()

        self._initialized = True
        self.logger.info("ServiceUP Core initialized successfully")

    def _register_core_services(self) -> None:
        """Регистрирует сервисы ядра в DI контейнере."""
        # Регистрируем само ядро как singleton
        self._container.register_instance(ServiceUpCore, self)
        
        # Регистрируем EventBus
        self._container.register_instance(EventBus, self._event_bus)
        
        # Регистрируем PluginManager
        self._container.register_instance(PluginManager, self._plugin_manager)
        
        # Регистрируем ModuleCache
        self._container.register_instance(ModuleCache, self._module_cache)
        
        # Регистрируем ModuleRegistrySingleton
        self._container.register_instance(ModuleRegistrySingleton, self._module_registry)

    def register_plugin(self, plugin: IPlugin) -> None:
        """Регистрирует плагин в системе."""
        if not self._initialized:
            raise RuntimeError("Core not initialized")
        
        self._plugin_manager.register(plugin)
        self.logger.info(f"Plugin '{plugin.metadata.name}' registered")

    def enable_plugin(self, plugin_name: str) -> bool:
        """Включает плагин по имени."""
        if not self._initialized:
            raise RuntimeError("Core not initialized")
        
        return self._plugin_manager.enable(plugin_name)

    def disable_plugin(self, plugin_name: str) -> None:
        """Отключает плагин по имени."""
        if not self._initialized:
            raise RuntimeError("Core not initialized")
        
        self._plugin_manager.disable(plugin_name)

    def get_plugin_api(self, plugin_name: str) -> Any | None:
        """Получает публичный API плагина."""
        if not self._initialized:
            raise RuntimeError("Core not initialized")
        
        return self._plugin_manager.get_api(plugin_name)

    def register_module(
        self,
        name: str,
        module_instance: Any,
        module_type: type,
        api: Any | None = None,
        dependencies: list[str] | None = None,
    ) -> None:
        """Регистрирует модуль в ядре через реестр синглетонов.

        Модули регистрируются как синглетоны и получают доступ друг к другу
        только через ядро.

        Args:
            name: Уникальное имя модуля
            module_instance: Экземпляр модуля
            module_type: Тип модуля (класс)
            api: Публичный API модуля (опционально)
            dependencies: Список зависимостей от других модулей
        """
        # Регистрируем в реестре синглетонов
        self._module_registry.register(
            name=name,
            instance=module_instance,
            module_type=module_type,
            api=api,
            dependencies=dependencies,
        )

        # Если есть API, сохраняем для быстрого доступа
        if api is not None:
            self._module_apis[name] = api

        self._services[name] = module_instance
        self.logger.info(f"Module '{name}' registered as singleton")

    def get_module_api(self, module_name: str) -> Any | None:
        """Получает публичный API модуля через реестр."""
        return self._module_registry.get_api(module_name)

    def get_module_instance(self, module_name: str) -> Any | None:
        """Получает экземпляр модуля через реестр.

        WARNING: Прямой доступ нарушает инкапсуляцию.
        Используйте get_module_api() или call_module_method().
        """
        return self._module_registry.get_instance(module_name)

    def call_module_method(
        self,
        module_name: str,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Вызывает метод модуля через его API.

        Это основной способ взаимодействия между модулями.
        Модули не должны импортировать друг друга напрямую.

        Все вызовы проходят через реестр синглетонов.
        """
        # ВАЖНО: module_name/method_name передаются позиционно, а не как
        # keyword вперемешку с *args — `f(module_name=x, *args)` при
        # непустом args приводит к "got multiple values for argument
        # 'module_name'", т.к. *args распаковывается в первый позиционный
        # параметр раньше, чем применяется keyword. Гарантированный краш
        # call_module_method() с любыми позиционными аргументами — самый
        # частый способ его вызова. Найдено тестами (tests/test_kernel.py,
        # tests/test_plugins_clients.py), см. AUDIT_REPORT_v21.md.
        return self._module_registry.call_method(
            module_name, method_name, *args, **kwargs
        )

    def get_db_access(self) -> Any | None:
        """Получает доступ к модулю работы с БД через ядро.

        Это единственный безопасный способ получить доступ к базе данных.
        Только один модуль (db_access) управляет подключениями.
        """
        return self._module_registry.get_db_access()

    def cache_set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> None:
        """Устанавливает значение в кэш ядра."""
        self._module_cache.set(key, value, ttl_seconds=ttl_seconds)

    def cache_get[T](self, key: str, default: T | None = None) -> T | None:
        """Получает значение из кэша ядра."""
        return self._module_cache.get(key, default=default)

    def cache_delete(self, key: str) -> bool:
        """Удаляет значение из кэша."""
        return self._module_cache.delete(key)

    def cache_invalidate_pattern(self, pattern: str) -> int:
        """Инвалидирует записи кэша по шаблону."""
        return self._module_cache.invalidate_pattern(pattern)

    def get_service[T](self, service_type: type[T]) -> T:
        """Получает сервис из DI контейнера."""
        if not self._initialized:
            raise RuntimeError("Core not initialized")

        return self._container.resolve(service_type)

    def register_service[T](self, service_type: type[T], instance: T) -> None:
        """Регистрирует внешний сервис (Database, менеджеры и т.п.) как singleton
        в DI-контейнере ядра. Публичная точка входа для bootstrap-кода —
        _register_core_services() регистрирует только внутренние объекты ядра.
        """
        if not self._initialized:
            raise RuntimeError("Core not initialized")

        self._container.register_instance(service_type, instance)

    def subscribe(self, event_type: type, handler: Callable) -> None:
        """Подписывается на событие."""
        if not self._initialized:
            raise RuntimeError("Core not initialized")
        
        self._event_bus.subscribe(event_type, handler)

    def unsubscribe(self, event_type: type, handler: Callable) -> None:
        """Отписывается от события."""
        if not self._initialized:
            raise RuntimeError("Core not initialized")
        
        self._event_bus.unsubscribe(event_type, handler)

    def publish(self, event: object) -> None:
        """Публикует событие."""
        if not self._initialized:
            raise RuntimeError("Core not initialized")
        
        self._event_bus.publish(event)

    def submit_task(
        self,
        task_id: str,
        func: Callable[..., Any],
        priority: int = 0,
        *args: Any,
        **kwargs: Any,
    ) -> str | None:
        """Отправляет задачу в пул работников ядра.
        
        Args:
            task_id: Уникальный идентификатор задачи
            func: Функция для выполнения
            priority: Приоритет задачи (меньше = выше приоритет)
            *args: Позиционные аргументы функции
            **kwargs: Именованные аргументы функции
            
        Returns:
            ID задачи если успешно, None иначе
        """
        if not self._initialized:
            raise RuntimeError("Core not initialized")
        
        return self._worker_pool.submit(
            task_id=task_id,
            func=func,
            priority=priority,
            *args,
            **kwargs,
        )

    def schedule_task(
        self,
        task_id: str,
        func: Callable[..., Any],
        interval_seconds: int,
        start_immediately: bool = False,
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        """Планирует периодическое выполнение задачи.
        
        Args:
            task_id: Уникальный идентификатор задачи
            func: Функция для выполнения
            interval_seconds: Интервал между выполнениями в секундах
            start_immediately: Выполнить немедленно при планировании
            *args: Позиционные аргументы функции
            **kwargs: Именованные аргументы функции
            
        Returns:
            True если успешно, False иначе
        """
        if not self._initialized:
            raise RuntimeError("Core not initialized")
        
        return self._task_scheduler.schedule_interval(
            task_id=task_id,
            func=func,
            interval_seconds=interval_seconds,
            start_immediately=start_immediately,
            *args,
            **kwargs,
        )

    def create_thread(
        self,
        name: str,
        target: Callable[..., Any],
        args: tuple = (),
        kwargs: dict | None = None,
        daemon: bool = False,
    ) -> str:
        """Создаёт управляемый поток через ThreadManager.
        
        Args:
            name: Уникальное имя потока
            target: Целевая функция потока
            args: Позиционные аргументы функции
            kwargs: Именованные аргументы функции
            daemon: Является ли поток демоном
            
        Returns:
            ID созданного потока
        """
        if not self._initialized:
            raise RuntimeError("Core not initialized")
        
        return self._thread_manager.create_thread(
            name=name,
            target=target,
            args=args,
            kwargs=kwargs or {},
            daemon=daemon,
        )

    def start_thread(self, thread_id: str) -> bool:
        """Запускает созданный поток."""
        if not self._initialized:
            raise RuntimeError("Core not initialized")

        return self._thread_manager.start_thread(thread_id)

    def stop_thread(self, thread_id: str, timeout: float = 5.0) -> bool:
        """Останавливает поток и сразу освобождает его имя (cleanup_stopped()),
        чтобы вызывающий мог создать новый поток с тем же именем (например,
        повторный старт PWA-сервера). Без этого create_thread(name=...) с уже
        использованным именем падает с ValueError даже после того, как старый
        поток фактически завершился — см. AUDIT_REPORT_v21.md."""
        if not self._initialized:
            raise RuntimeError("Core not initialized")

        result = self._thread_manager.stop_thread(thread_id, timeout=timeout)
        self._thread_manager.cleanup_stopped()
        return result

    def shutdown(self) -> None:
        """Корректно завершает работу ядра."""
        if not self._initialized:
            return

        self.logger.info("Shutting down ServiceUP Core...")

        # Останавливаем планировщик задач
        if self._task_scheduler:
            self._task_scheduler.stop(wait=True)

        # Останавливаем пул работников
        if self._worker_pool:
            self._worker_pool.shutdown(wait=True, cancel_pending=True)

        # Останавливаем все потоки через ThreadManager
        if self._thread_manager:
            self._thread_manager.stop_all(timeout=5.0)

        # Отключаем все плагины
        for plugin_info in self._plugin_manager.list_plugins():
            if plugin_info["state"] == "active":
                try:
                    self._plugin_manager.disable(plugin_info["name"])
                except Exception as e:
                    self.logger.error(
                        f"Error disabling plugin {plugin_info['name']}: {e}"
                    )

        self._initialized = False
        self.logger.info("ServiceUP Core shut down")


# Глобальный экземпляр ядра
_core_instance: ServiceUpCore | None = None


def get_core() -> ServiceUpCore:
    """Получает глобальный экземпляр ядра (singleton)."""
    global _core_instance
    if _core_instance is None:
        _core_instance = ServiceUpCore()
    return _core_instance


def reset_core() -> None:
    """Сбрасывает глобальный экземпляр ядра (для тестов)."""
    global _core_instance
    if _core_instance:
        _core_instance.shutdown()
    _core_instance = None


__all__ = [
    "CoreServices",
    "ServiceUpCore",
    "get_core",
    "reset_core",
]
