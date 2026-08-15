"""Threading Module - Управление потоками приложения.

Разделяет потоки для:
- UI (главный поток рендеринга)
- Core (бизнес-логика ядра)
- DB (операции с базой данных)
- PDF (генерация отчётов)

Принципы:
- Изоляция потоков по ответственности
- Безопасная коммуникация через Queue/Event
- Graceful shutdown
"""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from queue import Empty, Queue
from typing import Any, Dict, Optional

from core.base import LoggableMixin
from core.events import Event, get_event_bus

logger = logging.getLogger(__name__)


@dataclass
class ThreadTask:
    """Задача для выполнения в потоке."""

    task_id: str
    func: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    priority: int = 0  # 0 - низкий, 10 - высокий
    created_at: datetime = field(default_factory=datetime.now)
    thread_type: str = "default"  # ui, core, db, pdf


@dataclass
class ThreadResult:
    """Результат выполнения задачи."""

    task_id: str
    success: bool
    result: Any = None
    error: str | None = None
    completed_at: datetime = field(default_factory=datetime.now)


class ThreadManager(LoggableMixin):
    """Менеджер потоков приложения.

    Управляет пулами потоков для разных типов задач:
    - UI поток (главный)
    - Core поток (бизнес-логика)
    - DB поток (операции с БД)
    - PDF поток (генерация отчётов)
    """

    def __init__(self):
        super().__init__()

        # Очереди для каждого типа потока
        self.ui_queue: Queue = Queue()
        self.core_queue: Queue = Queue()
        self.db_queue: Queue = Queue()
        self.pdf_queue: Queue = Queue()

        # Пулы потоков для фоновых задач
        self.core_executor = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="core_worker"
        )
        self.db_executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="db_worker"
        )
        self.pdf_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="pdf_worker"
        )

        # Результаты задач
        self._results: dict[str, ThreadResult] = {}
        self._results_lock = threading.Lock()

        # Флаг остановки
        self._running = True

        self.logger.info("ThreadManager initialized")

    def submit_to_ui(
        self, func: Callable, *args, task_id: str | None = None, **kwargs
    ) -> Future:
        """Отправляет задачу в UI поток."""
        task_id = task_id or f"ui_{datetime.now().timestamp()}"
        self.logger.debug(f"Submitting UI task: {task_id}")
        return self.core_executor.submit(func, *args, **kwargs)

    def submit_to_core(
        self,
        func: Callable,
        *args,
        task_id: str | None = None,
        priority: int = 5,
        **kwargs,
    ) -> Future:
        """Отправляет задачу в Core поток (бизнес-логика)."""
        task_id = task_id or f"core_{datetime.now().timestamp()}"
        self.logger.debug(f"Submitting Core task: {task_id}")

        future = self.core_executor.submit(
            self._execute_with_result, task_id, func, *args, **kwargs
        )

        return future

    def submit_to_db(
        self,
        func: Callable,
        *args,
        task_id: str | None = None,
        priority: int = 5,
        **kwargs,
    ) -> Future:
        """Отправляет задачу в DB поток (операции с БД)."""
        task_id = task_id or f"db_{datetime.now().timestamp()}"
        self.logger.debug(f"Submitting DB task: {task_id}")

        future = self.db_executor.submit(
            self._execute_with_result, task_id, func, *args, **kwargs
        )

        return future

    def submit_to_pdf(
        self, func: Callable, *args, task_id: str | None = None, **kwargs
    ) -> Future:
        """Отправляет задачу в PDF поток (генерация отчётов)."""
        task_id = task_id or f"pdf_{datetime.now().timestamp()}"
        self.logger.debug(f"Submitting PDF task: {task_id}")

        future = self.pdf_executor.submit(
            self._execute_with_result, task_id, func, *args, **kwargs
        )

        return future

    def _execute_with_result(
        self, task_id: str, func: Callable, *args, **kwargs
    ) -> Any:
        """Выполняет функцию и сохраняет результат."""
        try:
            result = func(*args, **kwargs)

            with self._results_lock:
                self._results[task_id] = ThreadResult(
                    task_id=task_id,
                    success=True,
                    result=result,
                )

            # Публикуем событие о завершении
            event_bus = get_event_bus()
            event_bus.publish(
                Event(
                    event_type="task.completed",
                    source="thread_manager",
                    data={
                        "task_id": task_id,
                        "success": True,
                    },
                )
            )

            return result

        except Exception as e:
            self.logger.exception(f"Task {task_id} failed: {e}")

            with self._results_lock:
                self._results[task_id] = ThreadResult(
                    task_id=task_id,
                    success=False,
                    error=str(e),
                )

            # Публикуем событие об ошибке
            event_bus = get_event_bus()
            event_bus.publish(
                Event(
                    event_type="task.failed",
                    source="thread_manager",
                    data={
                        "task_id": task_id,
                        "error": str(e),
                    },
                )
            )

            raise

    def get_result(self, task_id: str) -> ThreadResult | None:
        """Получает результат выполнения задачи."""
        with self._results_lock:
            return self._results.get(task_id)

    def wait_for_result(
        self, task_id: str, timeout: float | None = None
    ) -> ThreadResult | None:
        """Ждёт завершения задачи и возвращает результат."""
        start_time = datetime.now()

        while True:
            result = self.get_result(task_id)
            if result:
                return result

            # Проверяем таймаут
            if timeout:
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed >= timeout:
                    self.logger.warning(f"Timeout waiting for task {task_id}")
                    return None

            # Ждём немного перед следующей проверкой
            threading.Event().wait(0.1)

    def clear_results(self, older_than: datetime | None = None) -> int:
        """Очищает сохранённые результаты."""
        with self._results_lock:
            if older_than:
                to_remove = [
                    task_id
                    for task_id, result in self._results.items()
                    if result.completed_at < older_than
                ]
                for task_id in to_remove:
                    del self._results[task_id]
                return len(to_remove)
            else:
                count = len(self._results)
                self._results.clear()
                return count

    def shutdown(self, wait: bool = True) -> None:
        """Останавливает все потоки."""
        self.logger.info("Shutting down ThreadManager...")
        self._running = False

        if wait:
            self.core_executor.shutdown(wait=True)
            self.db_executor.shutdown(wait=True)
            self.pdf_executor.shutdown(wait=True)
        else:
            self.core_executor.shutdown(wait=False)
            self.db_executor.shutdown(wait=False)
            self.pdf_executor.shutdown(wait=False)

        self.logger.info("ThreadManager shut down")


# Глобальный экземпляр
_thread_manager: ThreadManager | None = None


def get_thread_manager() -> ThreadManager:
    """Получает глобальный экземпляр ThreadManager."""
    global _thread_manager
    if _thread_manager is None:
        _thread_manager = ThreadManager()
    return _thread_manager


def reset_thread_manager() -> None:
    """Сбрасывает менеджер потоков (для тестов)."""
    global _thread_manager
    if _thread_manager:
        _thread_manager.shutdown(wait=True)
    _thread_manager = None


# Удобные функции для быстрого доступа
def run_in_ui_thread(func: Callable, *args, **kwargs) -> Future:
    """Выполняет функцию в UI потоке."""
    return get_thread_manager().submit_to_ui(func, *args, **kwargs)


def run_in_core_thread(func: Callable, *args, **kwargs) -> Future:
    """Выполняет функцию в Core потоке."""
    return get_thread_manager().submit_to_core(func, *args, **kwargs)


def run_in_db_thread(func: Callable, *args, **kwargs) -> Future:
    """Выполняет функцию в DB потоке."""
    return get_thread_manager().submit_to_db(func, *args, **kwargs)


def run_in_pdf_thread(func: Callable, *args, **kwargs) -> Future:
    """Выполняет функцию в PDF потоке."""
    return get_thread_manager().submit_to_pdf(func, *args, **kwargs)
