"""Централизованный модуль логирования приложения.

Предоставляет единую точку входа для логирования во всех компонентах системы,
стандартизированные форматеры, обработчики и контекстное логирование.
"""

import json
import logging
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JSONFormatter(logging.Formatter):
    """Форматтер для вывода логов в JSON формате (для интеграции с ELK/Splunk)."""

    def __init__(self, include_extra: bool = True):
        super().__init__()
        self.include_extra = include_extra

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if self.include_extra:
            for key, value in record.__dict__.items():
                if key not in [
                    "name",
                    "msg",
                    "args",
                    "created",
                    "filename",
                    "funcName",
                    "levelname",
                    "levelno",
                    "lineno",
                    "module",
                    "msecs",
                    "pathname",
                    "process",
                    "processName",
                    "relativeCreated",
                    "stack_info",
                    "exc_info",
                    "exc_text",
                    "thread",
                    "threadName",
                ]:
                    try:
                        json.dumps(value)  # Проверка на сериализуемость
                        log_data[key] = value
                    except (TypeError, ValueError):
                        log_data[key] = str(value)

        return json.dumps(log_data, ensure_ascii=False)


class ColoredFormatter(logging.Formatter):
    """Форматтер с цветным выводом для консоли."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


class LogContext:
    """Контекстный менеджер для добавления мета-данных в логи."""

    _context: dict[str, Any] = {}

    @classmethod
    def set(cls, **kwargs) -> None:
        """Установить значения контекста."""
        cls._context.update(kwargs)

    @classmethod
    def clear(cls) -> None:
        """Очистить контекст."""
        cls._context.clear()

    @classmethod
    def get(cls) -> dict[str, Any]:
        """Получить текущий контекст."""
        return cls._context.copy()

    @contextmanager
    def __call__(self, **kwargs):
        """Использовать как контекстный менеджер."""
        old_context = self._context.copy()
        self._context.update(kwargs)
        try:
            yield
        finally:
            self._context.clear()
            self._context.update(old_context)


class ContextFilter(logging.Filter):
    """Фильтр для добавления контекстных данных в записи лога."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in LogContext.get().items():
            setattr(record, key, value)
        return True


def get_logger(name: str, use_json: bool = False) -> logging.Logger:
    """Получить настроенный логгер с именем.

    Args:
        name: Имя логгера (обычно __name__ модуля)
        use_json: Использовать JSON форматтер (по умолчанию False)

    Returns:
        Настроенный экземпляр logging.Logger
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # Уже настроен

    logger.setLevel(logging.DEBUG)

    # Консольный обработчик
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    if use_json:
        console_formatter = JSONFormatter()
    else:
        console_formatter = ColoredFormatter(
            "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(ContextFilter())
    logger.addHandler(console_handler)

    return logger


def setup_logging(
    log_file: Path | None = None,
    log_level: int = logging.INFO,
    use_json: bool = False,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> None:
    """Инициализировать систему логирования для всего приложения.

    Args:
        log_file: Путь к файлу логов (если None, только консоль)
        log_level: Минимальный уровень логирования
        use_json: Использовать JSON формат для файлов
        max_bytes: Максимальный размер файла перед ротацией
        backup_count: Количество резервных копий файлов логов
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Очистка старых обработчиков
    root_logger.handlers.clear()

    # Консольный обработчик
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    if use_json:
        console_formatter = JSONFormatter()
    else:
        console_formatter = ColoredFormatter(
            "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(ContextFilter())
    root_logger.addHandler(console_handler)

    # Файловый обработчик
    if log_file:
        from logging.handlers import RotatingFileHandler

        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setLevel(log_level)

        if use_json:
            file_formatter = JSONFormatter()
        else:
            file_formatter = logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )

        file_handler.setFormatter(file_formatter)
        file_handler.addFilter(ContextFilter())
        root_logger.addHandler(file_handler)

    # Логирование исключения на уровне приложения
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            return
        root_logger.critical(
            "Необработанное исключение", exc_info=(exc_type, exc_value, exc_traceback)
        )

    sys.excepthook = handle_exception


# Базовый класс для всех сервисов с встроенным логированием
class LoggableMixin:
    """Миксин для добавления логгера в любой класс."""

    _logger: logging.Logger | None = None

    @property
    def logger(self) -> logging.Logger:
        if self._logger is None:
            self._logger = get_logger(self.__class__.__name__)
        return self._logger

    def log_debug(self, message: str, **kwargs) -> None:
        self.logger.debug(message, extra=kwargs)

    def log_info(self, message: str, **kwargs) -> None:
        self.logger.info(message, extra=kwargs)

    def log_warning(self, message: str, **kwargs) -> None:
        self.logger.warning(message, extra=kwargs)

    def log_error(self, message: str, exc: Exception | None = None, **kwargs) -> None:
        if exc:
            self.logger.error(message, exc_info=exc, extra=kwargs)
        else:
            self.logger.error(message, extra=kwargs)

    def log_critical(
        self, message: str, exc: Exception | None = None, **kwargs
    ) -> None:
        if exc:
            self.logger.critical(message, exc_info=exc, extra=kwargs)
        else:
            self.logger.critical(message, extra=kwargs)
