#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Основной класс для работы с базой данных"""

import sqlite3
import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime

from config import DB_PATH
from utils.constants import DICTIONARY_TYPES
from utils.formatters import normalize_phone_digits, parse_price_to_float


# Поля, которые могли добавляться со временем и отсутствуют в старых БД.
# Используется для миграций ALTER TABLE ADD COLUMN.
# Включает REAL-колонки для цен (раньше были только TEXT).
_DEVICE_COLUMNS = {
    'expense': "TEXT DEFAULT '0'",
    'total_price_num': "REAL DEFAULT 0",
    'prepayment_num': "REAL DEFAULT 0",
    'expense_num': "REAL DEFAULT 0",
}


class Database:
    """Класс для работы с базой данных"""

    def __init__(self, db_name: str = None):
        self.db_name = db_name or DB_PATH
        self.conn: Optional[sqlite3.Connection] = None
        self.connect()

    def connect(self) -> None:
        """Подключение к БД.

        При ошибке подключения падает с понятной ошибкой — НЕ подменяем БД
        пустой in-memory копией (это раньше приводило к тихой потере данных
        и созданию пустых бэкапов).
        """
        try:
            self.conn = sqlite3.connect(self.db_name, timeout=10)
            self.conn.row_factory = sqlite3.Row
            # --- Оптимизация производительности ---
            # WAL: параллельные чтение/запись без блокировок (PWA-сервер + десктоп)
            self.conn.execute('PRAGMA journal_mode=WAL')
            # synchronous=NORMAL: быстрее запись, минимальный риск при краше
            self.conn.execute('PRAGMA synchronous=NORMAL')
            # Кеширование страниц в памяти (ускоряет чтение)
            self.conn.execute('PRAGMA cache_size=-6400')  # ~6MB
            self.create_tables()
        except sqlite3.Error as e:
            raise RuntimeError(f"Не удалось подключиться к базе данных ({self.db_name}): {e}") from e

    # ==================== СХЕМА И МИГРАЦИИ ====================

    def create_tables(self) -> None:
        """Создание таблиц и применение миграций"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('PRAGMA foreign_keys = ON')

            # Счетчики
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS counters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    value INTEGER DEFAULT 1
                )
            ''')

            cursor.execute('SELECT value FROM counters WHERE name = ?', ('order_counter',))
            if not cursor.fetchone():
                cursor.execute('INSERT INTO counters (name, value) VALUES (?, ?)', ('order_counter', 1))

            # Устройства/заказы
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT UNIQUE,
                    receipt_date TEXT,
                    completion_date TEXT,
                    device_type TEXT,
                    brand TEXT,
                    model TEXT,
                    serial_number TEXT,
                    defect TEXT,
                    appearance TEXT,
                    completeness TEXT,
                    work_items TEXT,
                    client_name TEXT,
                    client_status TEXT DEFAULT 'Новый',
                    phone TEXT,
                    total_price TEXT,
                    prepayment TEXT,
                    status TEXT DEFAULT 'Диагностика',
                    priority TEXT DEFAULT 'Обычный',
                    engineer TEXT,
                    warranty TEXT,
                    notes TEXT,
                    photos TEXT,
                    expense TEXT DEFAULT '0',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Завершенные ремонты
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS completed_repairs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id INTEGER,
                    order_number TEXT,
                    completion_date TEXT,
                    work_description TEXT,
                    work_price TEXT,
                    engineer TEXT,
                    warranty TEXT,
                    notes TEXT,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE
                )
            ''')

            # Таблица для финансов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS finances (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT,
                    completion_date TEXT,
                    income REAL DEFAULT 0,
                    expense REAL DEFAULT 0,
                    profit REAL DEFAULT 0,
                    UNIQUE(order_number)
                )
            ''')

            # Словари
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dictionaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dict_type TEXT,
                    value TEXT,
                    sort_order INTEGER DEFAULT 0,
                    additional_info TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(dict_type, value)
                )
            ''')

            # Отдельная таблица работ (для быстрых запросов/отчётов).
            # devices.work_items (JSON) остаётся для совместимости — dual-write.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS work_items_db (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id INTEGER NOT NULL,
                    description TEXT,
                    price REAL DEFAULT 0,
                    quantity INTEGER DEFAULT 1,
                    total REAL DEFAULT 0,
                    sort_order INTEGER DEFAULT 0,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE
                )
            ''')

            # Отдельная таблица фото (вместо CSV абсолютных путей в devices.photos).
            # Dual-write: devices.photos остаётся для совместимости.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS photos_db (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id INTEGER NOT NULL,
                    file_path TEXT,
                    filename TEXT,
                    photo_type TEXT DEFAULT 'device',
                    sort_order INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE
                )
            ''')

            # --- Объединённые клиентские данные (вместо отдельных .db файлов) ---
            # Таблица клиентов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    status TEXT DEFAULT 'Новый',
                    total_orders INTEGER DEFAULT 0,
                    completed_orders INTEGER DEFAULT 0,
                    total_spent REAL DEFAULT 0,
                    first_order_date TEXT,
                    last_order_date TEXT,
                    favorite_device TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(phone)
                )
            ''')

            # История ремонтов клиентов (вместо DBClients/*.db)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS repair_history_main (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER,
                    device_id INTEGER,
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
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE
                )
            ''')

            self._run_migrations(cursor)

            for dict_type, config in DICTIONARY_TYPES.items():
                cursor.execute('SELECT COUNT(*) FROM dictionaries WHERE dict_type = ?', (dict_type,))
                if cursor.fetchone()[0] == 0:
                    for i, value in enumerate(config['default_values']):
                        cursor.execute('''
                            INSERT INTO dictionaries (dict_type, value, sort_order) VALUES (?, ?, ?)
                        ''', (dict_type, value, i))

            # --- Индексы для часто используемых полей (IF NOT EXISTS — безопасно) ---
            # Ускоряет фильтрацию, поиск и сортировку в 10-50 раз при больших объёмах
            self._create_indexes(cursor)

            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Ошибка создания таблиц: {e}")

    def _create_indexes(self, cursor) -> None:
        """Создаёт индексы на часто запрашиваемые поля (безопасно при повторах)."""
        indexes = [
            ('idx_devices_status', 'CREATE INDEX IF NOT EXISTS idx_devices_status ON devices(status)'),
            ('idx_devices_client', 'CREATE INDEX IF NOT EXISTS idx_devices_client ON devices(client_name)'),
            ('idx_devices_phone', 'CREATE INDEX IF NOT EXISTS idx_devices_phone ON devices(phone)'),
            ('idx_devices_receipt', 'CREATE INDEX IF NOT EXISTS idx_devices_receipt ON devices(receipt_date)'),
            ('idx_devices_brand', 'CREATE INDEX IF NOT EXISTS idx_devices_brand ON devices(brand)'),
            ('idx_devices_type', 'CREATE INDEX IF NOT EXISTS idx_devices_type ON devices(device_type)'),
            ('idx_devices_priority', 'CREATE INDEX IF NOT EXISTS idx_devices_priority ON devices(priority)'),
            ('idx_dicts_type', 'CREATE INDEX IF NOT EXISTS idx_dicts_type ON dictionaries(dict_type)'),
        ]
        for idx_name, sql in indexes:
            try:
                cursor.execute(sql)
            except sqlite3.Error as e:
                print(f"Индекс {idx_name} не создан: {e}")

    def _run_migrations(self, cursor) -> None:
        """Применение миграций: добавление отсутствующих колонок + заполнение REAL-цен."""
        try:
            cursor.execute("PRAGMA table_info(devices)")
            existing_cols = {row[1] for row in cursor.fetchall()}

            for col, definition in _DEVICE_COLUMNS.items():
                if col not in existing_cols:
                    try:
                        cursor.execute(f"ALTER TABLE devices ADD COLUMN {col} {definition}")
                        print(f"Миграция: добавлена колонка devices.{col}")
                    except sqlite3.Error as e:
                        print(f"Миграция (devices.{col}) не выполнена: {e}")

            # Миграция данных: заполняем REAL-колонки из TEXT-полей
            self._migrate_prices_to_real(cursor)
        except sqlite3.Error as e:
            print(f"Ошибка чтения схемы для миграций: {e}")

    def _migrate_prices_to_real(self, cursor) -> None:
        """Заполняет REAL-колонки цен из существующих TEXT-полей.

        Выполняется один раз при наличии колонок total_price_num (значение 0 = не мигрировано).
        Dual-write: TEXT остаётся для совместимости, REAL — для быстрых расчётов.
        """
        try:
            cursor.execute("PRAGMA table_info(devices)")
            cols = {row[1] for row in cursor.fetchall()}
            if 'total_price_num' not in cols:
                return

            # Мигрируем только если есть записи с total_price_num = 0 и total_price != ''
            cursor.execute("SELECT COUNT(*) FROM devices WHERE total_price_num = 0 AND total_price != '' AND total_price IS NOT NULL")
            count = cursor.fetchone()[0]
            if count == 0:
                return

            print(f"Миграция цен: конвертация {count} записей в REAL...")
            # SQLite не умеет CAST с REPLACE в одном UPDATE для всех — делаем построчно
            cursor.execute("SELECT id, total_price, prepayment, expense FROM devices WHERE total_price_num = 0")
            rows = cursor.fetchall()
            for row in rows:
                dev_id = row['id']
                tp = parse_price_to_float(row['total_price']) if row['total_price'] else 0.0
                pp = parse_price_to_float(row['prepayment']) if row['prepayment'] else 0.0
                ex = parse_price_to_float(row['expense']) if row['expense'] else 0.0
                cursor.execute(
                    "UPDATE devices SET total_price_num = ?, prepayment_num = ?, expense_num = ? WHERE id = ?",
                    (tp, pp, ex, dev_id))
            print(f"✅ Мигрировано {len(rows)} записей")

            # Миграция работ и фото в отдельные таблицы (если они пусты)
            cursor.execute('SELECT COUNT(*) FROM work_items_db')
            wi_count = cursor.fetchone()[0]
            if wi_count == 0:
                cursor.execute('SELECT id, work_items, photos FROM devices')
                for dev_row in cursor.fetchall():
                    self.sync_work_items_to_db(dev_row['id'], dev_row['work_items'] or '')
                    self.sync_photos_to_db(dev_row['id'], dev_row['photos'] or '')
                cursor.execute('SELECT COUNT(*) FROM work_items_db')
                new_wi = cursor.fetchone()[0]
                print(f"✅ Мигрировано работ в work_items_db: {new_wi}")
        except Exception as e:
            print(f"Ошибка миграции цен: {e}")

    # ==================== СЛОВАРИ ====================

    def get_next_order_number(self) -> int:
        """Получение следующего номера заказа.

        Атомарно: инкремент в той же транзакции, что и возврат значения.
        Возвращает текущее значение (до инкремента).
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT value FROM counters WHERE name = ?', ('order_counter',))
            result = cursor.fetchone()
            current = result['value'] if result else 1
            cursor.execute('UPDATE counters SET value = value + 1 WHERE name = ?', ('order_counter',))
            self.conn.commit()
            return current
        except sqlite3.Error as e:
            print(f"Ошибка получения номера заказа: {e}")
            return 1

    def get_dict_values(self, dict_type: str) -> List[str]:
        """Получение значений словаря (с кешированием).

        Словари меняются редко — кешируем в памяти после первого запроса.
        Кеш сбрасывается при add/update/delete_dict_value.
        """
        # Проверяем кеш
        if not hasattr(self, '_dict_cache'):
            self._dict_cache = {}
        if dict_type in self._dict_cache:
            return self._dict_cache[dict_type]

        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT value FROM dictionaries
                WHERE dict_type = ?
                ORDER BY sort_order
            ''', (dict_type,))
            values = [row['value'] for row in cursor.fetchall()]
            self._dict_cache[dict_type] = values  # кешируем
            return values
        except sqlite3.Error as e:
            print(f"Ошибка получения словаря: {e}")
            return []

    def _invalidate_dict_cache(self, dict_type: str = None):
        """Сбрасывает кеш словарей (при изменении)."""
        if hasattr(self, '_dict_cache'):
            if dict_type:
                self._dict_cache.pop(dict_type, None)
            else:
                self._dict_cache.clear()

    def get_all_dict_items(self, dict_type: str) -> List[Dict[str, Any]]:
        """Получение всех элементов словаря"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT id, value, sort_order, additional_info
                FROM dictionaries
                WHERE dict_type = ?
                ORDER BY sort_order
            ''', (dict_type,))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"Ошибка получения элементов словаря: {e}")
            return []

    def add_dict_value(self, dict_type: str, value: str, additional_info: str = "") -> bool:
        """Добавление значения в словарь"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT MAX(sort_order) as max_order
                FROM dictionaries WHERE dict_type = ?
            ''', (dict_type,))
            result = cursor.fetchone()
            sort_order = (result['max_order'] or 0) + 1

            cursor.execute('''
                INSERT INTO dictionaries (dict_type, value, sort_order, additional_info)
                VALUES (?, ?, ?, ?)
            ''', (dict_type, value, sort_order, additional_info))
            self.conn.commit()
            self._invalidate_dict_cache(dict_type)
            return True
        except sqlite3.IntegrityError:
            return False
        except sqlite3.Error as e:
            print(f"Ошибка добавления в словарь: {e}")
            return False

    def update_dict_value(self, item_id: int, value: str, additional_info: str = "") -> bool:
        """Обновление значения словаря"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE dictionaries
                SET value = ?, additional_info = ?
                WHERE id = ?
            ''', (value, additional_info, item_id))
            self.conn.commit()
            self._invalidate_dict_cache()
            return True
        except sqlite3.Error as e:
            print(f"Ошибка обновления словаря: {e}")
            return False

    def delete_dict_value(self, item_id: int) -> bool:
        """Удаление значения из словаря"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('DELETE FROM dictionaries WHERE id = ?', (item_id,))
            self.conn.commit()
            self._invalidate_dict_cache()
            return True
        except sqlite3.Error as e:
            print(f"Ошибка удаления из словаря: {e}")
            return False

    def get_statistics(self) -> Dict[str, int]:
        """Получение статистики"""
        try:
            cursor = self.conn.cursor()
            stats = {}

            cursor.execute('SELECT COUNT(*) FROM devices')
            row = cursor.fetchone()
            stats['total'] = row[0] if row else 0

            cursor.execute("SELECT COUNT(*) FROM devices WHERE status NOT IN ('Выдан клиенту', 'Отказ от ремонта')")
            row = cursor.fetchone()
            stats['in_repair'] = row[0] if row else 0

            cursor.execute("SELECT COUNT(*) FROM devices WHERE status = 'Готов к выдаче'")
            row = cursor.fetchone()
            stats['ready'] = row[0] if row else 0

            # Быстрая сумма выручки через REAL-колонку (если есть)
            try:
                cursor.execute("SELECT SUM(total_price_num) FROM devices WHERE status = 'Выдан клиенту'")
                row = cursor.fetchone()
                stats['total_income'] = row[0] if row and row[0] else 0.0
            except sqlite3.Error:
                stats['total_income'] = 0.0

            return stats
        except sqlite3.Error:
            return {'total': 0, 'in_repair': 0, 'ready': 0, 'total_income': 0.0}

    # ==================== УСТРОЙСТВА ====================

    def add_device(self, device_data: Dict[str, Any]) -> Optional[int]:
        """Добавление устройства"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO devices (
                    order_number, receipt_date, device_type, brand, model,
                    serial_number, defect, appearance, completeness, work_items,
                    client_name, client_status, phone, total_price, prepayment,
                    status, priority, engineer, warranty, notes, photos, expense
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                device_data.get('order_number', ''),
                device_data.get('receipt_date', ''),
                device_data.get('device_type', ''),
                device_data.get('brand', ''),
                device_data.get('model', ''),
                device_data.get('serial_number', ''),
                device_data.get('defect', ''),
                device_data.get('appearance', ''),
                device_data.get('completeness', ''),
                device_data.get('work_items_json', ''),
                device_data.get('client_name', ''),
                device_data.get('client_status', 'Новый'),
                device_data.get('phone', ''),
                device_data.get('total_price', ''),
                device_data.get('prepayment', ''),
                device_data.get('status', 'Диагностика'),
                device_data.get('priority', 'Обычный'),
                device_data.get('engineer', ''),
                device_data.get('warranty', ''),
                device_data.get('notes', ''),
                device_data.get('photos', ''),
                device_data.get('expense', '0')
            ))

            device_id = cursor.lastrowid
            # Dual-write: заполняем REAL-колонки цен для быстрых расчётов
            try:
                tp = parse_price_to_float(device_data.get('total_price', '0'))
                pp = parse_price_to_float(device_data.get('prepayment', '0'))
                ex = parse_price_to_float(device_data.get('expense', '0'))
                cursor.execute(
                    "UPDATE devices SET total_price_num = ?, prepayment_num = ?, expense_num = ? WHERE id = ?",
                    (tp, pp, ex, device_id))
            except Exception:
                pass
            # Dual-write: работы и фото в отдельные таблицы
            self.sync_work_items_to_db(device_id, device_data.get('work_items_json', ''))
            self.sync_photos_to_db(device_id, device_data.get('photos', ''))
            self.conn.commit()
            return device_id
        except sqlite3.Error as e:
            print(f"Ошибка добавления устройства: {e}")
            self.conn.rollback()
            return None

    # ==================== РАБОТЫ (work_items_db) ====================

    def sync_work_items_to_db(self, device_id: int, work_items_json: str) -> None:
        """Синхронизирует work_items_db из JSON-строки devices.work_items.

        Dual-write: JSON остаётся в devices.work_items для совместимости,
        отдельная таблица — для быстрых запросов/отчётов.
        """
        try:
            import json
            cursor = self.conn.cursor()
            # Очищаем старые записи
            cursor.execute('DELETE FROM work_items_db WHERE device_id = ?', (device_id,))
            if not work_items_json:
                return
            items = json.loads(work_items_json)
            if not isinstance(items, list):
                return
            for i, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                desc = item.get('description', '')
                price = parse_price_to_float(item.get('price', 0))
                try:
                    qty = int(item.get('quantity', 1))
                except (ValueError, TypeError):
                    qty = 1
                qty = max(qty, 1)
                total = price * qty
                cursor.execute('''
                    INSERT INTO work_items_db (device_id, description, price, quantity, total, sort_order)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (device_id, desc, price, qty, total, i))
        except Exception as e:
            print(f"Ошибка синхронизации work_items_db: {e}")

    def get_work_items_from_db(self, device_id: int) -> List[Dict[str, Any]]:
        """Получает работы заказа из отдельной таблицы (быстро, без JSON-парсинга)."""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT description, price, quantity, total FROM work_items_db
                WHERE device_id = ? ORDER BY sort_order
            ''', (device_id,))
            return [{'description': r['description'], 'price': r['price'],
                     'quantity': r['quantity'], 'total': r['total']}
                    for r in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"Ошибка получения work_items_db: {e}")
            return []

    # ==================== ФОТО (photos_db) ====================

    def sync_photos_to_db(self, device_id: int, photos_csv: str) -> None:
        """Синхронизирует photos_db из CSV-строки devices.photos.

        Dual-write: CSV остаётся в devices.photos для совместимости.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute('DELETE FROM photos_db WHERE device_id = ?', (device_id,))
            if not photos_csv:
                return
            paths = [p.strip() for p in photos_csv.split(',') if p.strip()]
            for i, path in enumerate(paths):
                fname = os.path.basename(path) if path else ''
                cursor.execute('''
                    INSERT INTO photos_db (device_id, file_path, filename, sort_order)
                    VALUES (?, ?, ?, ?)
                ''', (device_id, path, fname, i))
        except Exception as e:
            print(f"Ошибка синхронизации photos_db: {e}")

    def get_photos_from_db(self, device_id: int) -> List[Dict[str, Any]]:
        """Получает фото заказа из отдельной таблицы."""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT id, file_path, filename, photo_type FROM photos_db
                WHERE device_id = ? ORDER BY sort_order
            ''', (device_id,))
            return [dict(r) for r in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"Ошибка получения photos_db: {e}")
            return []

    def add_photo_to_db(self, device_id: int, file_path: str) -> bool:
        """Добавляет одно фото в photos_db."""
        try:
            cursor = self.conn.cursor()
            fname = os.path.basename(file_path)
            cursor.execute('SELECT COALESCE(MAX(sort_order), -1) + 1 FROM photos_db WHERE device_id = ?', (device_id,))
            next_order = cursor.fetchone()[0]
            cursor.execute('''
                INSERT INTO photos_db (device_id, file_path, filename, sort_order)
                VALUES (?, ?, ?, ?)
            ''', (device_id, file_path, fname, next_order))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Ошибка добавления фото в БД: {e}")
            return False

    # ==================== УСТРОЙСТВА (списки) ====================

    def get_all_devices(self, include_completed: bool = True) -> List[Dict[str, Any]]:
        """Получение всех устройств"""
        try:
            cursor = self.conn.cursor()

            if include_completed:
                cursor.execute('SELECT * FROM devices ORDER BY receipt_date DESC')
            else:
                cursor.execute('''
                    SELECT * FROM devices
                    WHERE status NOT IN ('Выдан клиенту', 'Отказ от ремонта')
                    ORDER BY receipt_date DESC
                ''')

            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"Ошибка получения устройств: {e}")
            return []

    def get_device(self, device_id: int) -> Optional[Dict[str, Any]]:
        """Получение устройства по ID"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM devices WHERE id = ?', (device_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            print(f"Ошибка получения устройства: {e}")
            return None

    def get_device_by_order_number(self, order_number: str) -> Optional[Dict[str, Any]]:
        """Получение устройства по номеру заказа"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM devices WHERE order_number = ?', (order_number,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            print(f"Ошибка получения устройства: {e}")
            return None

    def search_devices(self, search_text: str, include_completed: bool = True) -> List[Dict[str, Any]]:
        """Поиск устройств по подстроке.

        Поиск ведётся по всем текстовым полям заказа: номер, имя клиента,
        телефон, модель, бренд, серийный номер, тип устройства, неисправность.

        Особенности:
        - Регистронезависимый для Юникода (кириллицы). SQLite LOWER() работает
          только с ASCII, поэтому сравнение выполняется в Python через str.lower().
        - Устойчив к формату телефона: ищет по нормализованным цифрам, так что
          '+7 (927) 121-31-03', '927121' или '89271213103' — все найдут запись.
        - Номер заказа ищется и по полному формату ('00001'), и по числу ('1').

        Возвращает список словарей заказов.
        """
        try:
            search_text = (search_text or '').strip()
            if not search_text:
                return self.get_all_devices(include_completed=include_completed)

            cursor = self.conn.cursor()

            # Загружаем все записи с нужным фильтром статуса — фильтрацию по
            # подстроке делаем в Python, чтобы корректно работать с кириллицей
            # (SQLite LOWER() не переводит не-ASCII символы в нижний регистр).
            if include_completed:
                cursor.execute('SELECT * FROM devices ORDER BY receipt_date DESC')
            else:
                cursor.execute(
                    "SELECT * FROM devices WHERE status NOT IN "
                    "('Выдан клиенту', 'Отказ от ремонта') ORDER BY receipt_date DESC"
                )
            all_rows = [dict(row) for row in cursor.fetchall()]

            # Нормализованный поисковый запрос (нижний регистр, обрезан)
            needle = search_text.lower()
            # Нормализованные цифры телефона из запроса
            phone_digits = normalize_phone_digits(search_text)
            # Чистые цифры/буквы из запроса (для поиска по номеру заказа без лид. нулей)
            order_digits = ''.join(ch for ch in search_text if ch.isdigit())

            results = []
            for row in all_rows:
                if self._row_matches(row, needle, phone_digits, order_digits):
                    results.append(row)

            return results
        except sqlite3.Error as e:
            print(f"Ошибка поиска: {e}")
            return []

    @staticmethod
    def _row_matches(row: Dict[str, Any], needle: str, phone_digits: str,
                     order_digits: str) -> bool:
        """Проверяет, соответствует ли запись поисковому запросу.

        needle — запрос в нижнем регистре (для общего текстового поиска).
        phone_digits — только цифры из запроса (для поиска по телефону любого формата).
        order_digits — только цифры из запроса (для поиска по номеру заказа).
        """
        # Поля для общего регистронезависимого поиска по подстроке
        text_fields = (
            'order_number', 'client_name', 'phone', 'model', 'brand',
            'serial_number', 'device_type', 'defect', 'engineer', 'status',
        )
        for field in text_fields:
            val = row.get(field)
            if val and needle in str(val).lower():
                return True

        # Поиск по нормализованным цифрам телефона (устойчив к форматам).
        # Дополнительно нормализуем ведущую 8 в 7 (8XXX... -> 7XXX...),
        # т.к. телефон мог быть введён через «8», а хранится через «+7».
        if phone_digits:
            row_phone_digits = normalize_phone_digits(row.get('phone') or '')
            if row_phone_digits:
                # Варианты запроса: как есть и с заменой 8->7 в начале
                q_variants = {phone_digits}
                if phone_digits.startswith('8') and len(phone_digits) == 11:
                    q_variants.add('7' + phone_digits[1:])
                if phone_digits.startswith('7') and len(phone_digits) == 11:
                    q_variants.add('8' + phone_digits[1:])
                # Варианты записи: как есть, с заменой 8->7 / 7->8, и без кода страны
                row_variants = {row_phone_digits}
                if row_phone_digits.startswith('8') and len(row_phone_digits) == 11:
                    row_variants.add('7' + row_phone_digits[1:])
                if row_phone_digits.startswith('7') and len(row_phone_digits) == 11:
                    row_variants.add('8' + row_phone_digits[1:])
                    # И 10-значный вид без кода страны
                    row_variants.add(row_phone_digits[1:])
                # Ищем вхождение любого варианта запроса в любой вариант записи
                for q in q_variants:
                    for rv in row_variants:
                        if q and rv and q in rv:
                            return True

        # Поиск по номеру заказа без учёта лидирующих нулей:
        # '1' должно находить '00001'
        if order_digits:
            row_order = str(row.get('order_number') or '')
            # Полное совпадение по цифрам или вхождение
            if order_digits in row_order:
                return True
            # Сравнение как чисел: '1' == int('00001')
            try:
                if int(order_digits) == int(row_order):
                    return True
            except (ValueError, TypeError):
                pass

        return False

    def get_devices_by_filters(self, status_filter: str, priority_filter: str,
                               include_completed: bool = True,
                               device_type_filter: str = "Все",
                               brand_filter: str = "Все") -> List[Dict[str, Any]]:
        """Получение устройств с фильтрами.

        Поддерживает фильтрацию по статусу, приоритету, типу устройства и бренду.
        Значение 'Все' (или пустое) — фильтр не применяется.
        """
        try:
            cursor = self.conn.cursor()

            query = 'SELECT * FROM devices WHERE 1=1'
            params = []

            if not include_completed:
                query += " AND status NOT IN ('Выдан клиенту', 'Отказ от ремонта')"

            if status_filter and status_filter != "Все":
                query += " AND status = ?"
                params.append(status_filter)

            if priority_filter and priority_filter != "Все":
                query += " AND priority = ?"
                params.append(priority_filter)

            if device_type_filter and device_type_filter != "Все":
                query += " AND device_type = ?"
                params.append(device_type_filter)

            if brand_filter and brand_filter != "Все":
                query += " AND brand = ?"
                params.append(brand_filter)

            query += " ORDER BY receipt_date DESC"

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"Ошибка получения устройств: {e}")
            return []

    def update_device(self, device_id: int, device_data: Dict[str, Any]) -> bool:
        """Обновление устройства.

        ВАЖНО: берём order_number из переданных данных (раньше ветка
        обновления формы его не передавала, и запись в финансы падала
        с пустым номером заказа — нарушалась UNIQUE(order_number)).
        """
        try:
            cursor = self.conn.cursor()

            # Если статус меняется на "Выдан клиенту", добавляем дату выдачи
            completion_date = device_data.get('completion_date', '')
            status = device_data.get('status', '')

            if status == 'Выдан клиенту' and not completion_date:
                completion_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute('''
                UPDATE devices
                SET device_type = ?, brand = ?, model = ?, serial_number = ?, defect = ?,
                    appearance = ?, completeness = ?, work_items = ?,
                    client_name = ?, client_status = ?, phone = ?, total_price = ?, prepayment = ?,
                    priority = ?, engineer = ?, warranty = ?, notes = ?, status = ?, photos = ?,
                    completion_date = ?, expense = ?
                WHERE id = ?
            ''', (
                device_data.get('device_type', ''),
                device_data.get('brand', ''),
                device_data.get('model', ''),
                device_data.get('serial_number', ''),
                device_data.get('defect', ''),
                device_data.get('appearance', ''),
                device_data.get('completeness', ''),
                device_data.get('work_items_json', ''),
                device_data.get('client_name', ''),
                device_data.get('client_status', 'Новый'),
                device_data.get('phone', ''),
                device_data.get('total_price', ''),
                device_data.get('prepayment', ''),
                device_data.get('priority', 'Обычный'),
                device_data.get('engineer', ''),
                device_data.get('warranty', ''),
                device_data.get('notes', ''),
                device_data.get('status', 'Диагностика'),
                device_data.get('photos', ''),
                completion_date,
                device_data.get('expense', '0'),
                device_id
            ))

            # Если заказ выдан, добавляем запись в финансы (с реальным order_number)
            if status == 'Выдан клиенту':
                order_number = device_data.get('order_number', '')
                if not order_number:
                    # Подстраховка: достаём номер заказа из БД, если не передан
                    cursor.execute('SELECT order_number FROM devices WHERE id = ?', (device_id,))
                    row = cursor.fetchone()
                    if row:
                        order_number = row['order_number']

                if order_number:
                    income = parse_price_to_float(device_data.get('total_price', '0'))
                    expense_val = parse_price_to_float(device_data.get('expense', '0'))
                    profit = income - expense_val

                    cursor.execute('''
                        INSERT OR REPLACE INTO finances (order_number, completion_date, income, expense, profit)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (order_number, completion_date, income, expense_val, profit))

            # Dual-write: обновляем REAL-колонки цен для быстрых расчётов
            try:
                tp = parse_price_to_float(device_data.get('total_price', '0'))
                pp = parse_price_to_float(device_data.get('prepayment', '0'))
                ex = parse_price_to_float(device_data.get('expense', '0'))
                cursor.execute(
                    "UPDATE devices SET total_price_num = ?, prepayment_num = ?, expense_num = ? WHERE id = ?",
                    (tp, pp, ex, device_id))
            except Exception:
                pass
            # Dual-write: работы и фото в отдельные таблицы
            self.sync_work_items_to_db(device_id, device_data.get('work_items_json', ''))
            self.sync_photos_to_db(device_id, device_data.get('photos', ''))

            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Ошибка обновления устройства: {e}")
            self.conn.rollback()
            return False

    def update_device_status(self, device_id: int, status: str, completion_date: str = None) -> bool:
        """Обновление статуса устройства"""
        try:
            cursor = self.conn.cursor()

            if status == 'Выдан клиенту':
                if not completion_date:
                    completion_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute('''
                    UPDATE devices
                    SET status = ?, completion_date = ?
                    WHERE id = ?
                ''', (status, completion_date, device_id))
            else:
                cursor.execute('UPDATE devices SET status = ? WHERE id = ?', (status, device_id))

            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Ошибка обновления статуса: {e}")
            self.conn.rollback()
            return False

    def add_completed_repair(self, device: Dict[str, Any]) -> bool:
        """Добавление завершенного ремонта"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO completed_repairs (
                    device_id, order_number, completion_date,
                    work_description, work_price, engineer, warranty, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                device.get('id'),
                device.get('order_number'),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                device.get('work_items', ''),
                device.get('total_price', ''),
                device.get('engineer', ''),
                device.get('warranty', ''),
                device.get('notes', '')
            ))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Ошибка добавления завершенного ремонта: {e}")
            return False

    # ==================== ФИНАНСОВЫЕ МЕТОДЫ ====================

    def get_finances(self, period: str = 'all') -> List[Dict[str, Any]]:
        """Получение финансовых записей за период"""
        try:
            cursor = self.conn.cursor()

            if period == 'week':
                cursor.execute('''
                    SELECT * FROM finances
                    WHERE completion_date >= date('now', '-7 days')
                    ORDER BY completion_date DESC
                ''')
            elif period == 'month':
                cursor.execute('''
                    SELECT * FROM finances
                    WHERE completion_date >= date('now', '-30 days')
                    ORDER BY completion_date DESC
                ''')
            else:
                cursor.execute('SELECT * FROM finances ORDER BY completion_date DESC')

            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"Ошибка получения финансов: {e}")
            return []

    def get_finance_summary(self, period: str = 'all') -> Dict[str, float]:
        """Получение сводки по финансам"""
        try:
            cursor = self.conn.cursor()

            if period == 'week':
                cursor.execute('''
                    SELECT SUM(income) as total_income, SUM(expense) as total_expense, SUM(profit) as total_profit
                    FROM finances
                    WHERE completion_date >= date('now', '-7 days')
                ''')
            elif period == 'month':
                cursor.execute('''
                    SELECT SUM(income) as total_income, SUM(expense) as total_expense, SUM(profit) as total_profit
                    FROM finances
                    WHERE completion_date >= date('now', '-30 days')
                ''')
            else:
                cursor.execute('''
                    SELECT SUM(income) as total_income, SUM(expense) as total_expense, SUM(profit) as total_profit
                    FROM finances
                ''')

            row = cursor.fetchone()
            return {
                'total_income': row['total_income'] if row['total_income'] else 0,
                'total_expense': row['total_expense'] if row['total_expense'] else 0,
                'total_profit': row['total_profit'] if row['total_profit'] else 0
            }
        except sqlite3.Error as e:
            print(f"Ошибка получения сводки: {e}")
            return {'total_income': 0, 'total_expense': 0, 'total_profit': 0}

    def update_finance_expense(self, order_number: str, expense: float) -> bool:
        """Обновление расхода по заказу"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE finances
                SET expense = ?, profit = income - ?
                WHERE order_number = ?
            ''', (expense, expense, order_number))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Ошибка обновления расхода: {e}")
            return False

    # ==================== КЛИЕНТЫ (объединённые) ====================

    def get_or_create_client(self, name: str, phone: str, status: str = 'Новый') -> Optional[int]:
        """Находит или создаёт клиента в основной БД. Возвращает client_id."""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT id FROM clients WHERE phone = ?', (phone,))
            row = cursor.fetchone()
            if row:
                return row['id']
            cursor.execute('''
                INSERT INTO clients (name, phone, status, first_order_date, last_order_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (name, phone, status,
                  datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                  datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            print(f"Ошибка get_or_create_client: {e}")
            return None

    def add_to_repair_history_main(self, client_id: int, device_id: int,
                                    device_data: Dict[str, Any]) -> None:
        """Добавляет/обновляет запись в repair_history_main."""
        try:
            cursor = self.conn.cursor()
            order_number = device_data.get('order_number', '')
            cursor.execute(
                'SELECT id FROM repair_history_main WHERE client_id = ? AND order_number = ?',
                (client_id, order_number))
            existing = cursor.fetchone()
            values = (
                client_id, device_id, order_number,
                device_data.get('receipt_date', ''),
                device_data.get('completion_date', ''),
                device_data.get('device_type', ''),
                device_data.get('brand', ''),
                device_data.get('model', ''),
                device_data.get('serial_number', ''),
                device_data.get('defect', ''),
                device_data.get('work_items_json', ''),
                device_data.get('status', ''),
                device_data.get('total_price', ''),
                device_data.get('engineer', ''),
                device_data.get('warranty', ''),
                device_data.get('notes', ''),
                device_data.get('photos', ''),
            )
            if existing:
                # values = (client_id, device_id, order_number, receipt_date, ..., photos)
                # UPDATE: пропускаем client_id (0) и order_number (2) — они не меняются
                update_vals = (values[1],) + values[3:]  # device_id + receipt_date..photos = 15
                cursor.execute('''
                    UPDATE repair_history_main SET
                        device_id=?, receipt_date=?, completion_date=?, device_type=?, brand=?,
                        model=?, serial_number=?, defect=?, work_items=?, status=?, total_price=?,
                        engineer=?, warranty=?, notes=?, photos=?
                    WHERE id=?
                ''', update_vals + (existing['id'],))
            else:
                cursor.execute('''
                    INSERT INTO repair_history_main (
                        client_id, device_id, order_number, receipt_date, completion_date,
                        device_type, brand, model, serial_number, defect, work_items,
                        status, total_price, engineer, warranty, notes, photos
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', values)
            self._recalc_client_stats(client_id)
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Ошибка add_to_repair_history_main: {e}")

    def _recalc_client_stats(self, client_id: int) -> None:
        """Пересчитывает агрегаты клиента из repair_history_main."""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN status='Выдан клиенту' THEN 1 ELSE 0 END) as completed,
                       MIN(receipt_date) as first_date,
                       MAX(receipt_date) as last_date
                FROM repair_history_main WHERE client_id = ?
            ''', (client_id,))
            row = cursor.fetchone()
            if not row:
                return
            cursor.execute('''
                UPDATE clients SET total_orders=?, completed_orders=?, first_order_date=?, last_order_date=?
                WHERE id=?
            ''', (row['total'] or 0, row['completed'] or 0,
                  row['first_date'], row['last_date'], client_id))
        except sqlite3.Error as e:
            print(f"Ошибка _recalc_client_stats: {e}")

    def get_client_history_main(self, client_name: str, client_phone: str) -> List[Dict[str, Any]]:
        """Получает историю ремонтов клиента из основной БД.

        Поиск по нормализованным цифрам телефона (устойчив к форматам).
        """
        try:
            from utils.formatters import normalize_phone_digits
            phone_digits = normalize_phone_digits(client_phone)
            cursor = self.conn.cursor()
            # Ищем клиента по последним 10 цифрам телефона
            if len(phone_digits) >= 10:
                search = '%' + phone_digits[-10:]
                cursor.execute('''
                    SELECT rhm.* FROM repair_history_main rhm
                    JOIN clients c ON rhm.client_id = c.id
                    WHERE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(c.phone,'+',''),'(',''),')',''),'-',''),' ','') LIKE ?
                    ORDER BY rhm.receipt_date DESC
                ''', (search,))
            else:
                cursor.execute('''
                    SELECT rhm.* FROM repair_history_main rhm
                    JOIN clients c ON rhm.client_id = c.id
                    WHERE c.name = ? OR c.phone = ?
                    ORDER BY rhm.receipt_date DESC
                ''', (client_name, client_phone))
            return [dict(r) for r in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"Ошибка get_client_history_main: {e}")
            return []

    def get_client_stats_main(self, client_name: str, client_phone: str) -> Dict[str, Any]:
        """Получает статистику клиента из основной БД."""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT * FROM clients WHERE name = ? AND phone = ?
            ''', (client_name, client_phone))
            row = cursor.fetchone()
            return dict(row) if row else {}
        except sqlite3.Error:
            return {}

    def migrate_client_dbs(self) -> int:
        """Миграция всех клиентских БД из DBClients/*.db в основную БД.

        Возвращает количество мигрированных клиентов. Безопасен при повторах —
        проверяет по телефону (UNIQUE).
        """
        import glob
        from config import CLIENTS_DB_DIR
        from utils.formatters import normalize_phone_digits
        migrated = 0
        try:
            db_files = glob.glob(os.path.join(CLIENTS_DB_DIR, '*.db'))
            for db_path in db_files:
                try:
                    cl_conn = sqlite3.connect(db_path)
                    cl_conn.row_factory = sqlite3.Row
                    cl_cur = cl_conn.cursor()
                    # Читаем все ремонты клиента
                    cl_cur.execute('SELECT * FROM repair_history')
                    repairs = cl_cur.fetchall()
                    if not repairs:
                        cl_conn.close()
                        continue
                    # Берём имя/телефон из первой записи
                    first = repairs[0]
                    client_name = self._extract_client_name(db_path)
                    client_phone = self._extract_client_phone(db_path, repairs)
                    if not client_name or not client_phone:
                        cl_conn.close()
                        continue
                    client_id = self.get_or_create_client(client_name, client_phone)
                    if not client_id:
                        cl_conn.close()
                        continue
                    # Переносим ремонты
                    for r in repairs:
                        device_data = {
                            'order_number': r['order_number'] if 'order_number' in r.keys() else '',
                            'receipt_date': r['receipt_date'] if 'receipt_date' in r.keys() else '',
                            'completion_date': r['completion_date'] if 'completion_date' in r.keys() else '',
                            'device_type': r['device_type'] if 'device_type' in r.keys() else '',
                            'brand': r['brand'] if 'brand' in r.keys() else '',
                            'model': r['model'] if 'model' in r.keys() else '',
                            'serial_number': r['serial_number'] if 'serial_number' in r.keys() else '',
                            'defect': r['defect'] if 'defect' in r.keys() else '',
                            'work_items_json': r['work_items'] if 'work_items' in r.keys() else '',
                            'status': r['status'] if 'status' in r.keys() else '',
                            'total_price': r['total_price'] if 'total_price' in r.keys() else '',
                            'engineer': r['engineer'] if 'engineer' in r.keys() else '',
                            'warranty': r['warranty'] if 'warranty' in r.keys() else '',
                            'notes': r['notes'] if 'notes' in r.keys() else '',
                            'photos': r['photos'] if 'photos' in r.keys() else '',
                        }
                        # Найти device_id по order_number
                        cursor = self.conn.cursor()
                        cursor.execute('SELECT id FROM devices WHERE order_number = ?',
                                       (r['order_number'] if 'order_number' in r.keys() else '',))
                        dev_row = cursor.fetchone()
                        device_id = dev_row['id'] if dev_row else None
                        self.add_to_repair_history_main(client_id, device_id, device_data)
                    migrated += 1
                    cl_conn.close()
                    print(f"✅ Мигрирован клиент: {client_name} ({len(repairs)} ремонтов)")
                except Exception as e:
                    print(f"Ошибка миграции {db_path}: {e}")
        except Exception as e:
            print(f"Ошибка миграции клиентских БД: {e}")
        return migrated

    @staticmethod
    def _extract_client_name(db_path: str) -> str:
        """Извлекает имя клиента из имени файла БД (fallback)."""
        basename = os.path.basename(db_path).replace('.db', '')
        # Формат: имя_цифрытелефона → берём часть до последнего _
        parts = basename.rsplit('_', 1)
        return parts[0] if parts else basename

    @staticmethod
    def _extract_client_phone(db_path: str, repairs) -> str:
        """Извлекает телефон из имени файла БД.

        Имя файла: 'имя_цифрытелефона.db', где цифры — 10 или 11 знаков.
        Формат '79271213103' → '+7 (927) 121-31-03'.
        """
        basename = os.path.basename(db_path).replace('.db', '')
        parts = basename.rsplit('_', 1)
        if len(parts) < 2:
            return ''
        digits = parts[1]
        # Если 11 цифр с кодом страны 7/8 — убираем первую
        if len(digits) == 11 and digits[0] in ('7', '8'):
            digits = digits[1:]
        if len(digits) == 10:
            return f"+7 ({digits[0:3]}) {digits[3:6]}-{digits[6:8]}-{digits[8:10]}"
        return digits

    def close(self) -> None:
        """Закрытие соединения"""
        if self.conn:
            self.conn.close()
            self.conn = None
