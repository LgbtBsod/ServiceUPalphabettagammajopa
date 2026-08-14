#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""PWA-сервер для мобильной версии приложения.

Запускает Flask в фоновом daemon-потоке. REST API работает с той же
SQLite-БД (service_center.db) и папкой фото (client_photos/), что и
десктопное приложение — синхронизация естественная, в реальном времени.

Использование из главного окна::

    from pwa.server import PWAServerManager
    mgr = PWAServerManager()
    mgr.start(port=5000)   # запуск в daemon-потоке
    url = mgr.get_url()    # http://192.168.1.5:5000
    mgr.stop()
"""

import os
import socket
import threading
import json
import secrets
import logging
from datetime import datetime
from functools import wraps
from typing import Optional, List, Dict, Any

# Импорты приложения (пути уже настроены в config.py)
from config import DB_PATH, PHOTOS_DIR, THUMBNAILS_DIR
from database import Database, ClientDatabaseManager, WorkItemsManager
from database.models import WorkItem
from managers import PhotoManager
from utils.formatters import (
    format_date, format_phone, normalize_phone,
    format_order_number_for_display, format_order_number_for_db,
    generate_order_number, parse_price_to_float,
)
from utils.constants import STATUSES, PRIORITIES

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Безопасность: токен авторизации для PWA API
# ---------------------------------------------------------------------------

# Токен берётся из переменной окружения SERVICEUP_PWA_API_KEY
# Если не задан — генерируется случайный при каждом запуске (не рекомендуется для продакшена)
PWA_API_KEY = os.getenv("SERVICEUP_PWA_API_KEY", secrets.token_urlsafe(32))


def require_api_key(f):
    """Декоратор проверки API-ключа для защиты endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if not api_key or api_key != PWA_API_KEY:
            return jsonify({'error': 'Unauthorized: invalid or missing API key'}), 401
        return f(*args, **kwargs)
    return decorated_function


# ---------------------------------------------------------------------------
# Определение локального IP (для QR-кода)
# ---------------------------------------------------------------------------

def get_local_ip() -> str:
    """Возвращает локальный IP-адрес машины в сети (для доступа с телефона)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Не реально подключается — просто определяет интерфейс
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ---------------------------------------------------------------------------
# Потокобезопасный доступ к БД (отдельное соединение для Flask-потока)
# ---------------------------------------------------------------------------

class _DBHolder:
    """Создаёт соединения БД для КАЖДОГО потока (thread-local).

    SQLite требует, чтобы соединение использовалось в том же потоке, где
    создано. Flask с threaded=True обрабатывает запросы в разных потоках,
    поэтому используем threading.local() — каждое соединение живёт в своём
    потоке и создаётся лениво при первом обращении.
    """

    def __init__(self):
        self._local = threading.local()

    def _ensure(self):
        """Создаёт соединения для текущего потока, если ещё не созданы."""
        if not hasattr(self._local, 'db'):
            self._local.db = Database(DB_PATH)
            self._local.client_db = ClientDatabaseManager()
            self._local.photo = PhotoManager()

    @property
    def db(self) -> Database:
        self._ensure()
        return self._local.db

    @property
    def client_db(self) -> ClientDatabaseManager:
        self._ensure()
        return self._local.client_db

    @property
    def photo(self) -> PhotoManager:
        self._ensure()
        return self._local.photo

    def close(self):
        """Закрывает соединения текущего потока."""
        for attr in ('db', 'client_db'):
            obj = getattr(self._local, attr, None)
            if obj is not None:
                try:
                    if hasattr(obj, 'close'):
                        obj.close()
                except Exception:
                    pass
                setattr(self._local, attr, None)


# Глобальный держатель БД для Flask-приложения
_db_holder = _DBHolder()


# ---------------------------------------------------------------------------
# Создание Flask-приложения
# ---------------------------------------------------------------------------

def create_flask_app():
    """Создаёт и настраивает Flask-приложение с REST API."""
    from flask import Flask, request, jsonify, send_from_directory, send_file

    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    app = Flask(__name__, static_folder=static_dir, static_url_path='')

    # ------------------------------------------------------------------
    # Статика / PWA
    # ------------------------------------------------------------------

    @app.route('/')
    def index():
        return send_from_directory(static_dir, 'index.html')

    @app.route('/manifest.json')
    def manifest():
        return send_from_directory(static_dir, 'manifest.json')

    @app.route('/sw.js')
    def service_worker():
        return send_from_directory(static_dir, 'sw.js', mimetype='application/javascript')

    # ------------------------------------------------------------------
    # Вспомогательное: нормализация устройства для API
    # ------------------------------------------------------------------

    def _serialize_device(device: Dict[str, Any]) -> Dict[str, Any]:
        """Приводит запись заказа к JSON-совместимому виду для фронта."""
        if not device:
            return {}
        # work_items: JSON-строка -> список объектов
        work_items = []
        wi_json = device.get('work_items', '')
        if wi_json:
            try:
                work_items = json.loads(wi_json)
            except (json.JSONDecodeError, TypeError):
                work_items = []

        # photos: CSV абсолютных путей -> список с безопасными URL по индексу
        photos_list = []
        photos_str = device.get('photos', '')
        if photos_str:
            dev_id = device.get('id')
            for idx, p in enumerate(photos_str.split(',')):
                p = p.strip()
                if p and os.path.exists(p):
                    fname = os.path.basename(p)
                    photos_list.append({
                        'name': fname,
                        'url': f"/api/orders/{dev_id}/photos/{idx}",
                    })

        return {
            'id': device.get('id'),
            'order_number': format_order_number_for_display(device.get('order_number', '')),
            'receipt_date': format_date(device.get('receipt_date', '')),
            'completion_date': format_date(device.get('completion_date', '')),
            'device_type': device.get('device_type', ''),
            'brand': device.get('brand', ''),
            'model': device.get('model', ''),
            'serial_number': device.get('serial_number', ''),
            'defect': device.get('defect', ''),
            'appearance': device.get('appearance', ''),
            'completeness': device.get('completeness', ''),
            'work_items': work_items,
            'client_name': device.get('client_name', ''),
            'client_status': device.get('client_status', 'Новый'),
            'phone': format_phone(device.get('phone', '')),
            'total_price': device.get('total_price', ''),
            'prepayment': device.get('prepayment', ''),
            'status': device.get('status', 'Диагностика'),
            'priority': device.get('priority', 'Обычный'),
            'engineer': device.get('engineer', ''),
            'warranty': device.get('warranty', ''),
            'notes': device.get('notes', ''),
            'photos': photos_list,
            'created_at': device.get('created_at', ''),
        }

    # ------------------------------------------------------------------
    # API: Заказы
    # ------------------------------------------------------------------

    @app.route('/api/orders', methods=['GET'])
    @require_api_key
    def api_orders():
        """Список заказов. Параметры: status, limit, offset, hide_completed."""
        try:
            db = _db_holder.db
            status = request.args.get('status', 'Все')
            hide_completed = request.args.get('hide_completed', 'false').lower() == 'true'
            limit = min(int(request.args.get('limit', 200)), 500)
            offset = int(request.args.get('offset', 0))

            if status and status != 'Все':
                devices = db.get_devices_by_filters(status, 'Все',
                                                    include_completed=True,
                                                    device_type_filter='Все',
                                                    brand_filter='Все')
            else:
                devices = db.get_all_devices(include_completed=not hide_completed)

            # Пагинация
            total = len(devices)
            devices = devices[offset:offset + limit]
            return jsonify({
                'orders': [_serialize_device(d) for d in devices],
                'total': total,
                'limit': limit,
                'offset': offset,
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/orders/<int:device_id>', methods=['GET'])
    @require_api_key
    def api_order_detail(device_id: int):
        """Детали одного заказа."""
        try:
            db = _db_holder.db
            device = db.get_device(device_id)
            if not device:
                return jsonify({'error': 'Заказ не найден'}), 404
            return jsonify(_serialize_device(device))
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/orders', methods=['POST'])
    @require_api_key
    def api_create_order():
        """Создание нового заказа."""
        try:
            db = _db_holder.db
            data = request.get_json(force=True)

            # Генерируем номер заказа
            order_counter = db.get_next_order_number()
            order_number = generate_order_number(order_counter)

            # Нормализуем телефон
            phone_raw = data.get('phone', '')
            phone = normalize_phone(phone_raw)

            # Считаем итоговую цену из work_items, если есть
            total_price = data.get('total_price', '')
            if not total_price and data.get('work_items'):
                try:
                    wm = WorkItemsManager()
                    items_data = data.get('work_items')
                    if isinstance(items_data, str):
                        wm.from_json(items_data)
                    elif isinstance(items_data, list):
                        for it in items_data:
                            wm.add_item(WorkItem(
                                description=it.get('description', ''),
                                price=it.get('price', ''),
                                quantity=it.get('quantity', 1),
                            ))
                    total_price = str(int(wm.get_total_price()))
                except Exception:
                    pass

            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            device_data = {
                'order_number': order_number,
                'receipt_date': now,
                'device_type': data.get('device_type', ''),
                'brand': data.get('brand', ''),
                'model': data.get('model', ''),
                'serial_number': data.get('serial_number', ''),
                'defect': data.get('defect', ''),
                'appearance': data.get('appearance', ''),
                'completeness': data.get('completeness', ''),
                'work_items_json': _work_items_to_json(data.get('work_items')),
                'client_name': data.get('client_name', ''),
                'client_status': data.get('client_status', 'Новый'),
                'phone': phone,
                'total_price': str(total_price),
                'prepayment': data.get('prepayment', ''),
                'status': data.get('status', 'Диагностика'),
                'priority': data.get('priority', 'Обычный'),
                'engineer': data.get('engineer', ''),
                'warranty': data.get('warranty', ''),
                'notes': data.get('notes', ''),
                'photos': '',
                'expense': data.get('expense', '0'),
            }

            device_id = db.add_device(device_data)
            if device_id:
                # Сохраняем в историю клиента
                try:
                    _db_holder.client_db.add_repair_to_client_history(
                        data.get('client_name', ''), phone, device_data)
                except Exception as e:
                    logger.error(f"PWA: ошибка истории клиента: {e}", exc_info=True)

                device_data['id'] = device_id
                return jsonify({
                    'ok': True,
                    'id': device_id,
                    'order_number': format_order_number_for_display(order_number),
                    'order': _serialize_device(db.get_device(device_id)),
                }), 201
            return jsonify({'error': 'Не удалось создать заказ'}), 500
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/orders/<int:device_id>', methods=['PUT'])
    @require_api_key
    def api_update_order(device_id: int):
        """Редактирование заказа."""
        try:
            db = _db_holder.db
            existing = db.get_device(device_id)
            if not existing:
                return jsonify({'error': 'Заказ не найден'}), 404

            # Проверка: нельзя менять статус отказанного заказа
            if existing.get('status') == 'Отказано':
                return jsonify({'error': 'Нельзя редактировать заказ со статусом "Отказано"'}), 403

            data = request.get_json(force=True)
            phone = normalize_phone(data.get('phone', '')) or existing.get('phone', '')

            # Подготовка work_items
            work_items_json = _work_items_to_json(data.get('work_items'))
            if not work_items_json:
                work_items_json = existing.get('work_items', '')

            total_price = data.get('total_price', existing.get('total_price', ''))
            if data.get('work_items'):
                try:
                    wm = WorkItemsManager()
                    items_data = data.get('work_items')
                    if isinstance(items_data, str):
                        wm.from_json(items_data)
                    elif isinstance(items_data, list):
                        for it in items_data:
                            wm.add_item(WorkItem(
                                description=it.get('description', ''),
                                price=it.get('price', ''),
                                quantity=it.get('quantity', 1),
                            ))
                    total_price = str(int(wm.get_total_price()))
                except Exception:
                    pass

            order_number = existing.get('order_number', '')

            device_data = {
                'order_number': order_number,
                'device_type': data.get('device_type', existing.get('device_type', '')),
                'brand': data.get('brand', existing.get('brand', '')),
                'model': data.get('model', existing.get('model', '')),
                'serial_number': data.get('serial_number', existing.get('serial_number', '')),
                'defect': data.get('defect', existing.get('defect', '')),
                'appearance': data.get('appearance', existing.get('appearance', '')),
                'completeness': data.get('completeness', existing.get('completeness', '')),
                'work_items_json': work_items_json,
                'client_name': data.get('client_name', existing.get('client_name', '')),
                'client_status': data.get('client_status', existing.get('client_status', 'Новый')),
                'phone': phone,
                'total_price': str(total_price),
                'prepayment': data.get('prepayment', existing.get('prepayment', '')),
                'priority': data.get('priority', existing.get('priority', 'Обычный')),
                'engineer': data.get('engineer', existing.get('engineer', '')),
                'warranty': data.get('warranty', existing.get('warranty', '')),
                'notes': data.get('notes', existing.get('notes', '')),
                'status': data.get('status', existing.get('status', 'Диагностика')),
                'photos': existing.get('photos', ''),
                'completion_date': existing.get('completion_date', ''),
                'expense': data.get('expense', existing.get('expense', '0')),
            }

            if db.update_device(device_id, device_data):
                # Обновляем историю клиента
                try:
                    _db_holder.client_db.update_repair_in_history(
                        device_data.get('client_name', ''), phone,
                        order_number, device_data)
                except Exception as e:
                    logger.error(f"PWA: ошибка истории клиента: {e}", exc_info=True)

                return jsonify({
                    'ok': True,
                    'order': _serialize_device(db.get_device(device_id)),
                })
            return jsonify({'error': 'Не удалось обновить'}), 500
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/orders/<int:device_id>/status', methods=['PUT'])
    @require_api_key
    def api_update_status(device_id: int):
        """Смена статуса заказа."""
        try:
            db = _db_holder.db
            data = request.get_json(force=True)
            new_status = data.get('status', '').strip()
            if not new_status:
                return jsonify({'error': 'Не указан статус'}), 400

            completion_date = None
            if new_status == 'Выдан клиенту':
                completion_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            if db.update_device_status(device_id, new_status, completion_date):
                return jsonify({'ok': True, 'status': new_status})
            return jsonify({'error': 'Не удалось обновить статус'}), 500
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ------------------------------------------------------------------
    # API: Поиск
    # ------------------------------------------------------------------

    @app.route('/api/search', methods=['GET'])
    @require_api_key
    def api_search():
        """Поиск заказов по имени/телефону/номеру."""
        try:
            q = request.args.get('q', '').strip()
            if not q:
                return jsonify({'orders': [], 'total': 0})
            db = _db_holder.db
            devices = db.search_devices(q, include_completed=True)
            return jsonify({
                'orders': [_serialize_device(d) for d in devices],
                'total': len(devices),
                'query': q,
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ------------------------------------------------------------------
    # API: Справочники
    # ------------------------------------------------------------------

    @app.route('/api/dictionaries', methods=['GET'])
    @require_api_key
    def api_dictionaries():
        """Справочники для форм: типы устройств, бренды, статусы, приоритеты."""
        try:
            db = _db_holder.db
            return jsonify({
                'statuses': STATUSES,
                'priorities': PRIORITIES,
                'device_types': db.get_dict_values('device_types'),
                'brands': db.get_dict_values('brands'),
                'work_templates': db.get_dict_values('work'),
                'warranties': ['', '1 месяц', '3 месяца', '6 месяцев', '1 год', '2 года'],
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ------------------------------------------------------------------
    # API: Статистика
    # ------------------------------------------------------------------

    @app.route('/api/stats', methods=['GET'])
    @require_api_key
    def api_stats():
        """Статистика для дашборда."""
        try:
            db = _db_holder.db
            stats = db.get_statistics()
            return jsonify(stats)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ------------------------------------------------------------------
    # API: Фото
    # ------------------------------------------------------------------

    @app.route('/api/orders/<int:device_id>/photos', methods=['POST'])
    @require_api_key
    def api_upload_photo(device_id: int):
        """Загрузка фото для заказа (multipart form-data, field 'photo')."""
        try:
            db = _db_holder.db
            device = db.get_device(device_id)
            if not device:
                return jsonify({'error': 'Заказ не найден'}), 404

            if 'photo' not in request.files:
                return jsonify({'error': 'Файл не передан'}), 400

            file = request.files['photo']
            if not file.filename:
                return jsonify({'error': 'Пустое имя файла'}), 400

            # Сохраняем во временный файл
            import tempfile
            ext = os.path.splitext(file.filename)[1].lower() or '.jpg'
            fd, tmp_path = tempfile.mkstemp(suffix=ext)
            os.close(fd)
            file.save(tmp_path)

            client_name = device.get('client_name', '')
            client_phone = device.get('phone', '')
            order_number = device.get('order_number', '')

            # Сохраняем через PhotoManager (с созданием миниатюры)
            saved_path = _db_holder.photo.save_photo(
                tmp_path, client_name, client_phone, order_number, 'device')
            try:
                os.remove(tmp_path)
            except OSError:
                pass

            if not saved_path:
                return jsonify({'error': 'Не удалось сохранить фото'}), 500

            # Обновляем список фото в БД через фасад Database
            photos_str = device.get('photos', '')
            photos_list = [p.strip() for p in photos_str.split(',') if p.strip()] if photos_str else []
            photos_list.append(saved_path)
            new_photos_str = ','.join(photos_list)

            db.update_device(device_id, {'photos': new_photos_str})

            # Dual-write: добавляем фото и в отдельную таблицу photos_db
            try:
                db.add_photo_to_db(device_id, saved_path)
            except Exception:
                pass

            # Считаем индекс нового фото для URL
            photo_idx = len(photos_list) - 1
            return jsonify({
                'ok': True,
                'photo': {
                    'name': os.path.basename(saved_path),
                    'url': f"/api/orders/{device_id}/photos/{photo_idx}",
                }
            }), 201
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/orders/<int:device_id>/photos/<int:photo_idx>', methods=['GET'])
    @require_api_key
    def api_photo_by_index(device_id: int, photo_idx: int):
        """Отдаёт файл фото по индексу в списке photos заказа.

        Безопаснее, чем ?path= — не раскрывает пути файловой системы и
        не требует URL-кодирования Windows-путей с обратными слешами.
        """
        try:
            db = _db_holder.db
            device = db.get_device(device_id)
            if not device:
                return jsonify({'error': 'Заказ не найден'}), 404

            photos_str = device.get('photos', '')
            if not photos_str:
                return jsonify({'error': 'Нет фото'}), 404

            photos_list = [p.strip() for p in photos_str.split(',') if p.strip()]
            if photo_idx < 0 or photo_idx >= len(photos_list):
                return jsonify({'error': 'Фото не найдено'}), 404

            path = photos_list[photo_idx]
            if not os.path.exists(path):
                return jsonify({'error': 'Файл не найден на диске'}), 404

            # Безопасность: только в пределах PHOTOS_DIR
            norm = os.path.normpath(path)
            if not norm.startswith(os.path.normpath(PHOTOS_DIR)):
                return jsonify({'error': 'Доступ запрещён'}), 403
            return send_file(norm)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return app


def _work_items_to_json(work_items) -> str:
    """Преобразует work_items (строка JSON / список / None) в JSON-строку."""
    if not work_items:
        return ''
    if isinstance(work_items, str):
        return work_items
    if isinstance(work_items, list):
        import json as _json
        result = []
        for it in work_items:
            if isinstance(it, dict):
                qty = it.get('quantity', 1)
                try:
                    qty = int(qty)
                except (ValueError, TypeError):
                    qty = 1
                result.append({
                    'description': it.get('description', ''),
                    'price': str(it.get('price', '')),
                    'quantity': qty,
                })
        return _json.dumps(result, ensure_ascii=False)
    return ''


# ---------------------------------------------------------------------------
# Менеджер сервера
# ---------------------------------------------------------------------------

class PWAServerManager:
    """Управляет жизненным циклом Flask-сервера в daemon-потоке."""

    def __init__(self):
        self.app = None
        self.thread: Optional[threading.Thread] = None
        self.host = '0.0.0.0'
        self.port = 5000
        self._running = False

    def start(self, port: int = 5000, host: str = '0.0.0.0') -> bool:
        """Запускает сервер в фоновом потоке. Возвращает True при успехе."""
        if self._running:
            return True
        try:
            self.port = port
            self.host = host
            self.app = create_flask_app()

            def _serve():
                # werkzeug без reloader/log, чтобы не плодить потоки
                from werkzeug.serving import make_server
                server = make_server(host, port, self.app, threaded=True)
                self._werkzeug_server = server
                server.serve_forever()

            self.thread = threading.Thread(target=_serve, daemon=True, name='PWA-Server')
            self.thread.start()
            self._running = True
            return True
        except Exception as e:
            logger.error(f"Ошибка запуска PWA-сервера: {e}", exc_info=True)
            self._running = False
            return False

    def stop(self) -> None:
        """Останавливает сервер."""
        if not self._running:
            return
        try:
            srv = getattr(self, '_werkzeug_server', None)
            if srv is not None:
                srv.shutdown()
        except Exception as e:
            logger.error(f"Ошибка остановки PWA-сервера: {e}", exc_info=True)
        self._running = False
        # Закрываем соединения БД
        _db_holder.close()

    @property
    def is_running(self) -> bool:
        return self._running

    def get_url(self) -> str:
        """Возвращает URL для доступа с телефона (через локальный IP)."""
        ip = get_local_ip()
        return f"http://{ip}:{self.port}"
