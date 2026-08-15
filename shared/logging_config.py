"""Logging Module
Uses Python standard library logging with structured formatting
Follows SOLID/DRY principles with centralized configuration
"""

from __future__ import annotations

import logging
import sys
import time
from contextlib import contextmanager
from functools import lru_cache

from config import get_data_dir, get_settings


class LogFormatter(logging.Formatter):
    """Custom formatter with colored output for console
    and detailed format for files
    """

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def __init__(self, use_colors: bool = True):
        super().__init__()
        self.use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        # Create format based on level
        if self.use_colors and hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
            color = self.COLORS.get(record.levelname, self.RESET)
            reset = self.RESET
            level_format = f"{color}%(levelname)-8s{reset}"
        else:
            level_format = "%(levelname)-8s"

        # Different formats for different levels
        if record.levelno >= logging.ERROR:
            fmt = (
                f"{level_format} | "
                "%(asctime)s | "
                "%(name)s | "
                "%(filename)s:%(lineno)d | "
                "%(message)s"
            )
        else:
            fmt = f"{level_format} | %(asctime)s | %(name)s | %(message)s"

        formatter = logging.Formatter(fmt=fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


@lru_cache
def get_logger(name: str = "serviceup") -> logging.Logger:
    """Get or create a configured logger instance (Singleton pattern)
    Uses LRU cache to ensure only one logger per name

    Args:
        name: Logger name (default: "serviceup")

    Returns:
        logging.Logger: Configured logger instance
    """
    settings = get_settings()
    logger = logging.getLogger(name)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, settings.app.log_level))

    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(LogFormatter(use_colors=True))
    logger.addHandler(console_handler)

    # File handler (rotating)
    log_dir = get_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{name}.log"

    try:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(LogFormatter(use_colors=False))
        logger.addHandler(file_handler)
    except Exception as e:
        logger.warning(f"Could not create file handler: {e}")

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def get_module_logger(module_name: str) -> logging.Logger:
    """Get logger for a specific module
    Follows DRY principle - single place to configure module loggers

    Args:
        module_name: Usually __name__ of the calling module

    Returns:
        logging.Logger: Module-specific logger
    """
    return get_logger(module_name)


# Convenience functions for common logging patterns (DRY)
def log_debug(message: str, **kwargs) -> None:
    """Log debug message"""
    logger = get_logger()
    logger.debug(message, extra=kwargs if kwargs else None)


def log_info(message: str, **kwargs) -> None:
    """Log info message"""
    logger = get_logger()
    logger.info(message, extra=kwargs if kwargs else None)


def log_warning(message: str, **kwargs) -> None:
    """Log warning message"""
    logger = get_logger()
    logger.warning(message, extra=kwargs if kwargs else None)


def log_error(message: str, exc: Exception | None = None, **kwargs) -> None:
    """Log error message with optional exception"""
    logger = get_logger()
    if exc:
        logger.error(f"{message}: {exc}", extra=kwargs if kwargs else None)
    else:
        logger.error(message, extra=kwargs if kwargs else None)


def log_critical(message: str, exc: Exception | None = None, **kwargs) -> None:
    """Log critical message"""
    logger = get_logger()
    if exc:
        logger.critical(f"{message}: {exc}", extra=kwargs if kwargs else None)
    else:
        logger.critical(message, extra=kwargs if kwargs else None)


@contextmanager
def log_execution_time(operation_name: str, logger: logging.Logger | None = None):
    """Context manager to log execution time of code blocks
    Usage:
        with log_execution_time("database_query"):
            # your code here
    """
    if logger is None:
        logger = get_logger()

    start_time = time.perf_counter()
    logger.debug(f"Starting: {operation_name}")

    try:
        yield
        elapsed = time.perf_counter() - start_time
        logger.debug(f"Completed: {operation_name} in {elapsed:.4f}s")
    except Exception as e:
        elapsed = time.perf_counter() - start_time
        logger.exception(f"Failed: {operation_name} after {elapsed:.4f}s - {e}")
        raise


# Export public API
__all__ = [
    "LogFormatter",
    "get_logger",
    "get_module_logger",
    "log_critical",
    "log_debug",
    "log_error",
    "log_execution_time",
    "log_info",
    "log_warning",
]
