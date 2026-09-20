#!/usr/bin/env python3

"""Окно управления ролями (roles/permissions) — см. TODO_RBAC_ROADMAP.md.

Работает ИСКЛЮЧИТЕЛЬНО через API плагина employees/roles, полученный из
ядра (core.get_module_api("roles")) — как и все GUI-диалоги, не обращается
к БД напрямую. Открывается кнопкой "🔑 Роли..." из EmployeesManagerWindow
(gui/dialogs/employees.py) — управление ролями логически вложено в
управление сотрудниками, отдельная кнопка в шапке главного окна не нужна.
"""

from tkinter import messagebox, ttk

import customtkinter as ctk

from gui.widgets.premium import PremiumCard


class RolesManagerWindow(ctk.CTkToplevel):
    """Окно управления ролями и полномочиями."""

    def __init__(self, parent, roles_api, colors: dict[str, str], settings=None):
        super().__init__(parent)
        self.parent = parent
        self.roles_api = roles_api
        self.colors = colors
        self.settings = settings
        self.current_role_id: int | None = None
        self.permission_vars: dict[str, ctk.BooleanVar] = {}

        self.title("Управление ролями")
        from utils.window_state import restore_window_geometry

        restore_window_geometry(
            self.settings,
            "roles",
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
        from utils.window_state import close_dialog_with_geometry

        close_dialog_with_geometry(self, self.settings, "roles")

    def create_widgets(self):
        main_container = ctk.CTkFrame(self, fg_color=self.colors["bg_primary"])
        main_container.pack(fill="both", expand=True, padx=10, pady=10)

        title_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            title_frame,
            text="🔑 Управление ролями",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(side="left")

        columns = ctk.CTkFrame(main_container, fg_color="transparent")
        columns.pack(fill="both", expand=True)

        # --- Левая колонка: список ролей ---
        left_card = PremiumCard(columns, self.colors)
        left_card.pack(side="left", fill="both", expand=True, padx=(0, 5))

        ctk.CTkLabel(
            left_card,
            text="Список ролей",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(anchor="w", padx=12, pady=(12, 8))

        tree_frame = ctk.CTkFrame(left_card, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.tree = ttk.Treeview(
            tree_frame, columns=("id", "name", "description"), show="headings", height=15
        )
        self.tree.heading("id", text="ID")
        self.tree.heading("name", text="Название")
        self.tree.heading("description", text="Описание")
        self.tree.column("id", width=40, minwidth=35)
        self.tree.column("name", width=120, minwidth=90)
        self.tree.column("description", width=180, minwidth=100)

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

        ctk.CTkLabel(form, text="Название*:", font=ctk.CTkFont(size=12, weight="bold")).pack(
            anchor="w", pady=(0, 3)
        )
        self.name_entry = ctk.CTkEntry(
            form,
            fg_color=self.colors["bg_tertiary"],
            border_color=self.colors["border"],
            height=35,
        )
        self.name_entry.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(form, text="Описание:", font=ctk.CTkFont(size=12, weight="bold")).pack(
            anchor="w", pady=(0, 3)
        )
        self.description_entry = ctk.CTkEntry(
            form,
            fg_color=self.colors["bg_tertiary"],
            border_color=self.colors["border"],
            height=35,
        )
        self.description_entry.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            form, text="Полномочия:", font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", pady=(0, 3))
        self.permissions_frame = ctk.CTkScrollableFrame(
            form, fg_color=self.colors["bg_tertiary"], height=220
        )
        self.permissions_frame.pack(fill="both", expand=True, pady=(0, 10))

        btn_frame = ctk.CTkFrame(form, fg_color="transparent")
        btn_frame.pack(fill="x")

        buttons = [
            ("💾 Сохранить", self.save_role, self.colors["accent"], "white"),
            ("➕ Добавить", self.add_role, self.colors["bg_tertiary"], self.colors["text_primary"]),
            ("🗑️ Удалить", self.delete_role, "#d13438", "white"),
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

        self.build_permissions_checklist()
        self.load_roles()

    def build_permissions_checklist(self):
        """Строит чекбоксы полномочий, сгруппированные по объекту (часть
        кода до первой точки — "EMPLOYEES.delete" -> группа "EMPLOYEES"),
        см. core.base.PermissionObject. Список полномочий не меняется в
        течение жизни диалога (сидируется при старте приложения), строится
        один раз при открытии."""
        try:
            permissions = self.roles_api.list_permissions()
        except Exception:
            permissions = []

        groups: dict[str, list] = {}
        for perm in permissions:
            object_name = perm.code.split(".", 1)[0]
            groups.setdefault(object_name, []).append(perm)

        self.permission_vars = {}
        for object_name in sorted(groups):
            ctk.CTkLabel(
                self.permissions_frame,
                text=object_name,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=self.colors["accent"],
            ).pack(anchor="w", padx=6, pady=(8, 2))
            for perm in sorted(groups[object_name], key=lambda p: p.code):
                var = ctk.BooleanVar(value=False)
                self.permission_vars[perm.code] = var
                ctk.CTkCheckBox(
                    self.permissions_frame,
                    text=perm.code.split(".", 1)[1] if "." in perm.code else perm.code,
                    variable=var,
                ).pack(anchor="w", padx=20, pady=1)

        if not permissions:
            ctk.CTkLabel(
                self.permissions_frame,
                text="Нет объявленных полномочий",
                text_color=self.colors["text_secondary"],
            ).pack(anchor="w", padx=6, pady=8)

    def load_roles(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        roles = self.roles_api.list_roles()
        for r in roles:
            self.tree.insert(
                "", "end", iid=str(r.id), values=(r.id, r.name, r.description or "")
            )

    def on_select(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        try:
            role_id = int(selected[0])
        except (ValueError, TypeError):
            return

        role = self.roles_api.get_role(role_id)
        if not role:
            return

        self.current_role_id = role.id
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, role.name)
        self.description_entry.delete(0, "end")
        self.description_entry.insert(0, role.description or "")
        for code, var in self.permission_vars.items():
            var.set(code in role.permission_codes)

    def _selected_permission_codes(self) -> frozenset[str]:
        return frozenset(code for code, var in self.permission_vars.items() if var.get())

    def add_role(self):
        from plugins.employees.roles import CreateRoleCommand

        name = self.name_entry.get().strip()
        if not name:
            messagebox.showerror("Ошибка", "Введите название роли")
            return

        role = self.roles_api.create_role(
            CreateRoleCommand(
                name=name,
                description=self.description_entry.get().strip() or None,
                permission_codes=self._selected_permission_codes(),
            )
        )
        if role:
            messagebox.showinfo("Успех", "✅ Роль добавлена")
            self.load_roles()
            self.clear_form()
        else:
            messagebox.showerror("Ошибка", "❌ Не удалось добавить (название уже занято?)")

    def save_role(self):
        from plugins.employees.roles import UpdateRoleCommand

        if not self.current_role_id:
            messagebox.showwarning("Предупреждение", "Сначала выберите роль")
            return

        name = self.name_entry.get().strip()
        if not name:
            messagebox.showerror("Ошибка", "Введите название роли")
            return

        ok = self.roles_api.update_role(
            UpdateRoleCommand(
                role_id=self.current_role_id,
                name=name,
                description=self.description_entry.get().strip() or None,
                permission_codes=self._selected_permission_codes(),
            )
        )
        if ok:
            messagebox.showinfo("Успех", "✅ Роль обновлена")
            self.load_roles()
            self.clear_form()
        else:
            messagebox.showerror("Ошибка", "❌ Не удалось обновить (название уже занято?)")

    def delete_role(self):
        if not self.current_role_id:
            messagebox.showwarning("Предупреждение", "Выберите роль для удаления")
            return
        if not messagebox.askyesno(
            "Подтверждение",
            "Удалить роль? Она будет снята со всех сотрудников, которым назначена.",
        ):
            return
        if self.roles_api.delete_role(self.current_role_id):
            messagebox.showinfo("Успех", "✅ Роль удалена")
            self.load_roles()
            self.clear_form()
        else:
            messagebox.showerror("Ошибка", "❌ Не удалось удалить роль")

    def clear_form(self):
        self.name_entry.delete(0, "end")
        self.description_entry.delete(0, "end")
        for var in self.permission_vars.values():
            var.set(False)
        self.current_role_id = None
