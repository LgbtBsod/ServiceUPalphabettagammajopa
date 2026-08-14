"""
Модуль доступа к данным (Data Access Layer)

ЕДИНСТВЕННЫЙ способ работы с БД в приложении.
Реализует паттерны: Repository, Unit of Work, CQRS Query Handler.
Все SQL-запросы инкапсулированы внутри этого модуля.
"""

from infrastructure.db_access.manager import (
    DatabaseConfig,
    DataAccessManager,
    Command,
    Query,
    QueryResult,
    get_db_access,
    initialize_db_access,
    reset_db_access,
    db_session,
    db_unit_of_work,
    db_execute_command,
    db_execute_query,
    Base,
)

__all__ = [
    'DatabaseConfig',
    'DataAccessManager',
    'Command',
    'Query',
    'QueryResult',
    'get_db_access',
    'initialize_db_access',
    'reset_db_access',
    'db_session',
    'db_unit_of_work',
    'db_execute_command',
    'db_execute_query',
    'Base',
]