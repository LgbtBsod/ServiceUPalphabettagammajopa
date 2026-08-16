#!/usr/bin/env python3
"""DeviceActsMixin — печать/предпросмотр акта приёма и акта выполненных
работ прямо из формы. См. AUDIT_REPORT_v25.md, Task T (перенесено из
device_form.py без изменения поведения)."""

from __future__ import annotations

import os

from database import WorkItemsManager
from gui.dialogs.act_preview import ActPreviewWindow


class DeviceActsMixin:
    """Требует от финального класса DeviceFormDialog: self.is_new, self.db,
    self.device_data, self.report_gen, self.colors, self.settings,
    self._do_save() (см. DeviceSaveMixin)."""

    def print_receipt_from_form(self):
        """Печать акта приёма прямо из формы (новый или существующий заказ).

        Для нового заказа: сначала сохраняет, потом печатает.
        """
        from tkinter import messagebox as _mb

        if self.is_new:
            # Сначала сохраняем заказ
            if not self._do_save(silent=True):
                _mb.showwarning(
                    "Внимание", "Сначала сохраните заказ (заполните обязательные поля)"
                )
                return

        # Теперь заказ сохранён — печатаем акт
        device = self.db.get_device(self.device_data.get("id"))
        if not device:
            _mb.showerror("Ошибка", "Заказ не найден")
            return
        self.show_receipt_act_preview()

    def show_receipt_act_preview(self):
        """Показать предпросмотр акта приема"""
        report_gen = self.report_gen
        device = self.db.get_device(self.device_data.get("id"))
        if device:
            filename = report_gen.generate_receipt_act(device)
            if filename and os.path.exists(filename):
                with open(filename, encoding="utf-8") as f:
                    content = f.read()
                from reports.report_editor import load_template_data

                template = load_template_data("receipt")
                ActPreviewWindow(
                    self,
                    "Акт приема",
                    content,
                    self.colors,
                    "receipt",
                    device,
                    template,
                    settings=self.settings,
                )

    def show_completion_act_preview(self):
        """Показать предпросмотр акта выполненных работ"""
        report_gen = self.report_gen
        device = self.db.get_device(self.device_data.get("id"))
        if device:
            work_items_json = device.get("work_items", "")
            if work_items_json:
                work_manager = WorkItemsManager()
                work_manager.from_json(work_items_json)
                device["completed_work"] = work_manager.get_description_summary()

            filename = report_gen.generate_completion_act(device)
            if filename and os.path.exists(filename):
                with open(filename, encoding="utf-8") as f:
                    content = f.read()
                from reports.report_editor import load_template_data

                template = load_template_data("completion")
                ActPreviewWindow(
                    self,
                    "Акт выполненных работ",
                    content,
                    self.colors,
                    "completion",
                    device,
                    template,
                    settings=self.settings,
                )
