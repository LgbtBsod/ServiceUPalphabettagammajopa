"""Shared module - общие типы, константы и утилиты для всех модулей.

Single Source of Truth (SSOT) для общих определений.
Следует принципу DRY - не дублировать определения в разных модулях.
"""

from shared.async_utils import (
    AsyncExecutor,
    async_timeout,
    async_wrap,
    batch_process,
    gather_with_concurrency,
    get_executor,
    run_in_background,
    sync_unwrap,
)
from shared.kernel import (
    Address,
    Auditable,
    ClientStatus,
    # Constants
    Constants,
    DateRange,
    DeviceType,
    Email,
    EventHandler,
    # Protocols
    Identifiable,
    # Type Aliases
    Money,
    # Value Objects
    MoneyValue,
    NotificationSender,
    NotificationType,
    # Enums
    OrderStatus,
    PaymentMethod,
    PhoneNumber,
    Priority,
    Repository,
    Serializable,
    UnitOfWork,
    UUIDStr,
    # Utilities
    generate_uuid,
    generate_uuid_str,
    now_utc,
    safe_decimal,
    sanitize_string,
)
from shared.logging_config import (
    LogFormatter,
    get_logger,
    get_module_logger,
    log_critical,
    log_debug,
    log_error,
    log_execution_time,
    log_info,
    log_warning,
)

__version__ = "20.0"

__all__ = [
    "Address",
    # Async utilities
    "AsyncExecutor",
    "Auditable",
    "ClientStatus",
    # Constants
    "Constants",
    "DateRange",
    "DeviceType",
    "Email",
    "EventHandler",
    # Protocols
    "Identifiable",
    "LogFormatter",
    # Type Aliases
    "Money",
    # Value Objects
    "MoneyValue",
    "NotificationSender",
    "NotificationType",
    # Enums
    "OrderStatus",
    "PaymentMethod",
    "PhoneNumber",
    "Priority",
    "Repository",
    "Serializable",
    "UUIDStr",
    "UnitOfWork",
    "async_timeout",
    "async_wrap",
    "batch_process",
    "gather_with_concurrency",
    # Utilities
    "generate_uuid",
    "generate_uuid_str",
    "get_executor",
    # Logging
    "get_logger",
    "get_module_logger",
    "log_critical",
    "log_debug",
    "log_error",
    "log_execution_time",
    "log_info",
    "log_warning",
    "now_utc",
    "run_in_background",
    "safe_decimal",
    "sanitize_string",
    "sync_unwrap",
]
