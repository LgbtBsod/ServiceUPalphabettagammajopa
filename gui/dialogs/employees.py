#!/usr/bin/env python3

"""Окно управления сотрудниками (без авторизации).

Работает ИСКЛЮЧИТЕЛЬНО через API плагина employees, полученный из ядра
(core.get_module_api("employees")) — как и все GUI-диалоги, не обращается к
БД напрямую, см. правило проекта о доступе к модулям только через ядро.
"""

import contextlib
from tkinter import messagebox, ttk

import customtkinter as ctk

from gui.widgets.premium import PremiumCard


class EmployeesManagerWindow(ctk.CTkToplevel):
    """Окно управления сотрудниками."""

    def __init__(self, parent, employees_api, colors: dict[str, str], settings=None):
        super().__init__(parent)
        self.parent = parent
        self.employees_api = employees_api
        self.colors = colors
        self.settings = settings
        self.current_employee_id: int | None = None

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

        self.phone_entry = self._labeled_entry(form, "Телефон:")
        self.position_entry = self._labeled_entry(form, "Должность:")

        self.active_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            form, text="Активен", variable=self.active_var
        ).pack(anchor="w", pady=(5, 15))

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
            messagebox.showwarning("Предупреждение", "Сначала введите ФИО")
            return
        try:
            login = self.employees_api.suggest_login(full_name)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сгенерировать логин: {e}")
            return
        self.login_entry.delete(0, "end")
        self.login_entry.insert(0, login)

    def _labeled_entry(self, parent, label: str) -> ctk.CTkEntry:
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
        return entry

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

    def add_employee(self):
        from plugins.employees import CreateEmployeeCommand

        full_name = self.name_entry.get().strip()
        login = self.login_entry.get().strip()
        if not full_name or not login:
            messagebox.showerror("Ошибка", "Заполните ФИО и логин")
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
            messagebox.showinfo("Успех", "✅ Сотрудник добавлен")
            self.load_employees()
            self.clear_form()
            self._refresh_main_window_selector()
        else:
            messagebox.showerror("Ошибка", "❌ Не удалось добавить (логин уже занят?)")

    def save_employee(self):
        from plugins.employees import UpdateEmployeeCommand

        if not self.current_employee_id:
            messagebox.showwarning("Предупреждение", "Сначала выберите сотрудника")
            return

        full_name = self.name_entry.get().strip()
        login = self.login_entry.get().strip()
        if not full_name or not login:
            messagebox.showerror("Ошибка", "Заполните ФИО и логин")
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
            messagebox.showinfo("Успех", "✅ Сотрудник обновлён")
            self.load_employees()
            self.clear_form()
            self.current_employee_id = None
            self._refresh_main_window_selector()
        else:
            messagebox.showerror("Ошибка", "❌ Не удалось обновить (логин уже занят?)")

    def delete_employee(self):
        if not self.current_employee_id:
            messagebox.showwarning("Предупреждение", "Выберите сотрудника для удаления")
            return
        if not messagebox.askyesno(
            "Подтверждение",
            "Удалить сотрудника? Записи, созданные им, сохранятся без привязки.",
        ):
            return
        if self.employees_api.delete_employee(self.current_employee_id):
            messagebox.showinfo("Успех", "✅ Сотрудник удалён")
            self.load_employees()
            self.clear_form()
            self.current_employee_id = None
            self._refresh_main_window_selector()
        else:
            messagebox.showerror("Ошибка", "❌ Не удалось удалить сотрудника")

    def clear_form(self):
        self.name_entry.delete(0, "end")
        self.login_entry.delete(0, "end")
        self.phone_entry.delete(0, "end")
        self.position_entry.delete(0, "end")
        self.active_var.set(True)
        self.current_employee_id = None

    def _refresh_main_window_selector(self):
        """Обновляет дропдаун выбора текущего сотрудника в главном окне,
        если он там есть (список сотрудников мог измениться)."""
        with contextlib.suppress(Exception):
            self.parent.refresh_employee_selector()
