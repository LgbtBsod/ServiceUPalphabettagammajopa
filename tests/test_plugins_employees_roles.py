#!/usr/bin/env python3

"""Тесты для plugins/employees/roles.py + roles_repository.py — ролевая
модель (roles/permissions/employee_roles), см. TODO_RBAC_ROADMAP.md.

Тот же паттерн, что tests/test_plugins_employees.py: временная SQLite БД
через SQLiteEngine + Base.metadata.create_all, реальный репозиторий (не мок).
"""

import os
import tempfile

import pytest

from core.base import PermissionObject
from database.db_config import DatabaseConfig
from database.engines.sqlite_engine import SQLiteEngine
from database.sqlalchemy_models import Base
from plugins.employees import EmployeeService
from plugins.employees.repository import SqlAlchemyEmployeeRepository
from plugins.employees.roles import (
    CreateRoleCommand,
    RoleService,
    UpdateRoleCommand,
)
from plugins.employees.roles_repository import SqlAlchemyRoleRepository


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
def role_repository(engine) -> SqlAlchemyRoleRepository:
    return SqlAlchemyRoleRepository(engine)


@pytest.fixture
def role_service(role_repository) -> RoleService:
    return RoleService(role_repository)


@pytest.fixture
def employee_repository(engine) -> SqlAlchemyEmployeeRepository:
    return SqlAlchemyEmployeeRepository(engine)


@pytest.fixture
def employee_service(employee_repository) -> EmployeeService:
    return EmployeeService(employee_repository)


class TestSqlAlchemyRoleRepository:
    def test_ensure_permission_is_idempotent(self, role_repository):
        p1 = role_repository.ensure_permission("DEVICES.create", "Создание заказа")
        p2 = role_repository.ensure_permission("DEVICES.create", "другое описание — не должно перезаписать")
        assert p1.id == p2.id
        assert len(role_repository.list_permissions()) == 1

    def test_save_and_get_role_with_permissions(self, role_repository):
        from plugins.employees.roles import RoleEntity

        role_repository.ensure_permission("DEVICES.create")
        role_repository.ensure_permission("DEVICES.delete")
        role = RoleEntity(
            id=0,
            name="manager",
            description="Менеджер",
            permission_codes=frozenset({"DEVICES.create", "DEVICES.delete"}),
        )
        assert role_repository.save_role(role) is True
        assert role.id != 0

        fetched = role_repository.get_role_by_id(role.id)
        assert fetched.name == "manager"
        assert fetched.permission_codes == {"DEVICES.create", "DEVICES.delete"}

    def test_save_role_replaces_permission_set(self, role_repository):
        from plugins.employees.roles import RoleEntity

        role_repository.ensure_permission("A.read")
        role_repository.ensure_permission("A.write")
        role = RoleEntity(id=0, name="r1", permission_codes=frozenset({"A.read"}))
        role_repository.save_role(role)

        role.permission_codes = frozenset({"A.write"})
        role_repository.save_role(role)

        fetched = role_repository.get_role_by_id(role.id)
        assert fetched.permission_codes == {"A.write"}

    def test_save_role_ignores_unknown_permission_code(self, role_repository):
        from plugins.employees.roles import RoleEntity

        role = RoleEntity(id=0, name="r2", permission_codes=frozenset({"NOPE.read"}))
        assert role_repository.save_role(role) is True
        fetched = role_repository.get_role_by_id(role.id)
        assert fetched.permission_codes == frozenset()

    def test_delete_role_cascades_role_permissions(self, role_repository):
        from plugins.employees.roles import RoleEntity

        role_repository.ensure_permission("A.read")
        role = RoleEntity(id=0, name="r3", permission_codes=frozenset({"A.read"}))
        role_repository.save_role(role)

        assert role_repository.delete_role(role.id) is True
        assert role_repository.get_role_by_id(role.id) is None

    def test_employee_roles_roundtrip(self, role_repository, employee_repository):
        from plugins.employees import EmployeeEntity
        from plugins.employees.roles import RoleEntity

        employee = EmployeeEntity(id=0, full_name="Иван", login="ivan_roles")
        employee_repository.save(employee)

        role_repository.ensure_permission("A.read")
        role_repository.ensure_permission("B.write")
        role_a = RoleEntity(id=0, name="ra", permission_codes=frozenset({"A.read"}))
        role_b = RoleEntity(id=0, name="rb", permission_codes=frozenset({"B.write"}))
        role_repository.save_role(role_a)
        role_repository.save_role(role_b)

        assert role_repository.employee_has_any_roles(employee.id) is False

        role_repository.set_employee_roles(employee.id, {role_a.id, role_b.id})
        assert role_repository.get_employee_role_ids(employee.id) == {role_a.id, role_b.id}
        assert role_repository.get_employee_permission_codes(employee.id) == {
            "A.read",
            "B.write",
        }
        assert role_repository.employee_has_any_roles(employee.id) is True

        # Замена набора целиком, не слияние
        role_repository.set_employee_roles(employee.id, {role_a.id})
        assert role_repository.get_employee_role_ids(employee.id) == {role_a.id}
        assert role_repository.get_employee_permission_codes(employee.id) == {"A.read"}


class TestRoleService:
    def test_create_role_rejects_duplicate_name(self, role_service):
        role_service.create_role(CreateRoleCommand(name="dup"))
        second = role_service.create_role(CreateRoleCommand(name="dup"))
        assert second is None

    def test_update_role_permission_codes(self, role_service, role_repository):
        role_repository.ensure_permission("A.read")
        role = role_service.create_role(CreateRoleCommand(name="r"))
        ok = role_service.update_role(
            UpdateRoleCommand(role_id=role.id, permission_codes=frozenset({"A.read"}))
        )
        assert ok is True
        assert role_service.get_role(role.id).permission_codes == {"A.read"}

    def test_update_role_none_permission_codes_keeps_existing(self, role_service, role_repository):
        role_repository.ensure_permission("A.read")
        role = role_service.create_role(
            CreateRoleCommand(name="r", permission_codes=frozenset({"A.read"}))
        )
        ok = role_service.update_role(UpdateRoleCommand(role_id=role.id, description="новое"))
        assert ok is True
        updated = role_service.get_role(role.id)
        assert updated.description == "новое"
        assert updated.permission_codes == {"A.read"}

    def test_has_permission_true_when_role_grants_it(self, role_service, employee_repository):
        from plugins.employees import EmployeeEntity

        employee = EmployeeEntity(id=0, full_name="П", login="perm1")
        employee_repository.save(employee)
        role_service._repo.ensure_permission("EMPLOYEES.delete")
        role = role_service.create_role(
            CreateRoleCommand(name="deleter", permission_codes=frozenset({"EMPLOYEES.delete"}))
        )
        role_service.set_employee_roles(employee.id, {role.id})

        assert role_service.has_permission(employee.id, "EMPLOYEES.delete") is True
        assert role_service.has_permission(employee.id, "EMPLOYEES.create") is False

    def test_seed_default_rbac_creates_admin_with_all_permissions(
        self, role_service, employee_repository
    ):
        from plugins.employees import EmployeeEntity

        e1 = EmployeeEntity(id=0, full_name="Один", login="seed1")
        e2 = EmployeeEntity(id=0, full_name="Два", login="seed2")
        employee_repository.save(e1)
        employee_repository.save(e2)

        declared = [
            PermissionObject(name="DEVICES", operations=("create", "delete")),
            PermissionObject(name="EMPLOYEES", operations=("manage_roles",)),
        ]
        role_service.seed_default_rbac(declared, [e1.id, e2.id])

        admin = role_service._repo.get_role_by_name("admin")
        assert admin is not None
        assert admin.permission_codes == {
            "DEVICES.create",
            "DEVICES.delete",
            "EMPLOYEES.manage_roles",
        }
        assert role_service.get_employee_roles(e1.id)[0].name == "admin"
        assert role_service.get_employee_roles(e2.id)[0].name == "admin"

    def test_seed_default_rbac_is_idempotent_and_preserves_manual_reassignment(
        self, role_service, employee_repository
    ):
        from plugins.employees import EmployeeEntity

        e1 = EmployeeEntity(id=0, full_name="Один", login="seed3")
        employee_repository.save(e1)
        declared = [PermissionObject(name="X", operations=("read",))]

        role_service.seed_default_rbac(declared, [e1.id])
        # Сотрудника вручную переназначили на другую роль (не admin)
        custom_role = role_service.create_role(CreateRoleCommand(name="viewer"))
        role_service.set_employee_roles(e1.id, {custom_role.id})

        # Повторный сид (как при каждом следующем старте приложения) не
        # должен молча вернуть сотрудника обратно на admin — у него УЖЕ
        # есть назначенная роль.
        role_service.seed_default_rbac(declared, [e1.id])
        roles = {r.name for r in role_service.get_employee_roles(e1.id)}
        assert roles == {"viewer"}

    def test_seed_default_rbac_tops_up_admin_with_new_permissions(self, role_service):
        first_pass = [PermissionObject(name="X", operations=("read",))]
        role_service.seed_default_rbac(first_pass, [])

        second_pass = [
            PermissionObject(name="X", operations=("read",)),
            PermissionObject(name="Y", operations=("write",)),
        ]
        role_service.seed_default_rbac(second_pass, [])

        admin = role_service._repo.get_role_by_name("admin")
        assert admin.permission_codes == {"X.read", "Y.write"}


class TestEmployeeServiceHasPermissionWithRoleService:
    def test_defaults_to_true_without_role_service(self, employee_service):
        """Обратная совместимость: EmployeeService(repo) без role_service —
        поведение заглушки не изменилось."""
        assert employee_service.has_permission(None, "ANYTHING.delete") is True
        assert employee_service.has_permission(999, "ANYTHING.delete") is True

    def test_real_check_when_role_service_attached(
        self, employee_repository, role_service
    ):
        from plugins.employees import EmployeeEntity

        service = EmployeeService(employee_repository)
        employee_repository.save(EmployeeEntity(id=0, full_name="Т", login="attach1"))
        employee = employee_repository.get_by_login("attach1")

        service.attach_role_service(role_service)

        # Нет назначенных ролей — реальная проверка отказывает
        assert service.has_permission(employee.id, "EMPLOYEES.delete") is False
        # employee_id=None — тоже отказ (раньше был True)
        assert service.has_permission(None, "EMPLOYEES.delete") is False

        role_service._repo.ensure_permission("EMPLOYEES.delete")
        role = role_service.create_role(
            CreateRoleCommand(name="deleter2", permission_codes=frozenset({"EMPLOYEES.delete"}))
        )
        role_service.set_employee_roles(employee.id, {role.id})

        assert service.has_permission(employee.id, "EMPLOYEES.delete") is True
        assert service.has_permission(employee.id, "EMPLOYEES.create") is False


class TestBootstrapInitializeRbac:
    """bootstrap.py::_initialize_rbac — подключение RoleService к уже
    загруженным плагинам (тот же сценарий, что
    tests/test_plugins_employees.py::TestPluginDiscoveryIntegration, плюс
    вызов _initialize_rbac поверх)."""

    def test_wires_role_service_and_seeds_admin_for_existing_employees(self, engine):
        import bootstrap
        from core.kernel import get_core, reset_core
        from plugins.clients import IClientRepository
        from plugins.clients.repository import SqlAlchemyClientRepository
        from plugins.employees import CreateEmployeeCommand, IEmployeeRepository

        reset_core()
        core = get_core()
        core.initialize()
        try:
            core.register_service(IClientRepository, SqlAlchemyClientRepository(engine))
            core.register_service(IEmployeeRepository, SqlAlchemyEmployeeRepository(engine))
            core.register_module("db_access", object(), object, api=_FakeDbAccess(engine))

            loaded = core.services.plugin_manager.discover("plugins", context=core)
            assert "employees" in loaded

            employees_api = core.get_module_api("employees")
            pre_existing = employees_api.create_employee(
                CreateEmployeeCommand(full_name="Уже был", login="pre_existing_rbac")
            )
            # До подключения RBAC — заглушка (всегда True), как и раньше.
            assert employees_api.has_permission(pre_existing.id, "EMPLOYEES.delete") is True

            bootstrap._initialize_rbac(core)

            roles_api = core.get_module_api("roles")
            assert roles_api is not None

            admin = next(r for r in roles_api.list_roles() if r.name == "admin")
            assert admin.name == "admin"
            assert "EMPLOYEES.manage_roles" in admin.permission_codes
            assert "CLIENTS.delete" in admin.permission_codes

            # Существовавший до подключения RBAC сотрудник автоматически
            # получил роль admin — никто не потерял доступ.
            assert employees_api.has_permission(pre_existing.id, "EMPLOYEES.delete") is True
            assert employees_api.has_permission(pre_existing.id, "NOPE.delete") is False
        finally:
            reset_core()


class _FakeDbAccess:
    """Минимальная замена Database-фасада для _initialize_rbac(): нужен
    только .engine (core.get_db_access().engine), реальный db_access модуль
    в этом тесте не требуется — clients/employees используют собственные
    репозитории напрямую поверх engine."""

    def __init__(self, engine):
        self.engine = engine
