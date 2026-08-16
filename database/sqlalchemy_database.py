#!/usr/bin/env python3
"""SQLAlchemy-backed drop-in замена database.db_manager.Database.

Тот же публичный API (имена и сигнатуры методов, форма возвращаемых
словарей), что и у легаси-класса на сыром sqlite3 — но персистентность
идёт через IDatabaseEngine (database/engines/), выбираемый по DB_TYPE.
Это позволяет gui/main_window.py и pwa/server.py получать этот класс
через Kernel DI без единой правки в местах вызова self.db.method(...).

Также добавляет Calculation Offloading: calculate(name, **params) — тяжёлые
агрегации (просроченные заказы, статистика дашборда) считает SQL, а не Python.

Реализация разбита на mixin'ы (database/facade/*_mixin.py) по разделу
ответственности — устройства, словари, вычисления, структурированные
запросы, блокировки, финансы, дочерние таблицы, клиенты — тем же способом,
каким core/base.py собирает BaseService из LoggableMixin/
ExceptionHandlingMixin/... Этот файл — только "сборка" + жизненный цикл
сессии/движка; ни один внешний вызов self.db.method(...) не изменился,
имена и сигнатуры методов остались ровно теми же, см. AUDIT_REPORT_v25.md
(Task T).

Управление подключением (движок, guard от дублирующего Database() на тот же
файл, кэш запросов) вынесено в database/db_core.py::DatabaseCore — Database
получает готовый self.core, а не строит инфраструктуру сам, см.
AUDIT_REPORT_v25.md (Task W). self.engine/self._session() ниже — тонкие
проброс-методы к self.core, оставлены ради нуля правок в 8 mixin'ах и
внешнем коде (gui/pwa/plugins), которые уже вызывают self._session()/
self.db.engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from database.db_core import DatabaseCore, DuplicateDatabaseConnectionError
from database.facade.calculate_mixin import CalculateMixin
from database.facade.child_records_mixin import ChildRecordsMixin
from database.facade.clients_mixin import ClientsMixin
from database.facade.devices_mixin import DevicesMixin
from database.facade.dictionaries_mixin import DictionariesMixin
from database.facade.finance_mixin import FinanceMixin
from database.facade.locks_mixin import LocksMixin
from database.facade.query_mixin import QueryMixin
from database.facade.shared import (
    DEVICE_UPDATE_FIELDS,
    OVERDUE_THRESHOLD_DAYS,
    OptimisticLockError,
    QueryError,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from database.engines.base import IDatabaseEngine

# Реэкспорт для обратной совместимости — весь остальной код (bootstrap.py,
# pwa/server.py, gui/dialogs/device_form.py, tests/*) импортирует эти имена
# отсюда, из database.sqlalchemy_database, а не из database.facade.shared
# или database.db_core; перенос реализации не должен требовать правки ни
# одного места импорта.
__all__ = [
    "DEVICE_UPDATE_FIELDS",
    "OVERDUE_THRESHOLD_DAYS",
    "Database",
    "DuplicateDatabaseConnectionError",
    "OptimisticLockError",
    "QueryError",
]


class Database(
    DevicesMixin,
    DictionariesMixin,
    CalculateMixin,
    QueryMixin,
    LocksMixin,
    FinanceMixin,
    ChildRecordsMixin,
    ClientsMixin,
):
    """Drop-in замена database.db_manager.Database на SQLAlchemy."""

    def __init__(self, db_engine: IDatabaseEngine | None = None):
        # Вся инфраструктура подключения (движок, connection-guard, кэш
        # запросов) — в DatabaseCore, см. database/db_core.py, Task W.
        # DuplicateDatabaseConnectionError (если файл уже занят) долетает
        # отсюда наружу без изменений — конструирование DatabaseCore
        # происходит синхронно внутри этого __init__.
        self.core = DatabaseCore(db_engine)

    @property
    def engine(self) -> IDatabaseEngine:
        """Публичный доступ к движку — нужен, например, плагинам, которым
        требуется своя SQLAlchemy-сессия (см. plugins/clients/repository.py)."""
        return self.core.engine

    def _session(self) -> Session:
        return self.core.session()

    def refresh_query_cache(self) -> int:
        """Ручной сброс кэша запросов (кнопка "Обновить кэш" в Базис-
        кокпите) — см. DatabaseCore.refresh_query_cache(). Возвращает
        количество очищенных записей."""
        return self.core.refresh_query_cache()

    def close(self) -> None:
        """Совместимость с legacy API — сессии открываются и закрываются
        по одной на вызов, отдельного постоянного соединения нет."""
