"""
Application Layer - Use Cases и сервисы приложений.

Слой приложения содержит бизнес-логику использования (use cases),
которая координирует работу доменных сервисов и репозиториев.

Принципы:
- SRP: каждый use case решает одну задачу
- Dependency Injection: зависимости внедряются через конструктор
- Transaction Script: управление транзакциями через Unit of Work
"""

from .order_services import OrderAppService
from .client_services import ClientAppService
from .reporting_services import ReportingService
from .backup_services import BackupService

__version__ = "17.0"

__all__ = [
    'OrderAppService',
    'ClientAppService',
    'ReportingService',
    'BackupService',
]
