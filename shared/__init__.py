"""
Shared module - общие типы, константы и утилиты для всех модулей.

Single Source of Truth (SSOT) для общих определений.
Следует принципу DRY - не дублировать определения в разных модулях.
"""

from shared.kernel import (
    # Enums
    OrderStatus,
    Priority,
    ClientStatus,
    DeviceType,
    PaymentMethod,
    NotificationType,
    # Type Aliases
    Money,
    PhoneNumber,
    Email,
    UUIDStr,
    # Protocols
    Identifiable,
    Serializable,
    Auditable,
    Repository,
    UnitOfWork,
    EventHandler,
    NotificationSender,
    # Value Objects
    MoneyValue,
    DateRange,
    Address,
    # Constants
    Constants,
    # Utilities
    generate_uuid,
    generate_uuid_str,
    now_utc,
    sanitize_string,
    safe_decimal,
)

from shared.logging_config import (
    get_logger,
    get_module_logger,
    log_debug,
    log_info,
    log_warning,
    log_error,
    log_critical,
    log_execution_time,
    LogFormatter,
)

from shared.async_utils import (
    AsyncExecutor,
    get_executor,
    async_wrap,
    sync_unwrap,
    async_timeout,
    gather_with_concurrency,
    run_in_background,
    batch_process,
)

__version__ = "20.0"

__all__ = [
    # Enums
    'OrderStatus',
    'Priority',
    'ClientStatus',
    'DeviceType',
    'PaymentMethod',
    'NotificationType',
    # Type Aliases
    'Money',
    'PhoneNumber',
    'Email',
    'UUIDStr',
    # Protocols
    'Identifiable',
    'Serializable',
    'Auditable',
    'Repository',
    'UnitOfWork',
    'EventHandler',
    'NotificationSender',
    # Value Objects
    'MoneyValue',
    'DateRange',
    'Address',
    # Constants
    'Constants',
    # Utilities
    'generate_uuid',
    'generate_uuid_str',
    'now_utc',
    'sanitize_string',
    'safe_decimal',
    # Logging
    'get_logger',
    'get_module_logger',
    'log_debug',
    'log_info',
    'log_warning',
    'log_error',
    'log_critical',
    'log_execution_time',
    'LogFormatter',
    # Async utilities
    'AsyncExecutor',
    'get_executor',
    'async_wrap',
    'sync_unwrap',
    'async_timeout',
    'gather_with_concurrency',
    'run_in_background',
    'batch_process',
]
