"""Core Application Service
Single Source of Truth (SSOT) для инициализации и управления приложением.
Реализует паттерн Facade для упрощения взаимодействия с подсистемами.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto

from dependency_injector import containers
from dependency_injector.wiring import Provide, inject

from config.settings import (
    get_settings,
)
from events import EventBus
from shared.async_utils import async_wrap
from shared.logging_config import get_logger

# Глобальный экземпляр настроек (Singleton)
settings = get_settings()
# from i18n.service import I18NService

logger = get_logger(__name__)


class AppState(Enum):
    """Состояния жизненного цикла приложения."""

    INITIALIZING = auto()
    IDLE = auto()
    LOADING = auto()
    RUNNING = auto()
    SUSPENDED = auto()
    SHUTTING_DOWN = auto()
    ERROR = auto()


@dataclass(frozen=True)
class LoadingProgress:
    """Прогресс загрузки (для скелетонов и индикаторов)."""

    current: int
    total: int
    stage: str
    details: str | None = None

    @property
    def percentage(self) -> float:
        return (self.current / self.total * 100) if self.total > 0 else 0.0

    @property
    def is_complete(self) -> bool:
        return self.current >= self.total


class CoreApplication:
    """Главный класс приложения (Facade + State Machine).
    Управляет жизненным циклом, загрузкой модулей и состоянием.
    """

    def __init__(self) -> None:
        self._state = AppState.INITIALIZING
        self._container: containers.Container | None = None
        self._event_bus: EventBus | None = None
        self._loading_tasks: list[str] = []
        self._progress_callbacks: list[Callable[[LoadingProgress], None]] = []
        self._state_callbacks: list[Callable[[AppState], None]] = []

    def subscribe_progress(self, callback: Callable[[LoadingProgress], None]) -> None:
        """Подписка на обновления прогресса загрузки."""
        self._progress_callbacks.append(callback)

    def subscribe_state(self, callback: Callable[[AppState], None]) -> None:
        """Подписка на изменения состояния приложения."""
        self._state_callbacks.append(callback)

    def _notify_progress(self, progress: LoadingProgress) -> None:
        """Уведомление подписчиков о прогрессе."""
        for callback in self._progress_callbacks:
            try:
                callback(progress)
            except Exception as e:
                logger.exception(f"Error in progress callback: {e}")

    def _notify_state_change(self, new_state: AppState) -> None:
        """Уведомление подписчиков об изменении состояния."""
        old_state = self._state
        self._state = new_state
        logger.info(f"App state changed: {old_state.name} → {new_state.name}")
        for callback in self._state_callbacks:
            try:
                callback(new_state)
            except Exception as e:
                logger.exception(f"Error in state callback: {e}")

    @property
    def state(self) -> AppState:
        return self._state

    @inject
    async def initialize(
        self, container: containers.Container = Provide["container"]
    ) -> None:
        """Асинхронная инициализация приложения с прогресс-баром.
        Заменяет статический splash screen на динамическую загрузку.
        """
        self._notify_state_change(AppState.INITIALIZING)
        self._container = container

        stages = [
            ("config", "Loading configuration"),
            ("logging", "Initializing logging system"),
            ("i18n", "Loading translations"),
            ("database", "Connecting to database"),
            ("cache", "Warming up cache"),
            ("services", "Initializing services"),
            ("ui", "Preparing interface"),
        ]

        total_stages = len(stages)

        for idx, (stage_name, description) in enumerate(stages, 1):
            progress = LoadingProgress(
                current=idx, total=total_stages, stage=stage_name, details=description
            )
            self._notify_progress(progress)

            try:
                await self._run_stage(stage_name, description)
            except Exception as e:
                logger.exception(f"Failed to initialize stage '{stage_name}': {e}")
                self._notify_state_change(AppState.ERROR)
                raise

        self._notify_state_change(AppState.IDLE)
        logger.info("Application initialized successfully")

    async def _run_stage(self, stage_name: str, description: str) -> None:
        """Выполнение этапа инициализации."""
        # Имитация асинхронной работы для разных стадий
        if stage_name == "config":
            # Валидация конфига уже выполнена при импорте settings
            await asyncio.sleep(0.1)
        elif stage_name == "logging":
            # Логгер уже инициализирован
            await asyncio.sleep(0.1)
        elif stage_name == "i18n":
            i18n = (
                self._container.i18n_service()
                if hasattr(self._container, "i18n_service")
                else None
            )
            if i18n:
                await i18n.load_all_languages()
        elif stage_name == "database":
            db = (
                self._container.database()
                if hasattr(self._container, "database")
                else None
            )
            if db:
                await async_wrap(db.connect)()
        elif stage_name == "cache":
            cache = (
                self._container.cache_service()
                if hasattr(self._container, "cache_service")
                else None
            )
            if cache:
                await cache.warm_up()
        elif stage_name == "services":
            # Инициализация сервисов
            await asyncio.sleep(0.2)
        elif stage_name == "ui":
            # Подготовка UI компонентов
            await asyncio.sleep(0.1)

    async def run(self) -> None:
        """Запуск основного цикла приложения."""
        if self._state != AppState.IDLE:
            raise RuntimeError(f"Cannot run app in state {self._state.name}")

        self._notify_state_change(AppState.RUNNING)
        logger.info("Application started")

        try:
            # Основной цикл приложения
            while self._state == AppState.RUNNING:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Application loop cancelled")
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Корректное завершение работы приложения."""
        self._notify_state_change(AppState.SHUTTING_DOWN)
        logger.info("Shutting down application...")

        try:
            # Закрытие соединений
            if self._container:
                db = (
                    self._container.database()
                    if hasattr(self._container, "database")
                    else None
                )
                if db:
                    await async_wrap(db.disconnect)()

            # Остановка event bus
            if self._event_bus:
                await self._event_bus.shutdown()

        except Exception as e:
            logger.exception(f"Error during shutdown: {e}")
        finally:
            self._notify_state_change(AppState.IDLE)
            logger.info("Application shut down complete")


# Глобальный экземпляр (Singleton)
_app_instance: CoreApplication | None = None


def get_app() -> CoreApplication:
    """Получение глобального экземпляра приложения."""
    global _app_instance
    if _app_instance is None:
        _app_instance = CoreApplication()
    return _app_instance
