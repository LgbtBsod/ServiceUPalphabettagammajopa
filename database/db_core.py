#!/usr/bin/env python3
"""DatabaseCore — "ядро БД": управление жизненным циклом подключения
(движок, сессии, guard от повторного подключения к тому же файлу в обход
core.get_db_access()) и сквозной инфраструктурой БД (кэш запросов; задел под
будущее расширение — например health-check движка), отдельно от Database
(бизнес-CRUD в database/facade/*_mixin.py).

Та же идея, что и core.kernel.ServiceUpCore для приложения в целом (Kernel/
Mediator: DI, потоки, общий кэш, события) — только в масштабе БД. У нашей
БД оказалось достаточно СВОИХ задач управления и расширения (не только
держать движок, но и кэшировать запросы, а строение растёт — миграции между
БД в database/db_migration_tool.py, engines/ уже отдельный слой), чтобы не
размазывать их по __init__ facade-класса Database и его mixin'ам, а выделить
в отдельный слой ниже facade. Database получает готовый DatabaseCore, а не
строит свою инфраструктуру сам — тот же принцип "инфраструктура отдельно от
бизнес-методов", что уже проведён между database/engines/ (IDatabaseEngine)
и database/facade/*_mixin.py. См. AUDIT_REPORT_v25.md, Task W."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from core.module_manager import ModuleCache

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from database.engines.base import IDatabaseEngine

logger = logging.getLogger(__name__)

# Кэш запросов — для "постоянных" данных (справочники и т.п., НЕ заказы/
# финансы — те остаются всегда живыми), TTL ~1 час. Общий на процесс, а не
# per-пользователь: DatabaseCore — Kernel-синглтон (один Database на процесс,
# см. _claimed_connection_strings ниже), которым пользуются и GUI, и
# PWA-поток в одном и том же процессе — аналог серверного query cache (SAP
# HANA-style result cache), а не приватного кэша на клиента/сессию: запрос
# от одного потребителя населяет кэш, следующий вызов от ЛЮБОГО другого
# потребителя (другой поток, другой GUI-вызов) переиспользует его, если тот
# ещё не истёк.
QUERY_CACHE_TTL_SECONDS = 3600

_claimed_connection_strings: set[str] = set()
# Этот guard существует именно для того, чтобы поймать конкурентное
# конструирование Database() из GUI-потока и PWA-потока на один и тот же
# файл (см. докстринг DatabaseCore ниже) — но раньше сам был unsync
# check-then-act ("if conn_str in _claimed_connection_strings: raise ...",
# затем отдельной операцией ".add(conn_str)"), так что не мог поймать
# именно ту гонку, ради которой был написан: два потока могли оба увидеть
# conn_str отсутствующим до того, как любой из них дойдёт до .add()
# (workflow-найденный баг).
_claimed_connection_strings_lock = threading.Lock()


class DuplicateDatabaseConnectionError(RuntimeError):
    """Кто-то создаёт второй Database()/DatabaseCore() на тот же боевой путь
    БД, в обход ядра. Единственный санкционированный способ получить доступ
    к БД — core.get_db_access()."""


class DatabaseCore:
    """Владеет движком БД, фабрикой сессий и кэшем запросов.

    Database (facade) держит один DatabaseCore как self.core и делегирует
    ему всё, что не является бизнес-CRUD: self.core.session() вместо
    самостоятельного управления соединением, self.core.query_cache вместо
    ad-hoc словаря на facade-классе."""

    def __init__(self, db_engine: IDatabaseEngine | None = None):
        if db_engine is None:
            from database.engines import get_database_engine

            db_engine = get_database_engine()
        self._engine = db_engine

        # Guard: не настоящая песочница (Python не даёт capability-based
        # изоляции внутри процесса — код с прямым доступом к sqlite3 всегда
        # может обойти это), но ловит именно то, что реально происходит на
        # практике — случайное создание второго Database() на тот же файл
        # в обход core.get_db_access(), а не гипотетическую атаку. Тестовые
        # инстансы на временных файлах (tempfile.mkstemp) никогда не
        # совпадают с боевым путём, поэтому под guard не попадают.
        try:
            conn_str = str(self._engine.get_engine().url)
        except Exception:
            conn_str = None
        self._conn_str: str | None = conn_str
        if conn_str is not None:
            with _claimed_connection_strings_lock:
                if conn_str in _claimed_connection_strings:
                    raise DuplicateDatabaseConnectionError(
                        f"Database уже создан для {conn_str!r} в этом процессе. "
                        "Используйте core.get_db_access() вместо повторного "
                        "создания Database()."
                    )
                _claimed_connection_strings.add(conn_str)

        self._engine.create_tables()
        self.query_cache = ModuleCache(default_ttl_seconds=QUERY_CACHE_TTL_SECONDS)

    @property
    def engine(self) -> IDatabaseEngine:
        """Публичный доступ к движку — нужен, например, плагинам, которым
        требуется своя SQLAlchemy-сессия (см. plugins/clients/repository.py)."""
        return self._engine

    def session(self) -> Session:
        return self._engine.get_session()

    def refresh_query_cache(self) -> int:
        """Ручной сброс кэша запросов (кнопка "Обновить кэш" в Базис-
        кокпите, gui/main_window_parts/basis_cockpit_mixin.py) — на случай,
        если данные в БД изменились в обход этого процесса (например,
        прямое редактирование справочников через другой инструмент), а не
        только через эти же методы Database, которые и так инвалидируют
        кэш сами при записи. Возвращает количество очищенных записей."""
        size_before = self.query_cache.get_stats()["size"]
        self.query_cache.clear()
        return size_before

    def close(self) -> None:
        """Освобождает claim на conn_str и движок БД.

        Раньше отсутствовал: guard в __init__ добавлял conn_str в
        _claimed_connection_strings навсегда — второй Database() на тот же
        файл (повторный bootstrap.initialize_kernel(), например в тестах
        через core.reset_core()) падал DuplicateDatabaseConnectionError, хотя
        первый экземпляр давно не используется. Идемпотентно: повторный
        вызов — no-op (conn_str уже отсутствует в множестве)."""
        if self._conn_str is not None:
            with _claimed_connection_strings_lock:
                _claimed_connection_strings.discard(self._conn_str)
        try:
            self._engine.dispose()
        except Exception:
            logger.warning("Ошибка при закрытии движка БД", exc_info=True)
