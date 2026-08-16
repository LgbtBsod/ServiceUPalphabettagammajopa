#!/usr/bin/env python3
"""DevicePhotosMixin — добавление/удаление/просмотр фото заказа. См.
AUDIT_REPORT_v25.md, Task T (перенесено из device_form.py без изменения
поведения)."""

from __future__ import annotations

import logging
import os
from tkinter import filedialog, messagebox

from gui.dialogs.photo_viewer import PhotoViewerWindow
from gui.widgets.thumbnail import ThumbnailWidget

logger = logging.getLogger(__name__)


class DevicePhotosMixin:
    """Требует от финального класса DeviceFormDialog: self.client_name_entry,
    self.phone_entry, self.is_new, self.device_data, self.photo_manager,
    self.current_photos, self.thumbnail_widgets, self.thumbnails_container,
    self.photos_label, self.colors, self.settings."""

    def add_photos(self):
        """Добавление фотографий"""
        files = filedialog.askopenfilenames(
            title="Выберите фотографии",
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.gif *.bmp")],
        )

        if files:
            client_name = self.client_name_entry.get().strip()
            client_phone = self.phone_entry.get().strip()

            if not client_name or not client_phone:
                messagebox.showerror(
                    "Ошибка", "Сначала заполните ФИО и телефон клиента"
                )
                return

            order_number = "new"
            if not self.is_new and self.device_data:
                order_number = self.device_data.get("order_number", "")

            saved_count = 0
            for file in files:
                photo_path = self.photo_manager.save_photo(
                    file, client_name, client_phone, order_number, "device"
                )
                if photo_path:
                    self.current_photos.append(photo_path)
                    saved_count += 1

            if saved_count > 0:
                messagebox.showinfo("Успех", f"✅ Добавлено {saved_count} фото")
                self.update_photos_display()

    def delete_photo(self, photo_path: str):
        """Удаление фотографии"""
        if messagebox.askyesno("Подтверждение", "Удалить фото?"):
            if photo_path in self.current_photos:
                self.current_photos.remove(photo_path)
                if os.path.exists(photo_path):
                    try:
                        os.remove(photo_path)
                    except Exception as e:
                        logger.exception(f"Ошибка удаления фото {photo_path}: {e}")
                self.update_photos_display()

    def view_photo(self, photo_path: str):
        """Просмотр фотографии — открывает все фото заказа с навигацией."""
        if os.path.exists(photo_path):
            # Передаём ВСЕ фото заказа, чтобы работала навигация ◀ ▶
            all_photos = list(self.current_photos)
            try:
                start_idx = all_photos.index(photo_path)
            except ValueError:
                start_idx = 0
            viewer = PhotoViewerWindow(
                self,
                self.photo_manager,
                all_photos,
                self.colors,
                title="Просмотр фото",
                settings=self.settings,
            )
            viewer.current_index = start_idx
            viewer.load_current_photo()

    def update_photos_display(self):
        """Обновление отображения фотографий"""
        for widget in self.thumbnail_widgets:
            widget.destroy()
        self.thumbnail_widgets.clear()

        if self.current_photos:
            for photo_path in self.current_photos:
                if os.path.exists(photo_path):
                    thumb_widget = ThumbnailWidget(
                        self.thumbnails_container,
                        self.photo_manager,
                        photo_path,
                        self.colors,
                        on_delete=self.delete_photo,
                        on_click=self.view_photo,
                    )
                    thumb_widget.pack(side="left", padx=5, pady=5)
                    self.thumbnail_widgets.append(thumb_widget)

            self.photos_label.configure(text=f"📸 Фото: {len(self.current_photos)}")
        else:
            self.photos_label.configure(text="📸 Фото: 0")
