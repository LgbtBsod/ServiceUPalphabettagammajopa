"""Application Layer - Use Cases и сервисы приложений.

Слой приложения содержит бизнес-логику использования (use cases),
которая координирует работу доменных сервисов и репозиториев.

Принципы:
- SRP: каждый use case решает одну задачу
- Dependency Injection: зависимости внедряются через конструктор
- Transaction Script: управление транзакциями через Unit of Work
"""

from .backup_services import BackupService
from .client_services import ClientAppService
from .order_services import OrderAppService
from .reporting_services import ReportingService

__version__ = "17.0"

__all__ = [
    "BackupService",
    "ClientAppService",
    "OrderAppService",
    "ReportingService",
]
