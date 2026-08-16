#!/usr/bin/env python3

"""Диалог создания/редактирования устройства.

Реализация разбита на mixin'ы (gui/dialogs/device_form_parts/*_mixin.py) по
разделу ответственности — пессимистичная блокировка, построение виджетов,
фото, акты, сохранение — тем же способом, каким core/base.py уже собирает
BaseService из LoggableMixin/ExceptionHandlingMixin/... Этот файл — только
"сборка" (__init__ + композиция), см. AUDIT_REPORT_v25.md (Task T). Ни один
внешний вызов (gui/main_window.py, gui/dialogs/client_history.py) не
изменился — DeviceFormDialog(...) конструируется и вызывается ровно так
же, как раньше."""

import contextlib
import logging
from typing import Any

import customtkinter as ctk

from database import ClientDatabaseManager, Database, WorkItemsManager
from database.sqlalchemy_database import OptimisticLockError  # noqa: F401 — реэкспорт
from gui.dialogs.device_form_parts.acts_mixin import DeviceActsMixin
from gui.dialogs.device_form_parts.locking_mixin import (
    SCALAR_FIELD_NAMES as _SCALAR_FIELD_NAMES,
)
from gui.dialogs.device_form_parts.locking_mixin import DeviceLockingMixin
from gui.dialogs.device_form_parts.photos_mixin import DevicePhotosMixin
from gui.dialogs.device_form_parts.save_mixin import DeviceSaveMixin
from gui.dialogs.device_form_parts.widgets_mixin import DeviceWidgetsMixin
from managers import PhotoManager, ReportGenerator
from utils.formatters import format_order_number_for_display
from utils.window_effects import apply_dialog_translucency

logger = logging.getLogger(__name__)

__all__ = ["DeviceFormDialog", "OptimisticLockError"]


class DeviceFormDialog(
    DeviceLockingMixin,
    DeviceWidgetsMixin,
    DevicePhotosMixin,
    DeviceActsMixin,
    DeviceSaveMixin,
    ctk.CTkToplevel,
):
    """Диалог создания/редактирования устройства"""

    def __init__(
        self,
        parent,
        db: Database,
        client_db: ClientDatabaseManager,
        photo_manager: PhotoManager,
        colors: dict[str, str],
        is_new: bool = True,
        device_data: dict[str, Any] | None = None,
        settings=None,
        report_gen: ReportGenerator | None = None,
        employees_api=None,
        lock_api=None,
    ):
        super().__init__(parent)
        self.db = db
        self.client_db = client_db
        self.photo_manager = photo_manager
        # Уведомление о готовности заказа идёт через Kernel EventBus
        # (Database публикует DeviceStatusChangedEvent, IntegrationManager
        # подписан в bootstrap.py) — этот диалог не хранит и не зовёт
        # IntegrationManager напрямую, см. save() (DeviceSaveMixin).
        # Единственный экземпляр из Kernel (core.get_module_api("reports")) —
        # раньше диалог создавал свой ReportGenerator() локально в обход ядра
        # (см. AUDIT_REPORT_v21.md). Фолбэк оставлен на случай прямого
        # конструирования диалога вне обычного потока приложения.
        self.report_gen = report_gen or ReportGenerator()
        # API сотрудников (core.get_module_api("employees")) — для проставления
        # created_by/updated_by при сохранении. Опционально: если не передан
        # (например, старый вызов), заказ просто сохраняется без привязки.
        self.employees_api = employees_api
        # API пессимистичных блокировок (core.get_module_api("locking")) —
        # опционален и дополнительно гейтится настройкой
        # pessimistic_locking_enabled (см. LockManager.is_enabled()).
        # Оптимистичная блокировка (version_id) работает НЕЗАВИСИМО от этого —
        # см. save() (DeviceSaveMixin).
        self.lock_api = lock_api
        self.colors = colors
        self.settings = settings  # для сохранения геометрии окна (опционально)
        self.is_new = is_new
        self.device_data = device_data
        self.result = None
        self.current_photos: list[str] = []
        self.thumbnail_widgets: list[ctk.CTkFrame] = []
        self.work_manager = WorkItemsManager()
        self._holding_lock = False
        self._heartbeat_job: str | None = None
        self._lock_banner: ctk.CTkFrame | None = None

        # Загружаем существующие фото и работы
        if not is_new and device_data:
            photos = device_data.get("photos", "")
            self.current_photos = [p for p in photos.split(",") if p] if photos else []
            work_items_json = device_data.get("work_items", "")
            if work_items_json:
                self.work_manager.from_json(work_items_json)

        title = (
            "➕ Новый заказ"
            if is_new
            else f"✏️ Редактирование заказа #{format_order_number_for_display(device_data.get('order_number', '')) if device_data else ''}"
        )
        self.title(title)
        # Восстанавливаем геометрию из config-файла (или дефолт с центрированием)
        from utils.window_state import restore_window_geometry

        restore_window_geometry(
            self.settings,
            "device_form",
            self,
            default_w=1100,
            default_h=700,
            min_w=950,
            min_h=560,
        )

        self.transient(parent)
        self.grab_set()

        # Сохраняем геометрию при закрытии окна пользователем
        self.protocol("WM_DELETE_WINDOW", self._close_with_geometry)

        # macOS-стиль: лёгкая прозрачность и скругление углов диалога
        with contextlib.suppress(Exception):
            apply_dialog_translucency(self, theme=self.colors.get("bg_primary", "#fff"))

        self.create_widgets(device_data)
        self._setup_pessimistic_lock()
