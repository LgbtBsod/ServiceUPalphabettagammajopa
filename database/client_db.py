#!/usr/bin/env python3

"""Класс для работы с историей ремонтов клиентов."""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class ClientDatabaseManager:
    """Менеджер истории клиентов — единая БД, без отдельных файлов на клиента.

    Раньше этот класс дополнительно (dual-write) писал каждую запись истории
    ЕЩЁ и в отдельный `.db`-файл на клиента (`DBClients/<client>.db`) "для
    обратной совместимости", и `get_client_stats()` читал ТОЛЬКО из такого
    файла (даже не пытаясь заглянуть в основную БД) — то есть у приложения
    реально было ДВЕ базы данных одновременно, вопреки правилу проекта
    "одна БД, разные таблицы". Старые файлы уже перенесены в основную БД
    автоматически при старте приложения (`Database.migrate_client_dbs()`,
    вызывается из gui/main_window.py и безопасен при повторных запусках —
    проверяет по телефону). См. AUDIT_REPORT_v21.md и обсуждение в сессии.

    Методы сохраняют обратную совместимость по сигнатурам — device_form.py,
    client_history.py и pwa/server.py вызывают их как раньше, но теперь
    единственный источник данных — основная БД (self._main_db).
    """

    def __init__(self, main_db=None):
        self._main_db = main_db  # database.sqlalchemy_database.Database

    def add_repair_to_client_history(
        self, client_name: str, client_phone: str, device_data: dict[str, Any]
    ) -> bool:
        """Добавляет/обновляет запись ремонта в истории клиента (основная БД)."""
        if not client_name or not client_phone:
            logger.warning("Нет имени или телефона клиента для сохранения истории")
            return False
        if self._main_db is None:
            logger.error("ClientDatabaseManager без ссылки на основную БД")
            return False

        try:
            from utils.formatters import normalize_phone

            phone = normalize_phone(client_phone)
            client_id = self._main_db.get_or_create_client(client_name, phone)
            if not client_id:
                logger.error(f"Не удалось получить/создать клиента: {client_name}")
                return False

            order_number = device_data.get("order_number", "")
            device_id = self._main_db.get_device_id_by_order_number(order_number)
            self._main_db.add_to_repair_history_main(client_id, device_id, device_data)
            logger.info(
                f"Заказ {order_number} сохранён в истории клиента {client_name}"
            )
            return True
        except Exception as e:
            logger.exception(f"Ошибка добавления в историю клиента: {e}")
            return False

    def update_repair_in_history(
        self,
        client_name: str,
        client_phone: str,
        order_number: str,
        device_data: dict[str, Any],
    ) -> bool:
        """Обновление записи в истории клиента (add_to_repair_history_main
        сам делает upsert по client_id+order_number)."""
        try:
            return self.add_repair_to_client_history(
                client_name, client_phone, device_data
            )
        except Exception as e:
            logger.exception(f"Ошибка обновления записи в истории: {e}")
            return False

    def get_client_history(
        self, client_name: str, client_phone: str
    ) -> list[dict[str, Any]]:
        """Получение истории ремонтов клиента из основной БД."""
        if self._main_db is None:
            return []
        try:
            from utils.formatters import normalize_phone

            phone = normalize_phone(client_phone)
            return self._main_db.get_client_history_main(client_name, phone)
        except Exception as e:
            logger.exception(f"Ошибка получения истории клиента: {e}")
            return []

    def get_client_stats(self, client_name: str, client_phone: str) -> dict[str, Any]:
        """Статистика клиента: базовые поля из Client (total_orders/
        completed_orders/total_spent) + declined_orders/photo_count/avg_price,
        досчитанные из истории (эти поля не хранятся отдельной колонкой)."""
        empty_stats = {
            "total_orders": 0,
            "completed_orders": 0,
            "declined_orders": 0,
            "total_spent": 0,
            "first_order_date": datetime.now().strftime("%Y-%m-%d"),
            "last_order_date": datetime.now().strftime("%Y-%m-%d"),
            "favorite_device": "—",
            "photo_count": 0,
            "avg_price": 0,
        }
        if self._main_db is None:
            return empty_stats

        try:
            from domain.constants import STATUS_REFUSED
            from utils.formatters import normalize_phone

            phone = normalize_phone(client_phone)
            stats = self._main_db.get_client_stats_main(client_name, phone)
            if not stats:
                return empty_stats

            history = self.get_client_history(client_name, client_phone)
            declined_orders = sum(
                1 for r in history if r.get("status") == STATUS_REFUSED
            )
            photo_count = sum(
                len(r.get("photos", "").split(","))
                for r in history
                if r.get("photos")
            )

            completed = stats.get("completed_orders", 0) or 0
            total_spent = stats.get("total_spent", 0) or 0
            avg_price = total_spent / completed if completed > 0 else 0

            return {
                **empty_stats,
                **stats,
                "declined_orders": declined_orders,
                "photo_count": photo_count,
                "avg_price": avg_price,
            }
        except Exception as e:
            logger.exception(f"Ошибка получения статистики клиента: {e}")
            return empty_stats
