#!/usr/bin/env python3

"""Класс для работы с базами данных клиентов"""

import logging
import os
import re
import sqlite3
from datetime import datetime
from typing import Any

from config import CLIENTS_DB_DIR

from .db_config import get_db_config

logger = logging.getLogger(__name__)

DB_CONFIG = get_db_config()


class ClientDatabaseManager:
    """Менеджер для работы с историей клиентов.

    Начиная с оптимизации БД, все данные хранятся в основной БД
    (таблицы clients + repair_history_main). Старые отдельные .db файлы
    в DBClients/ мигрируются автоматически и больше не используются.

    Методы сохраняют обратную совместимость — device_form.py и
    client_history.py вызывают те же методы (add_repair_to_client_history,
    get_client_history и т.д.), но внутри работают с основной БД.
    """

    def __init__(self, main_db=None):
        self.clients_db_dir = CLIENTS_DB_DIR
        self.create_clients_db_directory()
        self._main_db = main_db  # ссылка на основную Database (если есть)

    def create_clients_db_directory(self):
        """Создание директории для баз данных клиентов"""
        try:
            if not os.path.exists(self.clients_db_dir):
                os.makedirs(self.clients_db_dir)
                logger.info(f"Создана для БД клиентов: {self.clients_db_dir}")
        except Exception as e:
            logger.exception(f"Ошибка создания для БД клиентов: {e}")

    def get_client_db_path(self, client_name: str, client_phone: str) -> str:
        """Получение пути к базе данных клиента.

        Имя файла нормализуется (lower-case, удаление пробелов/знаков),
        чтобы разные написания одного клиента вели к одному файлу БД —
        иначе терялась история (например, «Иван» + «8999...» и
        «Иван» + «+7 999...» создавали бы разные файлы).
        """
        # Канонизируем телефон к цифрам — это ключевой идентификатор клиента
        from utils.formatters import normalize_phone_digits

        name_part = (client_name or "").strip().lower()
        phone_digits = normalize_phone_digits(client_phone)
        # Оставляем буквы/цифры/дефисы/подчёркивания
        safe_name = re.sub(r"[^\w\-]", "", f"{name_part}_{phone_digits}")[:80]
        if not safe_name or safe_name == "_":
            safe_name = "unknown_client"
        db_path = os.path.join(self.clients_db_dir, f"{safe_name}.db")
        return db_path

    def create_client_database(self, client_name: str, client_phone: str) -> str | None:
        """Создание базы данных для клиента"""
        try:
            db_path = self.get_client_db_path(client_name, client_phone)

            if os.path.exists(db_path):
                return db_path

            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Таблица истории ремонтов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS repair_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT,
                    receipt_date TEXT,
                    completion_date TEXT,
                    device_type TEXT,
                    brand TEXT,
                    model TEXT,
                    serial_number TEXT,
                    defect TEXT,
                    work_items TEXT,
                    status TEXT,
                    total_price TEXT,
                    engineer TEXT,
                    warranty TEXT,
                    notes TEXT,
                    photos TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Таблица статистики клиента
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS client_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    total_orders INTEGER DEFAULT 0,
                    completed_orders INTEGER DEFAULT 0,
                    declined_orders INTEGER DEFAULT 0,
                    total_spent REAL DEFAULT 0,
                    first_order_date TEXT,
                    last_order_date TEXT,
                    favorite_device TEXT,
                    photo_count INTEGER DEFAULT 0,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                """
                INSERT INTO client_stats (total_orders, first_order_date, last_order_date)
                VALUES (0, ?, ?)
            """,
                (now, now),
            )

            conn.commit()
            conn.close()
            logger.info(f"Создана БД клиента: {db_path}")
            return db_path
        except Exception as e:
            logger.exception(f"Ошибка создания БД клиента: {e}")
            import traceback

            traceback.print_exc()
            return None

    def add_repair_to_client_history(
        self, client_name: str, client_phone: str, device_data: dict[str, Any]
    ) -> bool:
        """Добавление ремонта в историю клиента.

        Dual-write: если есть ссылка на основную БД — пишет в clients +
        repair_history_main (новая схема). Также пишет в старый .db файл
        для обратной совместимости.
        """
        try:
            if not client_name or not client_phone:
                logger.warning("Нет имени или телефона клиента для сохранения истории")
                return False

            # --- Новая схема: основная БД ---
            if self._main_db is not None:
                try:
                    from utils.formatters import normalize_phone

                    phone = normalize_phone(client_phone)
                    client_id = self._main_db.get_or_create_client(client_name, phone)
                    if client_id:
                        order_number = device_data.get("order_number", "")
                        cursor = self._main_db.conn.cursor()
                        cursor.execute(
                            "SELECT id FROM devices WHERE order_number = ?",
                            (order_number,),
                        )
                        dev_row = cursor.fetchone()
                        device_id = dev_row["id"] if dev_row else None
                        self._main_db.add_to_repair_history_main(
                            client_id, device_id, device_data
                        )
                except Exception as e:
                    logger.warning(f"Предупреждение Основная БД: {e}")

            # --- Старая схема: отдельный .db файл (для совместимости) ---
            logger.info(
                f"Сохраняем заказ в историю для клиента: {client_name}, тел: {client_phone}"
            )
            logger.debug(
                f"Данные заказа: {device_data.get('order_number')}, статус: {device_data.get('status')}"
            )

            db_path = self.create_client_database(client_name, client_phone)
            if not db_path:
                logger.error(f"Не удалось создать БД для {client_name}")
                return False

            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Проверяем, есть ли уже такой заказ
            order_number = device_data.get("order_number", "")
            cursor.execute(
                "SELECT id FROM repair_history WHERE order_number = ?", (order_number,)
            )
            existing = cursor.fetchone()

            # Запоминаем, был ли это апдейт существующего заказа, чтобы
            # не завышать счётчик total_orders при каждом сохранении.
            is_update = existing is not None

            if existing:
                logger.info(f"Заказ {order_number} уже есть в истории, обновляем...")
                # Обновляем существующую запись
                cursor.execute(
                    """
                    UPDATE repair_history SET
                        receipt_date = ?,
                        completion_date = ?,
                        device_type = ?,
                        brand = ?,
                        model = ?,
                        serial_number = ?,
                        defect = ?,
                        work_items = ?,
                        status = ?,
                        total_price = ?,
                        engineer = ?,
                        warranty = ?,
                        notes = ?,
                        photos = ?
                    WHERE order_number = ?
                """,
                    (
                        device_data.get("receipt_date", ""),
                        device_data.get("completion_date", ""),
                        device_data.get("device_type", ""),
                        device_data.get("brand", ""),
                        device_data.get("model", ""),
                        device_data.get("serial_number", ""),
                        device_data.get("defect", ""),
                        device_data.get("work_items_json", ""),
                        device_data.get("status", ""),
                        device_data.get("total_price", ""),
                        device_data.get("engineer", ""),
                        device_data.get("warranty", ""),
                        device_data.get("notes", ""),
                        device_data.get("photos", ""),
                        order_number,
                    ),
                )
            else:
                # Вставляем новую запись
                cursor.execute(
                    """
                    INSERT INTO repair_history (
                        order_number, receipt_date, completion_date, device_type,
                        brand, model, serial_number, defect, work_items,
                        status, total_price, engineer, warranty, notes, photos
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        device_data.get("order_number", ""),
                        device_data.get("receipt_date", ""),
                        device_data.get("completion_date", ""),
                        device_data.get("device_type", ""),
                        device_data.get("brand", ""),
                        device_data.get("model", ""),
                        device_data.get("serial_number", ""),
                        device_data.get("defect", ""),
                        device_data.get("work_items_json", ""),
                        device_data.get("status", ""),
                        device_data.get("total_price", ""),
                        device_data.get("engineer", ""),
                        device_data.get("warranty", ""),
                        device_data.get("notes", ""),
                        device_data.get("photos", ""),
                    ),
                )
                logger.info(f"Добавлена новая запись для заказа {order_number}")

            # Обновляем статистику
            price_val = 0
            try:
                price_str = device_data.get("total_price", "0")
                if price_str:
                    from utils.formatters import parse_price_to_float

                    price_val = parse_price_to_float(price_str)
            except (ValueError, TypeError):
                pass

            photos_str = device_data.get("photos", "")
            photos_count = len(photos_str.split(",")) if photos_str else 0
            status = device_data.get("status", "")
            receipt_date = device_data.get("receipt_date", "")

            # Получаем любимое устройство
            cursor.execute("""
                SELECT device_type, brand, model, COUNT(*) as cnt
                FROM repair_history
                GROUP BY device_type, brand, model
                ORDER BY cnt DESC
                LIMIT 1
            """)
            favorite = cursor.fetchone()
            favorite_device = ""
            if favorite:
                favorite_device = f"{favorite[1] or ''} {favorite[2] or ''} ({favorite[0] or ''})".strip()
                if not favorite_device:
                    favorite_device = "—"

            # Проверяем, есть ли уже статистика
            cursor.execute("SELECT id FROM client_stats WHERE id = 1")
            if cursor.fetchone():
                if is_update:
                    # При обновлении существующего заказа НЕ инкрементируем
                    # счётчики/суммы (иначе они завышались при каждом сохранении).
                    # Пересчитываем агрегаты из реальной истории.
                    cursor.execute("""
                        SELECT
                            COUNT(*) AS total,
                            SUM(CASE WHEN status='Выдан клиенту' THEN 1 ELSE 0 END) AS completed,
                            SUM(CASE WHEN status='Отказ от ремонта' THEN 1 ELSE 0 END) AS declined
                        FROM repair_history
                    """)
                    agg = cursor.fetchone()
                    cursor.execute(
                        """
                        UPDATE client_stats SET
                            total_orders = ?,
                            completed_orders = ?,
                            declined_orders = ?,
                            last_order_date = ?,
                            favorite_device = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = 1
                    """,
                        (
                            agg[0] or 0,
                            agg[1] or 0,
                            agg[2] or 0,
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            favorite_device,
                        ),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE client_stats SET
                            total_orders = total_orders + 1,
                            completed_orders = completed_orders + CASE WHEN ? = 'Выдан клиенту' THEN 1 ELSE 0 END,
                            declined_orders = declined_orders + CASE WHEN ? = 'Отказ от ремонта' THEN 1 ELSE 0 END,
                            total_spent = total_spent + ?,
                            last_order_date = ?,
                            photo_count = photo_count + ?,
                            favorite_device = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = 1
                    """,
                        (
                            status,
                            status,
                            price_val,
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            photos_count,
                            favorite_device,
                        ),
                    )
            else:
                cursor.execute(
                    """
                    INSERT INTO client_stats (
                        total_orders, completed_orders, declined_orders,
                        total_spent, last_order_date, photo_count,
                        favorite_device, first_order_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        1,
                        1 if status == "Выдан клиенту" else 0,
                        1 if status == "Отказ от ремонта" else 0,
                        price_val,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        photos_count,
                        favorite_device,
                        receipt_date or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )

            conn.commit()
            conn.close()
            logger.info(
                f"Заказ {order_number} успешно сохранен в истории клиента {client_name}"
            )
            return True
        except Exception as e:
            logger.exception(f"Ошибка добавления в историю клиента: {e}")
            import traceback

            traceback.print_exc()
            return False

    def update_repair_in_history(
        self,
        client_name: str,
        client_phone: str,
        order_number: str,
        device_data: dict[str, Any],
    ) -> bool:
        """Обновление записи в истории клиента"""
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
        """Получение истории ремонтов клиента.

        Приоритет — основная БД (если есть мигрированные данные),
        fallback — старый .db файл.
        """
        # --- Новая схема ---
        if self._main_db is not None:
            try:
                from utils.formatters import normalize_phone

                phone = normalize_phone(client_phone)
                history = self._main_db.get_client_history_main(client_name, phone)
                if history:
                    return history
            except Exception as e:
                logger.warning(f"Предупреждение Основная БД get_client_history: {e}")

        # --- Старая схема ---
        try:
            db_path = self.get_client_db_path(client_name, client_phone)
            logger.debug(f"Поиск истории по пути: {db_path}")

            if not os.path.exists(db_path):
                logger.warning(f"Файл БД не существует: {db_path}")
                return []

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM repair_history")
            count = cursor.fetchone()[0]
            logger.info(f"Найдено записей в истории: {count}")

            cursor.execute("""
                SELECT * FROM repair_history
                ORDER BY receipt_date DESC
            """)

            history = [dict(row) for row in cursor.fetchall()]
            conn.close()

            # Выводим для отладки
            for record in history:
                logger.debug(
                    f"  - Заказ {record.get('order_number')}: {record.get('status')}, цена: {record.get('total_price')}"
                )

            return history
        except Exception as e:
            logger.exception(f"Ошибка получения истории клиента: {e}")
            import traceback

            traceback.print_exc()
            return []

    def get_client_stats(self, client_name: str, client_phone: str) -> dict[str, Any]:
        """Получение статистики клиента"""
        try:
            db_path = self.get_client_db_path(client_name, client_phone)
            if not os.path.exists(db_path):
                return {
                    "total_orders": 0,
                    "completed_orders": 0,
                    "declined_orders": 0,
                    "total_spent": 0,
                    "first_order_date": datetime.now().strftime("%Y-%m-%d"),
                    "last_order_date": datetime.now().strftime("%Y-%m-%d"),
                    "favorite_device": "—",
                    "photo_count": 0,
                }

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM client_stats WHERE id = 1")
            stats = cursor.fetchone()
            stats_dict = dict(stats) if stats else {}

            if stats_dict.get("completed_orders", 0) > 0:
                stats_dict["avg_price"] = stats_dict.get(
                    "total_spent", 0
                ) / stats_dict.get("completed_orders", 1)
            else:
                stats_dict["avg_price"] = 0

            conn.close()
            return stats_dict
        except (sqlite3.Error, Exception) as e:
            logger.exception(f"Ошибка получения статистики клиента: {e}")
            return {}
