"""Database Agnostic Layer — реальный DB-engine слой.

Единственная абстракция, за которой прячется конкретная СУБД. Выбор движка
делается через уже существующий database.db_config.get_db_config()
(читает DB_TYPE из .env) — здесь НЕ добавляется ещё один конфиг.

Использование:
    from database.engines import get_database_engine

    db_engine = get_database_engine()          # выбор по DB_TYPE из .env
    engine = db_engine.get_engine()             # SQLAlchemy Engine
    session = db_engine.get_session_factory()()  # новая сессия
"""

from __future__ import annotations

import threading

from database.engines.base import IDatabaseEngine
from database.engines.postgresql_engine import PostgreSQLEngine
from database.engines.sqlite_engine import SQLiteEngine

__all__ = [
    "IDatabaseEngine",
    "PostgreSQLEngine",
    "SQLiteEngine",
    "create_engine_for",
    "get_database_engine",
]


def create_engine_for(config) -> IDatabaseEngine:
    """Создаёт реализацию IDatabaseEngine под конкретный DatabaseConfig.

    Args:
        config: database.db_config.DatabaseConfig (db_type определяет выбор).

    Returns:
        Готовый к использованию IDatabaseEngine.

    Raises:
        ValueError: если db_type не поддерживается ни одной реализацией.
    """
    from database.db_config import DatabaseType

    if config.db_type == DatabaseType.SQLITE:
        return SQLiteEngine(config)
    if config.db_type == DatabaseType.POSTGRESQL:
        return PostgreSQLEngine(config)
    raise ValueError(
        f"Нет реализации IDatabaseEngine для db_type={config.db_type!r}. "
        "Поддерживаются: sqlite, postgresql."
    )


_engine_instance: IDatabaseEngine | None = None
_engine_lock = threading.Lock()


def get_database_engine(force_reload: bool = False) -> IDatabaseEngine:
    """Возвращает singleton IDatabaseEngine, выбранный по DB_TYPE (.env).

    Args:
        force_reload: пересоздать движок (например, после смены .env в тестах).

    DatabaseCore.__init__ вызывает это на каждом обычном пути построения
    Database() — раньше здесь была unsync check-then-act проверка
    (`if _engine_instance is None or force_reload: ...`), и два потока,
    конкурентно конструирующих DatabaseCore для одного файла (GUI-поток vs.
    поток запуска PWA-сервера), могли оба увидеть _engine_instance is None
    и создать по отдельному SQLAlchemy Engine/пулу соединений на один и тот
    же файл, молча осиротив один из них (без .dispose()) — workflow-найденный
    баг. force_reload усложняет double-checked locking (нужно пересоздавать
    даже когда instance уже есть), поэтому вместо внешней unlocked
    fast-path проверки тело целиком выполняется под локом — вызывается
    редко (раз на конструирование DatabaseCore), так что цена лока
    незначительна.
    """
    global _engine_instance

    from database.db_config import get_db_config

    with _engine_lock:
        if _engine_instance is None or force_reload:
            if _engine_instance is not None:
                _engine_instance.dispose()
            _engine_instance = create_engine_for(get_db_config())

        return _engine_instance


def reset_database_engine() -> None:
    """Сбрасывает singleton движка (для тестов)."""
    global _engine_instance

    with _engine_lock:
        if _engine_instance is not None:
            _engine_instance.dispose()
        _engine_instance = None
