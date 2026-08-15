"""Модуль доступа к данным (Data Access Layer)

ЕДИНСТВЕННЫЙ способ работы с БД в приложении.
Реализует паттерны: Repository, Unit of Work, CQRS Query Handler.
Все SQL-запросы инкапсулированы внутри этого модуля.
"""

from infrastructure.db_access.manager import (
    Base,
    Command,
    DataAccessManager,
    DatabaseConfig,
    Query,
    QueryResult,
    db_execute_command,
    db_execute_query,
    db_session,
    db_unit_of_work,
    get_db_access,
    initialize_db_access,
    reset_db_access,
)

__all__ = [
    "Base",
    "Command",
    "DataAccessManager",
    "DatabaseConfig",
    "Query",
    "QueryResult",
    "db_execute_command",
    "db_execute_query",
    "db_session",
    "db_unit_of_work",
    "get_db_access",
    "initialize_db_access",
    "reset_db_access",
]
