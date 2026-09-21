#!/usr/bin/env python3

"""Окно управления сотрудниками (без авторизации).

Работает ИСКЛЮЧИТЕЛЬНО через API плагина employees, полученный из ядра
(core.get_module_api("employees")) — как и все GUI-диалоги, не обращается к
БД напрямую, см. правило проекта о доступе к модулям только через ядро.
"""

import contextlib
import logging
from tkinter import EventType, messagebox, ttk

import customtkinter as ctk

from gui.widgets.premium import PremiumCard
from utils.messages import Msg

logger = logging.getLogger(__name__)


class EmployeesManagerWindow(ctk.CTkToplevel):
    """Окно управления сотрудниками."""

    def __init__(
        self, parent, employees_api, colors: dict[str, str], settings=None, roles_api=None
    ):
        super().__init__(parent)
        self.parent = parent
        self.employees_api = employees_api
        # Опционален (может быть None, если RBAC ещё не подключён/недоступен) —
        # без него секция "Роли" в форме и кнопка "🔑 Роли..." не показываются,
        # см. TODO_RBAC_ROADMAP.md.
        self.roles_api = roles_api
        self.colors = colors
        self.settings = settings
        self.current_employee_id: int | None = None
        self.role_vars: dict[int, ctk.BooleanVar] = {}
        # False только когда _load_employee_roles() реально не смог прочитать
        # роли сотрудника (см. ниже) — save_employee() сверяется с этим,
        # чтобы транзитная ошибка чтения не превратилась в молчаливое
        # затирание реальных ролей пустым набором при сохранении (workflow-
        # найденный баг: чекбоксы после сбоя выглядят как "ролей нет", и
        # обычное сохранение стирало бы их взаправду).
        self._roles_loaded_ok = True

        self.title("Управление сотрудниками")
        from utils.window_state import restore_window_geometry

        restore_window_geometry(
            self.settings,
            "employees",
            self,
            default_w=850,
            default_h=550,
            min_w=750,
            min_h=450,
        )

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._close_with_geometry)

        self.create_widgets()

    def _close_with_geometry(self):
        """Сохраняет геометрию окна в config и закрывает его."""
        from utils.window_state import close_dialog_with_geometry

        close_dialog_with_geometry(self, self.settings, "employees")

    def create_widgets(self):
        main_container = ctk.CTkFrame(self, fg_color=self.colors["bg_primary"])
        main_container.pack(fill="both", expand=True, padx=10, pady=10)

        title_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            title_frame,
            text="👥 Управление сотрудниками",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(side="left")

        columns = ctk.CTkFrame(main_container, fg_color="transparent")
        columns.pack(fill="both", expand=True)

        # --- Левая колонка: список ---
        left_card = PremiumCard(columns, self.colors)
        left_card.pack(side="left", fill="both", expand=True, padx=(0, 5))

        ctk.CTkLabel(
            left_card,
            text="Список сотрудников",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(anchor="w", padx=12, pady=(12, 8))

        tree_frame = ctk.CTkFrame(left_card, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("id", "name", "login", "position", "active"),
            show="headings",
            height=15,
        )
        self.tree.heading("id", text="ID")
        self.tree.heading("name", text="ФИО")
        self.tree.heading("login", text="Логин")
        self.tree.heading("position", text="Должность")
        self.tree.heading("active", text="Активен")
        self.tree.column("id", width=40, minwidth=35)
        self.tree.column("name", width=180, minwidth=120)
        self.tree.column("login", width=100, minwidth=80)
        self.tree.column("position", width=120, minwidth=80)
        self.tree.column("active", width=60, minwidth=50)

        from gui.widgets.auto_scroll import attach_auto_scrollbars

        attach_auto_scrollbars(tree_frame, self.tree)
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        # --- Правая колонка: форма ---
        right_card = PremiumCard(columns, self.colors)
        right_card.pack(side="right", fill="both", expand=True, padx=(5, 0))

        ctk.CTkLabel(
            right_card,
            text="✏️ Редактирование",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(anchor="w", padx=12, pady=(12, 8))

        form = ctk.CTkFrame(right_card, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.name_entry = self._labeled_entry(form, "ФИО*:")

        ctk.CTkLabel(form, text="Логин*:", font=ctk.CTkFont(size=12, weight="bold")).pack(
            anchor="w", pady=(0, 3)
        )
        login_row = ctk.CTkFrame(form, fg_color="transparent")
        login_row.pack(fill="x", pady=(0, 10))
        self.login_entry = ctk.CTkEntry(
            login_row,
            fg_color=self.colors["bg_tertiary"],
            border_color=self.colors["border"],
            height=35,
        )
        self.login_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(
            login_row,
            text="🎲",
            command=self.suggest_login,
            width=35,
            height=35,
            corner_radius=6,
            fg_color=self.colors["bg_tertiary"],
            text_color=self.colors["text_primary"],
        ).pack(side="left")
        self._attach_tooltip(login_row.winfo_children()[-1], "Сгенерировать логин по ФИО")

        self.phone_entry = self._labeled_entry(form, "Телефон:", phone_mask=True)
        self.position_entry = self._labeled_entry(form, "Должность:")

        self.active_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            form, text="Активен", variable=self.active_var
        ).pack(anchor="w", pady=(5, 10))

        if self.roles_api is not None:
            roles_header = ctk.CTkFrame(form, fg_color="transparent")
            roles_header.pack(fill="x", pady=(0, 3))
            ctk.CTkLabel(
                roles_header, text="Роли:", font=ctk.CTkFont(size=12, weight="bold")
            ).pack(side="left")
            ctk.CTkButton(
                roles_header,
                text="🔑 Роли...",
                command=self.open_roles_manager,
                height=22,
                width=90,
                corner_radius=6,
                fg_color=self.colors["bg_tertiary"],
                text_color=self.colors["text_primary"],
                font=ctk.CTkFont(size=11),
            ).pack(side="right")
            self.roles_frame = ctk.CTkScrollableFrame(
                form, fg_color=self.colors["bg_tertiary"], height=80
            )
            self.roles_frame.pack(fill="x", pady=(0, 15))
            self.build_roles_checklist()

        btn_frame = ctk.CTkFrame(form, fg_color="transparent")
        btn_frame.pack(fill="x")

        buttons = [
            ("💾 Сохранить", self.save_employee, self.colors["accent"], "white"),
            ("➕ Добавить", self.add_employee, self.colors["bg_tertiary"], self.colors["text_primary"]),
            ("🗑️ Удалить", self.delete_employee, "#d13438", "white"),
            ("✖ Очистить", self.clear_form, self.colors["bg_tertiary"], self.colors["text_primary"]),
        ]
        for i, (text, cmd, fg, tc) in enumerate(buttons):
            ctk.CTkButton(
                btn_frame,
                text=text,
                command=cmd,
                height=33,
                width=130,
                corner_radius=6,
                fg_color=fg,
                text_color=tc,
                font=ctk.CTkFont(size=12),
            ).grid(row=i // 2, column=i % 2, padx=3, pady=3, sticky="ew")
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        self.load_employees()

    def build_roles_checklist(self):
        """(Пере)строит чекбоксы доступных ролей в форме сотрудника —
        нужно вызывать заново после закрытия "🔑 Роли..." (список ролей мог
        измениться). Сохранённое состояние выбора для ТЕКУЩЕГО открытого
        сотрудника не теряется — оно всё равно будет перечитано on_select()."""
        for child in self.roles_frame.winfo_children():
            child.destroy()
        self.role_vars = {}
        try:
            roles = self.roles_api.list_roles()
        except Exception:
            logger.exception(Msg.Employee.LOG_ROLES_LIST_LOAD_FAILED)
            roles = []
        if not roles:
            ctk.CTkLabel(
                self.roles_frame, text="Нет ролей", text_color=self.colors["text_secondary"]
            ).pack(anchor="w", padx=6, pady=4)
            return
        for role in roles:
            var = ctk.BooleanVar(value=False)
            self.role_vars[role.id] = var
            ctk.CTkCheckBox(self.roles_frame, text=role.name, variable=var).pack(
                anchor="w", padx=6, pady=1
            )

    def open_roles_manager(self):
        from gui.dialogs.roles_manager import RolesManagerWindow

        dialog = RolesManagerWindow(self, self.roles_api, self.colors, settings=self.settings)
        self.wait_window(dialog)
        # Роли могли измениться (добавлены/удалены/переименованы) — форма
        # сотрудника должна отражать актуальный список при следующем показе.
        self.build_roles_checklist()
        if self.current_employee_id:
            self._load_employee_roles(self.current_employee_id)

    def _load_employee_roles(self, employee_id: int) -> None:
        try:
            assigned_ids = {r.id for r in self.roles_api.get_employee_roles(employee_id)}
            self._roles_loaded_ok = True
        except Exception:
            logger.exception(Msg.Employee.LOG_ROLES_LOAD_FAILED.format(employee_id=employee_id))
            assigned_ids = set()
            self._roles_loaded_ok = False
        for role_id, var in self.role_vars.items():
            var.set(role_id in assigned_ids)

    def _attach_tooltip(self, widget, text: str) -> None:
        """Прикрепляет tooltip к виджету, не прерывая инициализацию UI при ошибке."""
        try:
            from gui.widgets.tooltip import create_tooltip

            create_tooltip(widget, text)
        except Exception:
            pass

    def suggest_login(self):
        """Предлагает логин по введённому ФИО (кнопка 🎲)."""
        full_name = self.name_entry.get().strip()
        if not full_name:
            messagebox.showwarning(Msg.Title.WARNING, Msg.Employee.NAME_REQUIRED_FOR_LOGIN)
            return
        try:
            login = self.employees_api.suggest_login(full_name)
        except Exception as e:
            messagebox.showerror(Msg.Title.ERROR, Msg.Employee.LOGIN_GENERATION_FAILED.format(error=e))
            return
        self.login_entry.delete(0, "end")
        self.login_entry.insert(0, login)

    def _labeled_entry(self, parent, label: str, phone_mask: bool = False) -> ctk.CTkEntry:
        ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(size=12, weight="bold")).pack(
            anchor="w", pady=(0, 3)
        )
        entry = ctk.CTkEntry(
            parent,
            fg_color=self.colors["bg_tertiary"],
            border_color=self.colors["border"],
            height=35,
        )
        entry.pack(fill="x", pady=(0, 10))

        # Добавляем маску телефона если нужно
        if phone_mask:
            entry.bind("<FocusOut>", self._format_phone_input)
            entry.bind("<Key>", self._on_phone_key_press)

        return entry

    def _format_phone_input(self, event=None):
        """Маска телефона: форматирует ввод как +7 (XXX) XXX-XX-XX.

        Применяется только при потере фокуса, чтобы не мешать вводу.
        """
        import re

        try:
            text = event.widget.get()

            # Если это не событие потери фокуса, пропускаем.
            # event.type — tkinter.EventType (str-enum), чьё СТРОКОВОЕ
            # ЗНАЧЕНИЕ — числовой код события ("10"), а не имя члена enum'а:
            # сравнение с литералом "FocusOut" никогда не было равным, маска
            # не применялась ВООБЩЕ (тот же баг независимо продублирован в
            # gui/dialogs/device_form_parts/widgets_mixin.py).
            if event is None or event.type != EventType.FocusOut:
                return

            # Полная форматировка только при потере фокуса
            digits = re.sub(r"\D", "", text)

            # Обработка префиксов 8 или без кода
            if digits.startswith("8") and len(digits) == 11:
                digits = "7" + digits[1:]
            elif len(digits) == 10:
                digits = "7" + digits

            # Если цифр меньше 2, оставляем как есть или очищаем
            if len(digits) < 2:
                if digits:
                    event.widget.delete(0, "end")
                    event.widget.insert(0, "+7")
                return

            # Форматирование по маске
            if len(digits) <= 4:
                formatted = f"+7 ({digits[1:]}"
            elif len(digits) <= 7:
                formatted = f"+7 ({digits[1:4]}) {digits[4:]}"
            elif len(digits) <= 9:
                formatted = f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
            else:
                formatted = (
                    f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
                )

            # Обновляем поле только если формат отличается
            if formatted != text:
                event.widget.delete(0, "end")
                event.widget.insert(0, formatted)

        except Exception:
            pass

    def _on_phone_key_press(self, event=None):
        """Обработка нажатий клавиш в поле телефона.

        Разрешает только цифры, Backspace, Delete и навигацию.
        """
        # Разрешаем специальные клавиши
        if event.keysym in ('BackSpace', 'Delete', 'Left', 'Right', 'Home', 'End', 'Tab'):
            return None

        # Блокируем все кроме цифр
        if not event.char.isdigit():
            return 'break'

        return None

    def load_employees(self):
        from plugins.employees import ListEmployeesQuery

        for item in self.tree.get_children():
            self.tree.delete(item)
        employees = self.employees_api.list_employees(ListEmployeesQuery(active_only=False))
        for e in employees:
            self.tree.insert(
                "",
                "end",
                iid=str(e.id),
                values=(e.id, e.full_name, e.login, e.position or "", "Да" if e.is_active else "Нет"),
            )

    def on_select(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        try:
            employee_id = int(selected[0])
        except (ValueError, TypeError):
            return

        from plugins.employees import GetEmployeeByIdQuery

        employee = self.employees_api.get_employee(GetEmployeeByIdQuery(employee_id=employee_id))
        if not employee:
            return

        self.current_employee_id = employee.id
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, employee.full_name)
        self.login_entry.delete(0, "end")
        self.login_entry.insert(0, employee.login)
        self.phone_entry.delete(0, "end")
        self.phone_entry.insert(0, employee.phone or "")
        self.position_entry.delete(0, "end")
        self.position_entry.insert(0, employee.position or "")
        self.active_var.set(employee.is_active)
        if self.roles_api is not None:
            self._load_employee_roles(employee.id)

    def _selected_role_ids(self) -> set[int]:
        return {role_id for role_id, var in self.role_vars.items() if var.get()}

    def add_employee(self):
        from plugins.employees import CreateEmployeeCommand

        full_name = self.name_entry.get().strip()
        login = self.login_entry.get().strip()
        if not full_name or not login:
            messagebox.showerror(Msg.Title.ERROR, Msg.Employee.FIELDS_REQUIRED)
            return

        employee = self.employees_api.create_employee(
            CreateEmployeeCommand(
                full_name=full_name,
                login=login,
                phone=self.phone_entry.get().strip() or None,
                position=self.position_entry.get().strip() or None,
            )
        )
        if employee:
            if self.roles_api is not None:
                self.roles_api.set_employee_roles(employee.id, self._selected_role_ids())
            messagebox.showinfo(Msg.Title.SUCCESS, Msg.Employee.ADDED)
            self.load_employees()
            self.clear_form()
            self._refresh_main_window_selector()
        else:
            messagebox.showerror(Msg.Title.ERROR, Msg.Employee.ADD_FAILED)

    def save_employee(self):
        from plugins.employees import UpdateEmployeeCommand

        if not self.current_employee_id:
            messagebox.showwarning(Msg.Title.WARNING, Msg.Employee.SELECT_FIRST)
            return

        full_name = self.name_entry.get().strip()
        login = self.login_entry.get().strip()
        if not full_name or not login:
            messagebox.showerror(Msg.Title.ERROR, Msg.Employee.FIELDS_REQUIRED)
            return

        ok = self.employees_api.update_employee(
            UpdateEmployeeCommand(
                employee_id=self.current_employee_id,
                full_name=full_name,
                login=login,
                phone=self.phone_entry.get().strip() or None,
                position=self.position_entry.get().strip() or None,
                is_active=self.active_var.get(),
            )
        )
        if ok:
            if self.roles_api is not None:
                if self._roles_loaded_ok:
                    self.roles_api.set_employee_roles(
                        self.current_employee_id, self._selected_role_ids()
                    )
                else:
                    # Роли сотрудника не удалось прочитать при открытии формы
                    # (см. _load_employee_roles) — чекбоксы сейчас не отражают
                    # реальное назначение, сохранять их как есть означало бы
                    # молча стереть настоящие роли пустым/неполным набором.
                    messagebox.showwarning(Msg.Title.WARNING, Msg.Employee.ROLES_NOT_SAVED)
            messagebox.showinfo(Msg.Title.SUCCESS, Msg.Employee.UPDATED)
            self.load_employees()
            self.clear_form()
            self.current_employee_id = None
            self._refresh_main_window_selector()
        else:
            messagebox.showerror(Msg.Title.ERROR, Msg.Employee.UPDATE_FAILED)

    def delete_employee(self):
        if not self.current_employee_id:
            messagebox.showwarning(Msg.Title.WARNING, Msg.Employee.SELECT_TO_DELETE)
            return
        if not messagebox.askyesno(Msg.Title.CONFIRM, Msg.Employee.DELETE_CONFIRM):
            return
        if self.employees_api.delete_employee(self.current_employee_id):
            messagebox.showinfo(Msg.Title.SUCCESS, Msg.Employee.DELETED)
            self.load_employees()
            self.clear_form()
            self.current_employee_id = None
            self._refresh_main_window_selector()
        else:
            messagebox.showerror(Msg.Title.ERROR, Msg.Employee.DELETE_FAILED)

    def clear_form(self):
        self.name_entry.delete(0, "end")
        self.login_entry.delete(0, "end")
        self.phone_entry.delete(0, "end")
        self.position_entry.delete(0, "end")
        self.active_var.set(True)
        for var in self.role_vars.values():
            var.set(False)
        self.current_employee_id = None

    def _refresh_main_window_selector(self):
        """Обновляет дропдаун выбора текущего сотрудника в главном окне,
        если он там есть (список сотрудников мог измениться)."""
        with contextlib.suppress(Exception):
            self.parent.refresh_employee_selector()
