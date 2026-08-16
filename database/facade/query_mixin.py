#!/usr/bin/env python3
"""QueryMixin — структурированный запрос к БД вместо сырого SQL
(see AUDIT_REPORT_v25.md, Task T)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from database.facade.shared import FILTER_OPERATORS, QUERYABLE_MODELS, QueryError, resolve_queryable_model


class QueryMixin:
    """Требует self._session() от финального класса Database."""

    def query(
        self,
        table: str,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        order_desc: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Структурированный запрос к БД вместо сырого SQL.

        Модуль передаёт ЧТО хочет получить (таблица из белого списка +
        фильтры/сортировка/лимит как данные), а не текст SQL — этот метод
        сам строит безопасный, параметризованный запрос через SQLAlchemy
        под текущий движок (SQLite/Postgres). Любая некорректная часть
        запроса (неизвестная таблица/колонка/оператор) кидает QueryError
        ДО обращения к БД.

        Args:
            table: имя таблицы из facade.shared.QUERYABLE_MODELS.
            filters: {"колонка": значение} — равенство, или
                {"колонка": {"оператор": значение, ...}} — один/несколько
                из facade.shared.FILTER_OPERATORS (eq/ne/gt/gte/lt/lte/in/like).
            order_by: имя колонки для сортировки.
            order_desc: сортировка по убыванию (по умолчанию — по возрастанию).
            limit: максимум строк (обязан быть положительным int, если задан).

        Returns:
            Список строк как dict (через Base.to_dict() каждой модели).

        Raises:
            QueryError: неизвестная таблица/колонка/оператор/некорректный limit.
        """
        model = resolve_queryable_model(table)

        def _column(name: str):
            if name not in model.__table__.columns:
                raise QueryError(f"Неизвестная колонка {name!r} в таблице {table!r}")
            return getattr(model, name)

        with self._session() as s:
            stmt = select(model)

            for column_name, condition in (filters or {}).items():
                column = _column(column_name)
                if isinstance(condition, dict):
                    for op, value in condition.items():
                        op_fn = FILTER_OPERATORS.get(op)
                        if op_fn is None:
                            raise QueryError(
                                f"Неизвестный оператор фильтра {op!r} "
                                f"(доступны: {sorted(FILTER_OPERATORS)})"
                            )
                        stmt = stmt.where(op_fn(column, value))
                else:
                    stmt = stmt.where(column == condition)

            if order_by is not None:
                order_column = _column(order_by)
                stmt = stmt.order_by(
                    order_column.desc() if order_desc else order_column.asc()
                )

            if limit is not None:
                if not isinstance(limit, int) or limit <= 0:
                    raise QueryError(f"Некорректный limit: {limit!r}")
                stmt = stmt.limit(limit)

            rows = s.execute(stmt).scalars().all()
            return [row.to_dict() for row in rows]

    def get_queryable_schema(self) -> dict[str, list[str]]:
        """Возвращает белый список таблиц, доступных через query(), с
        перечнем их колонок — чтобы модуль мог сам понять, что можно
        спросить у db_access, не заглядывая в код database/facade/*.

        Пример: core.call_module_method('db_access', 'get_queryable_schema')
        -> {'devices': ['id', 'order_number', 'status', ...], 'clients': [...], ...}
        """
        return {
            table: [c.name for c in model.__table__.columns]
            for table, model in QUERYABLE_MODELS.items()
        }
