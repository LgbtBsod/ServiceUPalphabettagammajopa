#!/usr/bin/env python3
"""DictionariesMixin — справочники (типы устройств/бренды/статусы для
комбобоксов). См. AUDIT_REPORT_v25.md, Task T.

get_dict_values() идёт через кэш запросов DatabaseCore (self.core.query_cache,
TTL ~1 час, см. database/db_core.py, Task W) — справочники читаются на
каждой отрисовке фильтров/комбобоксов, а меняются редко (только через
add/update/delete_dict_value ниже, которые сами инвалидируют кэш на запись).
Раньше здесь был свой ad-hoc dict без TTL (self._dict_cache) — переиспользуем
общую инфраструцию DatabaseCore вместо второго независимого кэша."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from database.facade.shared import logger
from database.sqlalchemy_models import DictionaryItem
from domain.constants import DICTIONARY_TYPES

_DICT_CACHE_KEY_PATTERN = "dict_values:*"


def _dict_cache_key(dict_type: str) -> str:
    return f"dict_values:{dict_type}"


class DictionariesMixin:
    """Требует self._session() и self.core.query_cache (DatabaseCore, см.
    database/db_core.py) от финального класса Database."""

    def seed_default_dictionaries(self) -> None:
        """Засевает domain.constants.DICTIONARY_TYPES.default_values в пустые
        справочники — по одному dict_type, только если для него ещё вообще
        нет строк (та же проверка, что и в легаси
        database/db_manager.py::create_tables()).

        Раньше этот сев жил ТОЛЬКО в легаси db_manager.py (сырой sqlite3),
        который сейчас не вызывается на живом пути приложения (см.
        database/__init__.py — единственные потребители db_manager.Database
        это migrate_client_dbs() и tools/migrate_to_sqlalchemy.py, оба
        одноразовые миграционные инструменты). На свежей БД, созданной
        текущим SQLAlchemy-движком (SQLiteEngine.create_tables()), таблица
        `dictionaries` создаётся пустой — ни бренды, ни типы устройств, ни
        инженеры никогда не засеивались, так что у любой НОВОЙ установки
        (не унаследовавшей уже заполненный файл вроде текущего
        data/serviceup.db) все выпадающие списки справочников пустые в
        обоих GUI и в PWA (эмпирически подтверждено: get_dict_values()
        на только что созданной БД возвращает [] для каждого dict_type).
        Вызывается один раз при конструировании Database() — как и
        engine.create_tables(), дешёвая проверка COUNT на dict_type, не
        перезаписывает то, что пользователь уже сам заполнил/очистил."""
        try:
            seeded_types: list[str] = []
            with self._session() as s:
                for dict_type, config in DICTIONARY_TYPES.items():
                    exists = s.execute(
                        select(func.count()).select_from(DictionaryItem).where(
                            DictionaryItem.dict_type == dict_type
                        )
                    ).scalar()
                    if exists:
                        continue
                    for i, value in enumerate(config.get("default_values", [])):
                        s.add(
                            DictionaryItem(
                                dict_type=dict_type, value=value, sort_order=i
                            )
                        )
                    seeded_types.append(dict_type)
                s.commit()
            # Обычно вызывается один раз при __init__, до первого
            # get_dict_values() — кэш ещё пуст, инвалидация не нужна. Но
            # если seed_default_dictionaries() вызвать повторно на уже
            # живом Database() (например, после ручной очистки категории
            # до нуля строк), не инвалидировав кэш, get_dict_values()
            # молча вернул бы устаревшее закэшированное значение (обычно
            # []) вместо только что вставленных строк.
            for dict_type in seeded_types:
                self._invalidate_dict_cache(dict_type)
        except Exception as e:
            logger.error(f"Ошибка сева справочников по умолчанию: {e}", exc_info=True)

    def get_dict_values(self, dict_type: str) -> list[str]:
        cache_key = _dict_cache_key(dict_type)
        cached = self.core.query_cache.get(cache_key)
        if cached is not None:
            return cached
        with self._session() as s:
            rows = s.execute(
                select(DictionaryItem.value)
                .where(DictionaryItem.dict_type == dict_type)
                .order_by(DictionaryItem.sort_order)
            ).scalars().all()
            values = list(rows)
            self.core.query_cache.set(cache_key, values)
            return values

    def _invalidate_dict_cache(self, dict_type: str | None = None) -> None:
        if dict_type:
            self.core.query_cache.delete(_dict_cache_key(dict_type))
        else:
            self.core.query_cache.invalidate_pattern(_DICT_CACHE_KEY_PATTERN)

    def get_all_dict_items(self, dict_type: str) -> list[dict[str, Any]]:
        with self._session() as s:
            rows = s.execute(
                select(DictionaryItem)
                .where(DictionaryItem.dict_type == dict_type)
                .order_by(DictionaryItem.sort_order)
            ).scalars().all()
            return [
                {
                    "id": r.id,
                    "value": r.value,
                    "sort_order": r.sort_order,
                    "additional_info": r.additional_info,
                }
                for r in rows
            ]

    def add_dict_value(
        self, dict_type: str, value: str, additional_info: str = ""
    ) -> bool:
        try:
            with self._session() as s:
                max_order = s.execute(
                    select(func.max(DictionaryItem.sort_order)).where(
                        DictionaryItem.dict_type == dict_type
                    )
                ).scalar()
                item = DictionaryItem(
                    dict_type=dict_type,
                    value=value,
                    sort_order=(max_order or 0) + 1,
                    additional_info=additional_info,
                )
                s.add(item)
                s.commit()
            self._invalidate_dict_cache(dict_type)
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления в словарь: {e}", exc_info=True)
            return False

    def update_dict_value(
        self, item_id: int, value: str, additional_info: str = ""
    ) -> bool:
        try:
            with self._session() as s:
                item = s.get(DictionaryItem, item_id)
                if item is None:
                    return False
                item.value = value
                item.additional_info = additional_info
                s.commit()
            self._invalidate_dict_cache()
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления словаря: {e}", exc_info=True)
            return False

    def delete_dict_value(self, item_id: int) -> bool:
        try:
            with self._session() as s:
                item = s.get(DictionaryItem, item_id)
                if item is None:
                    return False
                s.delete(item)
                s.commit()
            self._invalidate_dict_cache()
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления из словаря: {e}", exc_info=True)
            return False
