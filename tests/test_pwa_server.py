#!/usr/bin/env python3

"""Тесты для pwa/server.py — REST API поверх той же Database facade, что
использует GUI. Инжектируем тестовую БД напрямую в _db_holder._local,
минуя _get_core()/bootstrap.initialize_kernel() (который иначе полез бы в
боевую БД/конфиг приложения — см. AUDIT_REPORT_v25.md о рисках полного
bootstrap в тестах)."""

import io
import os
import tempfile

import pytest

from database.db_config import DatabaseConfig
from database.engines.sqlite_engine import SQLiteEngine
from database.sqlalchemy_database import Database

import gui  # noqa: F401  — тот же обход циклического импорта managers/__init__.py
from pwa import server as pwa_server


class _FakeClientDb:
    def update_repair_in_history(self, *args, **kwargs):
        pass

    def add_repair_to_client_history(self, *args, **kwargs):
        pass


class _FakePhotoManager:
    """Не трогает реальные PHOTOS_DIR/THUMBNAILS_DIR приложения — просто
    возвращает переданный source_path как "сохранённый" (сам файл во
    временной директории теста уже существует)."""

    def save_photo(self, source_path, client_name, client_phone, order_number, photo_type):
        return source_path


@pytest.fixture
def pwa_client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = SQLiteEngine(DatabaseConfig(database=path))
    database = Database(engine)

    # Инжектируем тестовые сервисы напрямую в thread-local _DBHolder —
    # _ensure() увидит hasattr(..., "db") == True и не полезет в
    # _get_core()/bootstrap.initialize_kernel() (боевая БД/конфиг).
    pwa_server._db_holder._local.db = database
    pwa_server._db_holder._local.client_db = _FakeClientDb()
    pwa_server._db_holder._local.photo = _FakePhotoManager()

    app = pwa_server.create_flask_app()
    app.config["TESTING"] = True
    client = app.test_client()
    client.environ_base["HTTP_X_API_KEY"] = pwa_server.PWA_API_KEY

    yield client, database

    for attr in ("db", "client_db", "photo"):
        if hasattr(pwa_server._db_holder._local, attr):
            delattr(pwa_server._db_holder._local, attr)
    engine.dispose()
    if os.path.exists(path):
        os.remove(path)


def _sample_device(**overrides) -> dict:
    data = {
        "order_number": "00001",
        "receipt_date": "2026-01-01",
        "device_type": "Ноутбук",
        "brand": "Test",
        "model": "TestModel",
        "defect": "Не включается",
        "client_name": "Иван Иванов",
        "phone": "+79991234567",
        "total_price": "1000",
        "status": "Диагностика",
        "engineer": "Пётр Инженеров",
        "notes": "Важная заметка",
    }
    data.update(overrides)
    return data


class TestPhotoUploadPreservesOrderData:
    """Регрессия CRITICAL-находки аудита v25: api_upload_photo() слал
    update_device() словарь только с ключом "photos", из-за чего
    full-replace семантика update_device() стирала ВСЕ остальные поля
    заказа (и удаляла все work_items) на каждой загрузке фото."""

    def test_upload_photo_does_not_wipe_other_fields(self, pwa_client):
        client, database = pwa_client
        device_id = database.add_device(_sample_device())

        fd, photo_path = tempfile.mkstemp(suffix=".jpg")
        os.write(fd, b"\xff\xd8\xff\xe0fake-jpeg-bytes")
        os.close(fd)
        try:
            with open(photo_path, "rb") as f:
                resp = client.post(
                    f"/api/orders/{device_id}/photos",
                    data={"photo": (io.BytesIO(f.read()), "test.jpg")},
                    content_type="multipart/form-data",
                )
        finally:
            if os.path.exists(photo_path):
                os.remove(photo_path)

        assert resp.status_code == 201, resp.get_json()

        device = database.get_device(device_id)
        assert device["engineer"] == "Пётр Инженеров"
        assert device["notes"] == "Важная заметка"
        assert device["defect"] == "Не включается"
        assert device["client_name"] == "Иван Иванов"
        assert device["status"] == "Диагностика"
        assert device["photos"]  # ровно один добавленный путь, непусто

    def test_upload_photo_does_not_delete_work_items(self, pwa_client):
        client, database = pwa_client
        device_id = database.add_device(
            _sample_device(work_items_json='[{"description": "Замена экрана", "price": "500", "quantity": 1}]')
        )
        work_items_before = database.get_work_items_from_db(device_id)
        assert len(work_items_before) == 1

        fd, photo_path = tempfile.mkstemp(suffix=".jpg")
        os.write(fd, b"\xff\xd8\xff\xe0fake-jpeg-bytes")
        os.close(fd)
        try:
            with open(photo_path, "rb") as f:
                resp = client.post(
                    f"/api/orders/{device_id}/photos",
                    data={"photo": (io.BytesIO(f.read()), "test2.jpg")},
                    content_type="multipart/form-data",
                )
        finally:
            if os.path.exists(photo_path):
                os.remove(photo_path)

        assert resp.status_code == 201, resp.get_json()
        work_items_after = database.get_work_items_from_db(device_id)
        assert len(work_items_after) == 1


class TestOrderVersionRoundTrip:
    """Регрессия HIGH-находки: PWA раньше никогда не передавал
    _expected_version в update_device() — оптимистичная блокировка была
    мертва на этом пути."""

    def test_get_order_exposes_version(self, pwa_client):
        client, database = pwa_client
        device_id = database.add_device(_sample_device())

        resp = client.get(f"/api/orders/{device_id}")
        assert resp.status_code == 200
        assert resp.get_json()["version"] == 1

    def test_update_with_stale_version_returns_409(self, pwa_client):
        client, database = pwa_client
        device_id = database.add_device(_sample_device())
        # Кто-то другой уже сохранил -> версия в БД теперь 2
        database.update_device(device_id, _sample_device(status="Готов к выдаче"))

        resp = client.put(
            f"/api/orders/{device_id}",
            json={"notes": "моя правка", "version": 1},
        )
        assert resp.status_code == 409
        assert resp.get_json().get("code") == "version_conflict"

    def test_update_with_current_version_succeeds(self, pwa_client):
        client, database = pwa_client
        device_id = database.add_device(_sample_device())

        resp = client.put(
            f"/api/orders/{device_id}",
            json={"notes": "моя правка", "version": 1},
        )
        assert resp.status_code == 200, resp.get_json()
        assert database.get_device(device_id)["notes"] == "моя правка"
