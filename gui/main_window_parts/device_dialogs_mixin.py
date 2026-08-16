#!/usr/bin/env python3
"""DeviceDialogsMixin — открытие диалога создания/редактирования заказа и
окна истории клиента. См. AUDIT_REPORT_v25.md, Task T (перенесено из
main_window.py без изменения поведения)."""

from __future__ import annotations

import logging
from tkinter import messagebox
from typing import Any

from gui.dialogs.client_history import ClientHistoryWindow
from gui.dialogs.device_form import DeviceFormDialog
from utils.formatters import format_order_number_for_db, format_order_number_for_display

logger = logging.getLogger(__name__)


class DeviceDialogsMixin:
    """Требует от финального класса ServiceCenterApp: self.root, self.db,
    self.client_db, self.photo_manager, self.colors, self.settings,
    self.report_gen, self.employees_api, self.lock_api, self.tree."""

    def open_add_device_window(self):
        """Открытие окна добавления заказа"""
        dialog = DeviceFormDialog(
            self.root,
            self.db,
            self.client_db,
            self.photo_manager,
            self.colors,
            is_new=True,
            settings=self.settings,
            report_gen=self.report_gen,
            employees_api=self.employees_api,
        )
        self.root.wait_window(dialog)

        if dialog.result:
            self.load_devices()
            self.dashboard.update_stats()
            self.update_finance_display()
            self.update_status_bar(
                f"Создан заказ: #{format_order_number_for_display(dialog.result.get('order_number', ''))}"
            )

    def open_edit_device_window(self, device_data: dict[str, Any]):
        """Открытие окна редактирования заказа"""
        dialog = DeviceFormDialog(
            self.root,
            self.db,
            self.client_db,
            self.photo_manager,
            self.colors,
            is_new=False,
            device_data=device_data,
            settings=self.settings,
            report_gen=self.report_gen,
            employees_api=self.employees_api,
            lock_api=self.lock_api,
        )
        self.root.wait_window(dialog)

        if dialog.result:
            self.load_devices()
            self.dashboard.update_stats()
            self.update_finance_display()
            self.update_status_bar("Заказ обновлен")

    def _get_selected_device_or_warn(self):
        """Возвращает выбранное в таблице устройство или None.

        Показывает предупреждение, если заказ не выбран, или сообщение об
        ошибке, если устройство не найдено в БД. Общий код, ранее
        продублированный в print_receipt_act/print_completion_act/
        print_dual_acts (см. AUDIT_REPORT_v21.md).
        """
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Предупреждение", "Выберите заказ")
            return None

        order_number_display = self.tree.item(selected[0])["values"][0]
        device_id = self.get_device_id_by_order_number(order_number_display)
        device = self.db.get_device(device_id)

        if not device:
            messagebox.showerror(
                "Ошибка",
                f"Не удалось найти устройство с номером {order_number_display}",
            )
            return None
        return device

    def show_client_history(self):
        """Показ истории клиента"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Предупреждение", "Выберите заказ")
            return

        item = self.tree.item(selected[0])
        values = item["values"]
        if len(values) < 6:
            return

        client_name = values[4]
        client_phone = values[5]

        if client_name and client_phone:
            order_number_display = values[0]
            db_order_number = format_order_number_for_db(order_number_display)
            device = self.db.get_device_by_order_number(db_order_number)
            client_status = device.get("client_status", "Новый") if device else "Новый"

            ClientHistoryWindow(
                self.root,
                self.db,
                self.client_db,
                client_name,
                client_phone,
                client_status,
                self.colors,
                settings=self.settings,
                report_gen=self.report_gen,
                # Раньше это единственное место конструирования
                # ClientHistoryWindow не прокидывало employees_api/lock_api
                # вовсе (пре-существующий пробел, не регрессия этой сессии) —
                # редактирование заказа из истории клиента отсюда не
                # проставляло created_by и не участвовало в блокировках.
                # integration_manager сюда прокидывать не нужно —
                # уведомления идут через Kernel EventBus (см. save() в
                # device_form.py), а не прямой вызов из GUI.
                employees_api=self.employees_api,
                lock_api=self.lock_api,
            )
