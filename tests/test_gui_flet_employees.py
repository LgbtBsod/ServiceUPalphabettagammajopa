#!/usr/bin/env python3

"""Тесты для gui_flet/views_employees.py — Flet-эквивалент
gui/dialogs/employees.py + gui/dialogs/roles_manager.py (parity-разрыв,
закрытый в этой сессии — см. TODO_RBAC_ROADMAP.md и gui_flet/app.py).

Реальные EmployeeService/RoleService поверх временной SQLite БД (тот же
паттерн, что tests/test_plugins_employees_roles.py) — рендер и Page
фейковые (_FakePage/_walk/_find/_find_button из tests/test_gui_flet.py,
тот же подход, что и остальные gui_flet-тесты)."""

import os
import tempfile

import pytest

from database.db_config import DatabaseConfig
from database.engines.sqlite_engine import SQLiteEngine
from database.sqlalchemy_models import Base
from gui_flet.theme import colors
from gui_flet.views_employees import EmployeesView
from plugins.employees import EmployeeService, ListEmployeesQuery
from plugins.employees.repository import SqlAlchemyEmployeeRepository
from plugins.employees.roles import RoleService
from plugins.employees.roles_repository import SqlAlchemyRoleRepository
from tests.test_gui_flet import _FakePage, _find, _find_button
from utils.messages import Msg


@pytest.fixture
def engine():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    eng = SQLiteEngine(DatabaseConfig(database=path))
    Base.metadata.create_all(eng.get_engine())
    yield eng
    eng.dispose()
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def employee_service(engine) -> EmployeeService:
    return EmployeeService(SqlAlchemyEmployeeRepository(engine))


@pytest.fixture
def role_service(engine) -> RoleService:
    return RoleService(SqlAlchemyRoleRepository(engine))


class _Core:
    def __init__(self, employee_service, role_service=None):
        self._apis = {"employees": employee_service, "roles": role_service}

    def get_module_api(self, name):
        return self._apis.get(name)


class _FakeApp:
    def __init__(self, employee_service, role_service=None):
        self.core = _Core(employee_service, role_service)
        self.colors = colors("light")
        self.page = _FakePage()
        self.snackbars = []

    def show_snackbar(self, message, error=False):
        self.snackbars.append((message, error))

    def rerender(self):
        pass


def _all_employees(employee_service):
    return employee_service.list_employees(ListEmployeesQuery(active_only=False))


class _FakeEvent:
    """Реальный Flet передаёт on_change(e) с e.control == сам контрол
    (обновлённое значение уже в e.control.value) — тесты, меняющие
    checkbox.value напрямую, должны сами эмулировать этот вызов, иначе
    обработчик (который читает e.control.value, а не сам объект checkbox)
    никогда не срабатывает."""

    def __init__(self, control):
        self.control = control


class TestEmployeesViewBasicCrud:
    def test_add_employee(self, employee_service):
        app = _FakeApp(employee_service)
        view = EmployeesView(app)
        form = view.render()

        _find(form, label="ФИО*").value = "Иван Иванов"
        _find(form, label="Логин*").value = "ivanov"
        _find_button(form, "➕ Добавить").on_click(None)

        assert [e.login for e in _all_employees(employee_service)] == ["ivanov"]
        assert app.snackbars[-1] == (Msg.Employee.ADDED, False)

    def test_add_employee_rejects_empty_login(self, employee_service):
        app = _FakeApp(employee_service)
        view = EmployeesView(app)
        form = view.render()

        _find(form, label="ФИО*").value = "Без логина"
        _find_button(form, "➕ Добавить").on_click(None)

        assert _all_employees(employee_service) == []
        assert app.snackbars[-1][1] is True

    def test_edit_existing_employee_preloads_fields(self, employee_service):
        from plugins.employees import CreateEmployeeCommand

        employee = employee_service.create_employee(
            CreateEmployeeCommand(full_name="Старое Имя", login="edituser")
        )
        app = _FakeApp(employee_service)
        view = EmployeesView(app)
        view.selected_employee_id = employee.id
        form = view.render()

        assert _find(form, label="ФИО*").value == "Старое Имя"
        assert _find(form, label="Логин*").value == "edituser"

    def test_save_updates_employee(self, employee_service):
        from plugins.employees import CreateEmployeeCommand

        employee = employee_service.create_employee(
            CreateEmployeeCommand(full_name="Старое Имя", login="upduser")
        )
        app = _FakeApp(employee_service)
        view = EmployeesView(app)
        view.selected_employee_id = employee.id
        form = view.render()

        _find(form, label="ФИО*").value = "Новое Имя"
        _find_button(form, "💾 Сохранить").on_click(None)

        updated = _all_employees(employee_service)[0]
        assert updated.full_name == "Новое Имя"

    def test_delete_employee_via_confirm_dialog(self, employee_service):
        from plugins.employees import CreateEmployeeCommand

        employee = employee_service.create_employee(
            CreateEmployeeCommand(full_name="К удалению", login="deluser")
        )
        app = _FakeApp(employee_service)
        view = EmployeesView(app)
        view.selected_employee_id = employee.id
        form = view.render()

        _find_button(form, "🗑 Удалить").on_click(None)
        assert len(app.page.dialogs) == 1
        # AlertDialog хранит кнопки подтверждения в .actions, а не
        # .controls/.content — _walk()/_find_button() их не обходят (тот же
        # паттерн понадобился бы любому другому тесту confirm-диалога в этом
        # файле, см. tests/test_gui_flet.py::_walk).
        confirm_button = app.page.dialogs[0].actions[1]
        confirm_button.on_click(None)

        assert _all_employees(employee_service) == []
        assert app.page.dialogs == []


class TestEmployeesViewRoleAssignment:
    def test_roles_section_hidden_without_role_service(self, employee_service):
        app = _FakeApp(employee_service)
        form = EmployeesView(app).render()
        assert _find_button(form, "🔑 Управление ролями") is None

    def test_roles_section_shown_with_role_service(self, employee_service, role_service):
        app = _FakeApp(employee_service, role_service)
        form = EmployeesView(app).render()
        assert _find_button(form, "🔑 Управление ролями") is not None

    def test_assigning_role_on_create_persists(self, employee_service, role_service):
        from plugins.employees.roles import CreateRoleCommand

        role = role_service.create_role(CreateRoleCommand(name="viewer"))
        app = _FakeApp(employee_service, role_service)
        view = EmployeesView(app)
        form = view.render()

        _find(form, label="ФИО*").value = "С Ролью"
        _find(form, label="Логин*").value = "roleduser"
        view.selected_role_ids = {role.id}
        _find_button(form, "➕ Добавить").on_click(None)

        employee = _all_employees(employee_service)[0]
        assigned = {r.name for r in role_service.get_employee_roles(employee.id)}
        assert assigned == {"viewer"}

    def test_edit_preloads_assigned_roles(self, employee_service, role_service):
        from plugins.employees import CreateEmployeeCommand
        from plugins.employees.roles import CreateRoleCommand

        employee = employee_service.create_employee(
            CreateEmployeeCommand(full_name="Т", login="preloadroles")
        )
        role = role_service.create_role(CreateRoleCommand(name="manager"))
        role_service.set_employee_roles(employee.id, {role.id})

        app = _FakeApp(employee_service, role_service)
        view = EmployeesView(app)
        view.selected_employee_id = employee.id
        view.render()

        assert view.selected_role_ids == {role.id}


class TestEmployeesViewRolesManagement:
    def test_open_roles_manager_switches_mode(self, employee_service, role_service):
        app = _FakeApp(employee_service, role_service)
        view = EmployeesView(app)
        form = view.render()

        _find_button(form, "🔑 Управление ролями").on_click(None)
        assert view.roles_mode is True

    def test_create_role_with_permission(self, employee_service, role_service):
        role_service._repo.ensure_permission("EMPLOYEES.delete")
        app = _FakeApp(employee_service, role_service)
        view = EmployeesView(app)
        view.roles_mode = True
        form = view.render()

        _find(form, label="Название*").value = "deleter"
        checkbox = _find(form, label="delete")
        assert checkbox is not None
        checkbox.value = True
        # Setting .value alone doesn't update the view's backing
        # _role_permission_checks dict — on_save() reads that dict, not the
        # control — real Flet fires on_change on click, so the test does too.
        checkbox.on_change(_FakeEvent(checkbox))
        _find_button(form, "➕ Добавить").on_click(None)

        created = next(r for r in role_service.list_roles() if r.name == "deleter")
        assert created.permission_codes == {"EMPLOYEES.delete"}

    def test_back_button_returns_to_employees_mode(self, employee_service, role_service):
        app = _FakeApp(employee_service, role_service)
        view = EmployeesView(app)
        view.roles_mode = True
        form = view.render()

        back_button = _find(form, tooltip="К сотрудникам")
        assert back_button is not None
        back_button.on_click(None)
        assert view.roles_mode is False
