#!/usr/bin/env python3

"""Тесты для plugins/employees — второго реального плагина (после
plugins/clients), учёт сотрудников без авторизации + "текущий сотрудник"
для created_by/updated_by на заказах.
"""

import os
import tempfile

import pytest

from core.kernel import get_core, reset_core
from database.db_config import DatabaseConfig
from database.engines.sqlite_engine import SQLiteEngine
from database.sqlalchemy_models import Base
from plugins.employees import (
    CreateEmployeeCommand,
    EmployeeService,
    GetEmployeeByIdQuery,
    IEmployeeRepository,
    ListEmployeesQuery,
    UpdateEmployeeCommand,
)
from plugins.employees.repository import SqlAlchemyEmployeeRepository


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
def repository(engine) -> SqlAlchemyEmployeeRepository:
    return SqlAlchemyEmployeeRepository(engine)


@pytest.fixture
def service(repository) -> EmployeeService:
    return EmployeeService(repository)


class TestSqlAlchemyEmployeeRepository:
    def test_save_and_get_by_id(self, repository):
        from plugins.employees import EmployeeEntity

        employee = EmployeeEntity(id=0, full_name="Иван Иванов", login="ivanov")
        assert repository.save(employee) is True
        assert employee.id != 0

        fetched = repository.get_by_id(employee.id)
        assert fetched is not None
        assert fetched.full_name == "Иван Иванов"
        assert fetched.login == "ivanov"

    def test_get_by_login(self, repository):
        from plugins.employees import EmployeeEntity

        repository.save(EmployeeEntity(id=0, full_name="Пётр Петров", login="petrov"))
        found = repository.get_by_login("petrov")
        assert found is not None
        assert found.full_name == "Пётр Петров"

    def test_get_all_excludes_inactive_by_default(self, repository):
        from plugins.employees import EmployeeEntity

        active = EmployeeEntity(id=0, full_name="Активный", login="active1")
        inactive = EmployeeEntity(
            id=0, full_name="Неактивный", login="inactive1", is_active=False
        )
        repository.save(active)
        repository.save(inactive)

        all_active = repository.get_all(active_only=True)
        logins = {e.login for e in all_active}
        assert "active1" in logins
        assert "inactive1" not in logins

        everyone = repository.get_all(active_only=False)
        assert {"active1", "inactive1"}.issubset({e.login for e in everyone})


class TestEmployeeService:
    def test_create_employee(self, service):
        employee = service.create_employee(
            CreateEmployeeCommand(full_name="Иван Иванов", login="ivanov", phone="89991234567")
        )
        assert employee is not None
        assert employee.login == "ivanov"
        assert employee.phone.startswith("+7")

    def test_create_employee_rejects_duplicate_login(self, service):
        service.create_employee(CreateEmployeeCommand(full_name="Первый", login="dup"))
        second = service.create_employee(CreateEmployeeCommand(full_name="Второй", login="dup"))
        assert second is None

    def test_display_label_format(self, service):
        employee = service.create_employee(
            CreateEmployeeCommand(full_name="Иван Иванов", login="ivanov")
        )
        assert employee.display_label == "Иван Иванов — ivanov"

    def test_update_employee(self, service):
        employee = service.create_employee(
            CreateEmployeeCommand(full_name="Старое Имя", login="user1")
        )
        ok = service.update_employee(
            UpdateEmployeeCommand(employee_id=employee.id, full_name="Новое Имя")
        )
        assert ok is True
        updated = service.get_employee(GetEmployeeByIdQuery(employee_id=employee.id))
        assert updated.full_name == "Новое Имя"

    def test_list_employees(self, service):
        service.create_employee(CreateEmployeeCommand(full_name="A", login="a"))
        service.create_employee(CreateEmployeeCommand(full_name="B", login="b"))
        employees = service.list_employees(ListEmployeesQuery())
        assert len(employees) == 2

    def test_current_employee_roundtrip(self, service):
        employee = service.create_employee(
            CreateEmployeeCommand(full_name="Текущий", login="current1")
        )
        assert service.get_current_employee_id() is None

        assert service.set_current_employee(employee.id) is True
        assert service.get_current_employee_id() == employee.id
        assert service.get_current_employee().login == "current1"

        assert service.set_current_employee(None) is True
        assert service.get_current_employee_id() is None

    def test_cannot_select_inactive_employee(self, service):
        employee = service.create_employee(
            CreateEmployeeCommand(full_name="Неактивный", login="inactive2")
        )
        service.update_employee(
            UpdateEmployeeCommand(employee_id=employee.id, is_active=False)
        )
        assert service.set_current_employee(employee.id) is False
        assert service.get_current_employee_id() is None


class TestPluginDiscoveryIntegration:
    """Сквозной путь: core.initialize() -> discover('plugins', context=core) ->
    register_plugin() -> load() -> on_initialize() -> register_module('employees', ...).
    Оба плагина (clients + employees) должны загрузиться одновременно —
    первая реальная проверка PluginManager с более чем одним плагином,
    см. AUDIT_REPORT_v21.md (dependency-resolution ранее не проверялся)."""

    def test_discover_loads_both_plugins(self, engine):
        from plugins.clients import IClientRepository
        from plugins.clients.repository import SqlAlchemyClientRepository

        reset_core()
        core = get_core()
        core.initialize()
        try:
            core.register_service(IClientRepository, SqlAlchemyClientRepository(engine))
            core.register_service(IEmployeeRepository, SqlAlchemyEmployeeRepository(engine))

            loaded = core.services.plugin_manager.discover("plugins", context=core)

            assert "clients" in loaded
            assert "employees" in loaded

            api = core.get_module_api("employees")
            assert isinstance(api, EmployeeService)

            employee = core.call_module_method(
                "employees",
                "create_employee",
                CreateEmployeeCommand(full_name="Через Ядро", login="via_core"),
            )
            assert employee is not None
            assert employee.full_name == "Через Ядро"
        finally:
            reset_core()
