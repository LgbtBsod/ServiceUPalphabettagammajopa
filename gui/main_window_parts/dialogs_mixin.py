#!/usr/bin/env python3
"""DialogsMixin — прочие диалоги главного окна: настройки, словари,
сотрудники (+ селектор текущего сотрудника в шапке), активация лицензии,
редактор актов. См. AUDIT_REPORT_v25.md, Task T (перенесено из
main_window.py без изменения поведения)."""

from __future__ import annotations

import logging
from tkinter import messagebox

from gui.dialogs.dictionaries import DictionariesManagerWindow
from gui.dialogs.employees import EmployeesManagerWindow
from gui.dialogs.settings import SettingsWindow

logger = logging.getLogger(__name__)


class DialogsMixin:
    """Требует от финального класса ServiceCenterApp: self.root, self.db,
    self.colors, self.settings, self.employees_api."""

    def show_activation(self):
        """Показывает окно активации лицензии из главного окна."""
        try:
            from gui.dialogs.activation_dialog import ActivationDialog
            from utils.license_manager import LicenseManager

            lic = LicenseManager()
            dialog = ActivationDialog(self.root, lic, self.colors)
            self.root.wait_window(dialog)
        except Exception as e:
            import traceback

            traceback.print_exc()
            messagebox.showerror("Ошибка", f"Не удалось открыть активацию: {e}")

    def open_settings(self):
        """Открытие окна настроек"""
        SettingsWindow(self.root, self.settings, self)

    def open_dictionaries_manager(self):
        """Открытие менеджера словарей"""
        DictionariesManagerWindow(
            self.root, self.db, self.colors, settings=self.settings
        )

    def open_employees_manager(self):
        """Открытие окна управления сотрудниками."""
        if not self.employees_api:
            messagebox.showerror("Ошибка", "Модуль сотрудников недоступен")
            return
        EmployeesManagerWindow(
            self.root, self.employees_api, self.colors, settings=self.settings
        )

    def refresh_employee_selector(self):
        """Обновляет дропдаун выбора текущего сотрудника (после изменений в
        окне управления сотрудниками или при старте)."""
        if not self.employees_api or not hasattr(self, "employee_selector"):
            return
        try:
            from plugins.employees import ListEmployeesQuery

            employees = self.employees_api.list_employees(
                ListEmployeesQuery(active_only=True)
            )
            self._employee_by_label = {e.display_label: e.id for e in employees}
            values = ["Не выбран", *self._employee_by_label.keys()]
            self.employee_selector.configure(values=values)

            current_id = self.employees_api.get_current_employee_id()
            current_label = next(
                (
                    label
                    for label, eid in self._employee_by_label.items()
                    if eid == current_id
                ),
                "Не выбран",
            )
            self.employee_selector.set(current_label)
        except Exception as e:
            logger.error(f"Не удалось обновить список сотрудников: {e}", exc_info=True)

    def _on_employee_selected(self, label: str):
        """Callback выбора сотрудника в дропдауне."""
        if not self.employees_api:
            return
        employee_id = getattr(self, "_employee_by_label", {}).get(label)
        self.employees_api.set_current_employee(employee_id)

    def open_report_editor(self):
        """Открытие редактора актов (сразу, с вкладками приёма/выполненных работ)."""
        try:
            from reports.report_editor import ReportEditor

            ReportEditor(self.root, self.colors, settings=self.settings)
        except ImportError as e:
            messagebox.showerror(
                "Ошибка",
                f"Не удалось загрузить редактор: {e}\n\nУстановите reportlab: pip install reportlab",
            )
