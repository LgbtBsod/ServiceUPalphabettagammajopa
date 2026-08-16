#!/usr/bin/env python3
"""ActsMixin — печать актов приёма/выполненных работ из главного окна
(включая режим "два акта на листе A4"). См. AUDIT_REPORT_v25.md, Task T
(перенесено из main_window.py без изменения поведения)."""

from __future__ import annotations

import os
import sys
from tkinter import messagebox

import customtkinter as ctk

from database import WorkItemsManager
from domain.constants import STATUS_ISSUED
from gui.dialogs.act_preview import ActPreviewWindow
from gui.widgets import ModernButton
from utils.formatters import format_order_number_for_display


class ActsMixin:
    """Требует от финального класса ServiceCenterApp: self.root, self.db,
    self.report_gen, self.colors, self.settings, self._get_selected_device_or_warn()
    (см. DeviceDialogsMixin)."""

    def print_receipt_act(self):
        """Печать акта приема"""
        try:
            device = self._get_selected_device_or_warn()
            if device is None:
                return

            filename = self.report_gen.generate_receipt_act(device)
            if filename and os.path.exists(filename):
                with open(filename, encoding="utf-8") as f:
                    content = f.read()

                order_number = format_order_number_for_display(
                    device.get("order_number", "")
                )
                from reports.report_editor import load_template_data

                template = load_template_data("receipt")
                # Окно предпросмотра само генерирует PDF с применением шаблона
                # редактора (header_text, поля, цвет, логотип). Печать/экспорт —
                # через кнопки в окне предпросмотра.
                ActPreviewWindow(
                    self.root,
                    f"Акт приема {order_number}",
                    content,
                    self.colors,
                    "receipt",
                    device,
                    template,
                    settings=self.settings,
                )
            else:
                messagebox.showerror("Ошибка", "❌ Не удалось создать файл акта")

        except Exception as e:
            messagebox.showerror("Ошибка", f"❌ Ошибка создания документа: {e!s}")

    def print_completion_act(self):
        """Печать акта выполненных работ"""
        try:
            device = self._get_selected_device_or_warn()
            if device is None:
                return

            work_items_json = device.get("work_items", "")
            if work_items_json:
                work_manager = WorkItemsManager()
                work_manager.from_json(work_items_json)
                device["completed_work"] = work_manager.get_description_summary()

            filename = self.report_gen.generate_completion_act(device)
            if filename and os.path.exists(filename):
                with open(filename, encoding="utf-8") as f:
                    content = f.read()

                order_number = format_order_number_for_display(
                    device.get("order_number", "")
                )
                from reports.report_editor import load_template_data

                template = load_template_data("completion")
                ActPreviewWindow(
                    self.root,
                    f"Акт выполненных работ {order_number}",
                    content,
                    self.colors,
                    "completion",
                    device,
                    template,
                    settings=self.settings,
                )

                # Печать акта выполненных работ = выдача устройства клиенту.
                # Меняем статус на «Выдан клиенту» (с подтверждением).
                if device.get("status") != STATUS_ISSUED:
                    if messagebox.askyesno(
                        "Выдача устройства",
                        f"Изменить статус заказа #{order_number} на «Выдан клиенту»?",
                    ) and self.db.update_device_status(
                        device.get("id"), STATUS_ISSUED
                    ):
                        self.load_devices()
                        self.dashboard.update_stats()
                        self.update_finance_display()
                        self.update_status_bar(f"Заказ #{order_number} выдан клиенту")
            else:
                messagebox.showerror("Ошибка", "❌ Не удалось создать файл акта")

        except Exception as e:
            messagebox.showerror("Ошибка", f"❌ Ошибка создания документа: {e!s}")

    def _ask_dual_print_mode(self):
        """Показывает кастомный диалог выбора режима печати двух актов.

        Возвращает: 'receipt2', 'completion2', 'both' или None (закрыто).
        """
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Два акта на листе A4")
        dialog.geometry("400x320")
        dialog.transient(self.root)
        dialog.grab_set()

        # Центрируем
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 400) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 320) // 2
        dialog.geometry(f"+{x}+{y}")

        result = {"choice": None}

        ctk.CTkLabel(
            dialog,
            text="📋 Выберите режим печати",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(pady=(20, 15))

        ctk.CTkLabel(
            dialog,
            text="Что напечатать на одном листе A4?",
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_secondary"],
        ).pack(pady=(0, 15))

        def _choose(value):
            result["choice"] = value
            dialog.destroy()

        ModernButton(
            dialog,
            self.colors,
            variant="primary",
            text="📄📄  2× Акт приёма",
            command=lambda: _choose("receipt2"),
            height=42,
            width=320,
        ).pack(pady=4)

        ModernButton(
            dialog,
            self.colors,
            variant="primary",
            text="🔧🔧  2× Акт выполненных работ",
            command=lambda: _choose("completion2"),
            height=42,
            width=320,
        ).pack(pady=4)

        ModernButton(
            dialog,
            self.colors,
            variant="secondary",
            text="📄🔧  Акт приёма + Акт работ",
            command=lambda: _choose("both"),
            height=42,
            width=320,
        ).pack(pady=4)

        ModernButton(
            dialog,
            self.colors,
            variant="secondary",
            text="✖ Отмена",
            command=dialog.destroy,
            height=36,
            width=320,
        ).pack(pady=(12, 4))

        self.root.wait_window(dialog)
        return result["choice"]

    def print_dual_acts(self):
        """Печать двух актов на одном листе A4 с выбором режима."""
        try:
            device = self._get_selected_device_or_warn()
            if device is None:
                return

            # work_items для акта выполненных работ
            work_items_json = device.get("work_items", "")
            if work_items_json:
                work_manager = WorkItemsManager()
                work_manager.from_json(work_items_json)
                device["completed_work"] = work_manager.get_description_summary()

            # Кастомный диалог выбора режима печати
            choice = self._ask_dual_print_mode()
            if choice is None:
                return  # пользователь закрыл окно

            # 'receipt2' → 2×receipt, 'completion2' → 2×completion, 'both' → receipt+completion
            if choice == "receipt2":
                act_type1, act_type2 = "receipt", "receipt"
                tpl_key = "receipt"
            elif choice == "completion2":
                act_type1, act_type2 = "completion", "completion"
                tpl_key = "completion"
            else:
                act_type1, act_type2 = "receipt", "completion"
                tpl_key = "receipt"

            from tkinter import filedialog

            from reports.report_renderer import ActPDFGenerator

            file_path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf")],
                initialfile=f"acts_{format_order_number_for_display(device.get('order_number', ''))}.pdf",
            )
            if not file_path:
                return

            from reports.report_editor import load_template_data

            tpl = load_template_data(tpl_key)
            gen = ActPDFGenerator(template_data=tpl)
            ok = gen.generate_dual_pdf(
                file_path, device, device, act_type1=act_type1, act_type2=act_type2
            )
            if ok:
                messagebox.showinfo(
                    "Успех", f"Два акта на листе A4 сохранены:\n{file_path}"
                )
                if sys.platform == "win32":
                    os.startfile(file_path)
            else:
                messagebox.showerror("Ошибка", "Не удалось создать PDF")
        except Exception as e:
            messagebox.showerror("Ошибка", f"❌ Ошибка: {e!s}")
