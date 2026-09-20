"""Управление сотрудниками + ролями — Flet-эквивалент gui/dialogs/employees.py
+ gui/dialogs/roles_manager.py (классический интерфейс).

Тот же list+edit-card подход, что и views_dictionaries.py::DictionariesView
(ResponsiveRow: список слева, форма справа), тот же паттерн доступа к
модулям ядра, что и остальные Flet-вью (self.app.core.get_module_api(...),
см. _PhotosEditor в views_orders.py). Роли/полномочия — см.
TODO_RBAC_ROADMAP.md; roles_api может быть None (RBAC не подключён —
например, EmployeesPlugin не загрузился), тогда секция ролей не рисуется,
как и в классическом интерфейсе."""

from __future__ import annotations

import flet as ft

from . import theme


class EmployeesView:
    def __init__(self, app):
        self.app = app
        self.selected_employee_id: int | None = None
        self.selected_role_ids: set[int] = set()
        self.roles_mode = False  # False — редактирование сотрудника, True — ролей

    @property
    def employees_api(self):
        return self.app.core.get_module_api("employees")

    @property
    def roles_api(self):
        return self.app.core.get_module_api("roles")

    def render(self) -> ft.Control:
        return self._render_roles() if self.roles_mode else self._render_employees()

    # ── сотрудники ───────────────────────────────────────────

    def _render_employees(self) -> ft.Control:
        from plugins.employees import ListEmployeesQuery

        c = self.app.colors
        employees_api = self.employees_api
        roles_api = self.roles_api

        if employees_api is None:
            return ft.Container(
                ft.Text("Модуль сотрудников недоступен.", color=c["text_secondary"]),
                padding=30,
            )

        employees = employees_api.list_employees(ListEmployeesQuery(active_only=False))
        selected = next((e for e in employees if e.id == self.selected_employee_id), None)

        if selected and roles_api is not None:
            assigned_ids = {r.id for r in roles_api.get_employee_roles(selected.id)}
            if not self.selected_role_ids and assigned_ids:
                self.selected_role_ids = assigned_ids

        name_field = ft.TextField(label="ФИО*", value=(selected.full_name if selected else ""))
        login_field = ft.TextField(label="Логин*", value=(selected.login if selected else ""))
        phone_field = ft.TextField(label="Телефон", value=(selected.phone if selected else "") or "")
        position_field = ft.TextField(
            label="Должность", value=(selected.position if selected else "") or ""
        )
        active_switch = ft.Switch(label="Активен", value=selected.is_active if selected else True)

        def on_generate_login(_e) -> None:
            full_name = name_field.value.strip()
            if not full_name:
                self.app.show_snackbar("Сначала введите ФИО", error=True)
                return
            login_field.value = employees_api.suggest_login(full_name)
            self.app.page.update()

        def on_row_click(employee_id: int):
            def _handler(_e) -> None:
                self.selected_employee_id = employee_id
                self.selected_role_ids = set()
                self.app.rerender()

            return _handler

        def _validated() -> tuple[str, str] | None:
            full_name = name_field.value.strip()
            login = login_field.value.strip()
            if not full_name or not login:
                self.app.show_snackbar("Заполните ФИО и логин", error=True)
                return None
            return full_name, login

        def _sync_roles(employee_id: int) -> None:
            if roles_api is not None:
                roles_api.set_employee_roles(employee_id, self.selected_role_ids)

        def on_save(_e) -> None:
            from plugins.employees import CreateEmployeeCommand, UpdateEmployeeCommand

            validated = _validated()
            if validated is None:
                return
            full_name, login = validated

            if selected is None:
                employee = employees_api.create_employee(
                    CreateEmployeeCommand(
                        full_name=full_name,
                        login=login,
                        phone=phone_field.value.strip() or None,
                        position=position_field.value.strip() or None,
                    )
                )
                ok = employee is not None
                if ok:
                    _sync_roles(employee.id)
                message = "Сотрудник добавлен" if ok else "Не удалось добавить (логин уже занят?)"
            else:
                ok = employees_api.update_employee(
                    UpdateEmployeeCommand(
                        employee_id=selected.id,
                        full_name=full_name,
                        login=login,
                        phone=phone_field.value.strip() or None,
                        position=position_field.value.strip() or None,
                        is_active=active_switch.value,
                    )
                )
                if ok:
                    _sync_roles(selected.id)
                message = "Сотрудник обновлён" if ok else "Не удалось обновить (логин уже занят?)"

            self.app.show_snackbar(message, error=not ok)
            if ok:
                self.selected_employee_id = None
                self.selected_role_ids = set()
            self.app.rerender()

        def on_clear(_e) -> None:
            self.selected_employee_id = None
            self.selected_role_ids = set()
            self.app.rerender()

        def on_delete_confirmed(_e) -> None:
            self.app.page.pop_dialog()
            ok = employees_api.delete_employee(self.selected_employee_id)
            self.selected_employee_id = None
            self.selected_role_ids = set()
            self.app.show_snackbar(
                "Сотрудник удалён" if ok else "Не удалось удалить сотрудника", error=not ok
            )
            self.app.rerender()

        def on_delete_cancelled(_e) -> None:
            self.app.page.pop_dialog()

        def on_delete_click(_e) -> None:
            if selected is None:
                self.app.show_snackbar("Выберите сотрудника для удаления", error=True)
                return
            self.app.page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Удаление"),
                    content=ft.Text(
                        "Удалить сотрудника? Записи, созданные им, сохранятся без привязки."
                    ),
                    actions=[
                        ft.TextButton("Отмена", on_click=on_delete_cancelled),
                        ft.TextButton("Удалить", on_click=on_delete_confirmed),
                    ],
                )
            )

        def on_open_roles(_e) -> None:
            self.roles_mode = True
            self.app.rerender()

        if employees:
            rows: list[ft.Control] = [
                ft.ListTile(
                    title=ft.Text(e.full_name, size=13, color=c["text_primary"]),
                    subtitle=ft.Text(
                        f"{e.login}" + (f" · {e.position}" if e.position else "")
                        + ("" if e.is_active else " · неактивен"),
                        size=11, color=c["text_secondary"],
                    ),
                    selected=e.id == self.selected_employee_id,
                    selected_tile_color=c["accent"],
                    on_click=on_row_click(e.id),
                    dense=True,
                )
                for e in employees
            ]
        else:
            rows = [
                ft.Container(
                    ft.Text("Сотрудников пока нет.", size=12, color=c["text_secondary"]),
                    padding=20,
                )
            ]

        list_card = ft.Container(
            ft.Column(
                [
                    ft.Text(
                        "👥 Сотрудники", size=14, weight=ft.FontWeight.W_600,
                        color=c["text_primary"],
                    ),
                    ft.Container(height=8),
                    ft.Column(rows, spacing=0, scroll=ft.ScrollMode.AUTO, height=420),
                ],
            ),
            bgcolor=c["bg_card"], border_radius=12, padding=16, expand=True,
            border=theme.card_border(c["border"]),
        )

        roles_section: list[ft.Control] = []
        if roles_api is not None:
            all_roles = roles_api.list_roles()
            roles_section = [
                ft.Container(height=8),
                ft.Row(
                    [
                        ft.Text("Роли:", size=12, weight=ft.FontWeight.W_600, color=c["text_primary"]),
                        ft.Container(expand=True),
                        ft.TextButton("🔑 Управление ролями", on_click=on_open_roles),
                    ],
                ),
                ft.Container(
                    self._roles_checklist(all_roles, self.selected_role_ids)
                    if all_roles
                    else ft.Text("Нет ролей", size=12, color=c["text_secondary"]),
                    bgcolor=c["bg_secondary"], border_radius=8, padding=8,
                ),
            ]

        edit_card = ft.Container(
            ft.Column(
                [
                    ft.Text(
                        "✏️ Редактирование" if selected else "➕ Новый сотрудник",
                        size=14, weight=ft.FontWeight.W_600, color=c["text_primary"],
                    ),
                    ft.Container(height=8),
                    name_field,
                    ft.Row(
                        [login_field, ft.IconButton(icon=ft.Icons.CASINO, tooltip="Сгенерировать логин по ФИО", on_click=on_generate_login)],
                        spacing=6,
                    ),
                    phone_field,
                    position_field,
                    active_switch,
                    *roles_section,
                    ft.Container(height=8),
                    ft.Row(
                        [
                            ft.FilledButton(
                                "💾 Сохранить" if selected else "➕ Добавить", on_click=on_save,
                            ),
                            ft.OutlinedButton("✖ Очистить", on_click=on_clear),
                            ft.OutlinedButton(
                                "🗑 Удалить", on_click=on_delete_click, disabled=selected is None,
                            ),
                        ],
                        wrap=True, spacing=8,
                    ),
                ],
            ),
            bgcolor=c["bg_card"], border_radius=12, padding=16, expand=True,
            border=theme.card_border(c["border"]),
        )

        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            "Сотрудники", size=24, weight=ft.FontWeight.BOLD,
                            color=c["text_primary"],
                        ),
                    ],
                ),
                ft.Container(height=16),
                ft.ResponsiveRow(
                    [
                        ft.Container(list_card, col={"sm": 12, "md": 7}),
                        ft.Container(edit_card, col={"sm": 12, "md": 5}),
                    ],
                    spacing=16, run_spacing=16,
                ),
            ],
            spacing=0,
        )

    def _roles_checklist(self, all_roles: list, selected_ids: set[int]) -> ft.Control:
        def on_toggle(role_id: int):
            def _handler(e: ft.ControlEvent) -> None:
                if e.control.value:
                    self.selected_role_ids.add(role_id)
                else:
                    self.selected_role_ids.discard(role_id)

            return _handler

        return ft.Column(
            [
                ft.Checkbox(
                    label=role.name, value=role.id in selected_ids, on_change=on_toggle(role.id),
                )
                for role in all_roles
            ],
            spacing=0,
        )

    # ── роли ─────────────────────────────────────────────────

    def _render_roles(self) -> ft.Control:
        c = self.app.colors
        roles_api = self.roles_api
        if roles_api is None:
            self.roles_mode = False
            return self._render_employees()

        roles = roles_api.list_roles()
        selected_role_id = getattr(self, "_editing_role_id", None)
        selected_role = next((r for r in roles if r.id == selected_role_id), None)

        permissions = roles_api.list_permissions()
        groups: dict[str, list] = {}
        for perm in permissions:
            groups.setdefault(perm.code.split(".", 1)[0], []).append(perm)

        if not hasattr(self, "_role_permission_checks"):
            self._role_permission_checks: dict[str, bool] = {}
        if selected_role is not None and not self._role_permission_checks:
            self._role_permission_checks = {code: code in selected_role.permission_codes for code in (p.code for p in permissions)}

        name_field = ft.TextField(label="Название*", value=(selected_role.name if selected_role else ""))
        description_field = ft.TextField(
            label="Описание", value=(selected_role.description if selected_role else "") or ""
        )

        def on_row_click(role_id: int):
            def _handler(_e) -> None:
                self._editing_role_id = role_id
                self._role_permission_checks = {}
                self.app.rerender()

            return _handler

        def on_toggle_permission(code: str):
            def _handler(e: ft.ControlEvent) -> None:
                self._role_permission_checks[code] = e.control.value

            return _handler

        def _selected_codes() -> frozenset[str]:
            return frozenset(code for code, checked in self._role_permission_checks.items() if checked)

        def on_save(_e) -> None:
            from plugins.employees.roles import CreateRoleCommand, UpdateRoleCommand

            name = name_field.value.strip()
            if not name:
                self.app.show_snackbar("Введите название роли", error=True)
                return
            description = description_field.value.strip() or None
            if selected_role is None:
                role = roles_api.create_role(
                    CreateRoleCommand(name=name, description=description, permission_codes=_selected_codes())
                )
                ok = role is not None
                message = "Роль добавлена" if ok else "Не удалось добавить (название уже занято?)"
            else:
                ok = roles_api.update_role(
                    UpdateRoleCommand(
                        role_id=selected_role.id, name=name, description=description,
                        permission_codes=_selected_codes(),
                    )
                )
                message = "Роль обновлена" if ok else "Не удалось обновить (название уже занято?)"
            self.app.show_snackbar(message, error=not ok)
            if ok:
                self._editing_role_id = None
                self._role_permission_checks = {}
            self.app.rerender()

        def on_clear(_e) -> None:
            self._editing_role_id = None
            self._role_permission_checks = {}
            self.app.rerender()

        def on_delete_confirmed(_e) -> None:
            self.app.page.pop_dialog()
            ok = roles_api.delete_role(self._editing_role_id)
            self._editing_role_id = None
            self._role_permission_checks = {}
            self.app.show_snackbar("Роль удалена" if ok else "Не удалось удалить роль", error=not ok)
            self.app.rerender()

        def on_delete_cancelled(_e) -> None:
            self.app.page.pop_dialog()

        def on_delete_click(_e) -> None:
            if selected_role is None:
                self.app.show_snackbar("Выберите роль для удаления", error=True)
                return
            self.app.page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Удаление"),
                    content=ft.Text("Удалить роль? Она будет снята со всех сотрудников."),
                    actions=[
                        ft.TextButton("Отмена", on_click=on_delete_cancelled),
                        ft.TextButton("Удалить", on_click=on_delete_confirmed),
                    ],
                )
            )

        def on_back(_e) -> None:
            self.roles_mode = False
            self._editing_role_id = None
            self._role_permission_checks = {}
            self.app.rerender()

        if roles:
            rows: list[ft.Control] = [
                ft.ListTile(
                    title=ft.Text(r.name, size=13, color=c["text_primary"]),
                    subtitle=ft.Text(r.description or "", size=11, color=c["text_secondary"]),
                    selected=r.id == selected_role_id,
                    selected_tile_color=c["accent"],
                    on_click=on_row_click(r.id),
                    dense=True,
                )
                for r in roles
            ]
        else:
            rows = [ft.Container(ft.Text("Ролей пока нет.", size=12, color=c["text_secondary"]), padding=20)]

        list_card = ft.Container(
            ft.Column(
                [
                    ft.Text("🔑 Роли", size=14, weight=ft.FontWeight.W_600, color=c["text_primary"]),
                    ft.Container(height=8),
                    ft.Column(rows, spacing=0, scroll=ft.ScrollMode.AUTO, height=420),
                ],
            ),
            bgcolor=c["bg_card"], border_radius=12, padding=16, expand=True,
            border=theme.card_border(c["border"]),
        )

        permission_controls: list[ft.Control] = []
        for object_name in sorted(groups):
            permission_controls.append(
                ft.Text(object_name, size=12, weight=ft.FontWeight.W_600, color=c["accent"])
            )
            for perm in sorted(groups[object_name], key=lambda p: p.code):
                op = perm.code.split(".", 1)[1] if "." in perm.code else perm.code
                permission_controls.append(
                    ft.Checkbox(
                        label=op,
                        value=self._role_permission_checks.get(perm.code, False),
                        on_change=on_toggle_permission(perm.code),
                    )
                )

        edit_card = ft.Container(
            ft.Column(
                [
                    ft.Text(
                        "✏️ Редактирование" if selected_role else "➕ Новая роль",
                        size=14, weight=ft.FontWeight.W_600, color=c["text_primary"],
                    ),
                    ft.Container(height=8),
                    name_field,
                    description_field,
                    ft.Container(height=8),
                    ft.Text("Полномочия:", size=12, weight=ft.FontWeight.W_600, color=c["text_primary"]),
                    ft.Container(
                        ft.Column(permission_controls, spacing=0)
                        if permission_controls
                        else ft.Text("Нет объявленных полномочий", size=12, color=c["text_secondary"]),
                        bgcolor=c["bg_secondary"], border_radius=8, padding=8,
                    ),
                    ft.Container(height=8),
                    ft.Row(
                        [
                            ft.FilledButton(
                                "💾 Сохранить" if selected_role else "➕ Добавить", on_click=on_save,
                            ),
                            ft.OutlinedButton("✖ Очистить", on_click=on_clear),
                            ft.OutlinedButton(
                                "🗑 Удалить", on_click=on_delete_click, disabled=selected_role is None,
                            ),
                        ],
                        wrap=True, spacing=8,
                    ),
                ],
            ),
            bgcolor=c["bg_card"], border_radius=12, padding=16, expand=True,
            border=theme.card_border(c["border"]),
        )

        return ft.Column(
            [
                ft.Row(
                    [
                        ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="К сотрудникам", on_click=on_back),
                        ft.Text("Роли", size=24, weight=ft.FontWeight.BOLD, color=c["text_primary"]),
                    ],
                ),
                ft.Container(height=16),
                ft.ResponsiveRow(
                    [
                        ft.Container(list_card, col={"sm": 12, "md": 7}),
                        ft.Container(edit_card, col={"sm": 12, "md": 5}),
                    ],
                    spacing=16, run_spacing=16,
                ),
            ],
            spacing=0,
        )
