"""Ролевая модель (roles/permissions) — см. TODO_RBAC_ROADMAP.md.

Второй "слой" плагина employees (после базового учёта сотрудников в
plugins/employees/__init__.py): роль — именованный набор полномочий,
сотрудник может иметь >1 роли (many-to-many). EmployeeService.has_permission()
делегирует сюда, когда RoleService подключён (см. bootstrap.py) — до этого
момента (role_service=None) поведение не меняется (всегда True), см.
plugins/employees/__init__.py::EmployeeService.has_permission().

Principles:
- SRP: только роли/полномочия, ничего не знает о заказах/клиентах
- DIP: зависит от абстракции (IRoleRepository)
- SSOT: единый источник кодов полномочий — core.base.PermissionObject,
  уже объявленный сервисами (ClientService.permission_object и т.д.)
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field

from core.base import BaseRepository, BaseService

# =============================================================================
# DOMAIN ENTITIES (SSOT)
# =============================================================================


@dataclass
class PermissionEntity:
    """Полномочие — код вида "<PermissionObject.name>.<операция>"."""

    id: int
    code: str
    description: str | None = None


@dataclass
class RoleEntity:
    """Роль — имя + набор кодов полномочий (не объекты PermissionEntity —
    коды достаточно для has_permission(), не тянуть лишние данные)."""

    id: int
    name: str
    description: str | None = None
    permission_codes: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self):
        if not self.name or not self.name.strip():
            raise ValueError("Имя роли не может быть пустым")
        self.name = self.name.strip()
        if not isinstance(self.permission_codes, frozenset):
            self.permission_codes = frozenset(self.permission_codes)


# =============================================================================
# COMMANDS
# =============================================================================


@dataclass
class CreateRoleCommand:
    """Команда создания роли."""

    name: str
    description: str | None = None
    permission_codes: frozenset[str] = field(default_factory=frozenset)


@dataclass
class UpdateRoleCommand:
    """Команда обновления роли (permission_codes=None — не трогать набор,
    permission_codes=frozenset() — явно очистить)."""

    role_id: int
    name: str | None = None
    description: str | None = None
    permission_codes: frozenset[str] | None = None


# =============================================================================
# REPOSITORIES
# =============================================================================


class IRoleRepository(BaseRepository[RoleEntity]):
    """Интерфейс репозитория ролей/полномочий/назначений сотрудник<->роль."""

    @abstractmethod
    def get_role_by_id(self, role_id: int) -> RoleEntity | None:
        """Получить роль по ID (с уже подтянутым набором permission_codes)."""

    @abstractmethod
    def get_role_by_name(self, name: str) -> RoleEntity | None:
        """Получить роль по имени."""

    @abstractmethod
    def list_roles(self) -> list[RoleEntity]:
        """Получить все роли."""

    @abstractmethod
    def save_role(self, role: RoleEntity) -> bool:
        """Сохранить роль (создать/обновить имя+описание+полный набор
        permission_codes — набор заменяется целиком, не сливается)."""

    @abstractmethod
    def delete_role(self, role_id: int) -> bool:
        """Удалить роль (заодно снимает её со всех сотрудников — CASCADE)."""

    @abstractmethod
    def ensure_permission(self, code: str, description: str | None = None) -> PermissionEntity:
        """Идемпотентно создать полномочие с данным кодом, если его ещё нет
        (используется сидом при старте — см. seed_default_rbac)."""

    @abstractmethod
    def list_permissions(self) -> list[PermissionEntity]:
        """Получить все известные полномочия (для UI управления ролями)."""

    @abstractmethod
    def get_employee_role_ids(self, employee_id: int) -> set[int]:
        """ID ролей, назначенных сотруднику."""

    @abstractmethod
    def set_employee_roles(self, employee_id: int, role_ids: set[int]) -> bool:
        """Заменить набор ролей сотрудника целиком (не слияние)."""

    @abstractmethod
    def get_employee_permission_codes(self, employee_id: int) -> frozenset[str]:
        """Объединение permission_codes всех ролей сотрудника (дедуплицировано)."""

    @abstractmethod
    def employee_has_any_roles(self, employee_id: int) -> bool:
        """True, если сотруднику уже назначена хотя бы одна роль — используется
        миграцией по умолчанию, чтобы не переназначать роли повторно при
        каждом старте (см. RoleService.seed_default_rbac)."""


# =============================================================================
# SERVICES
# =============================================================================


class RoleService(BaseService):
    """Сервис ролей/полномочий — CRUD ролей, назначение сотрудникам, и
    разовый сид дефолтных ролей + миграция существующих сотрудников."""

    def __init__(self, role_repository: IRoleRepository):
        self._repo = role_repository

    def list_roles(self) -> list[RoleEntity]:
        return self.safe_execute(self._repo.list_roles, default=[])

    def get_role(self, role_id: int) -> RoleEntity | None:
        return self.safe_execute(self._repo.get_role_by_id, role_id, default=None)

    def list_permissions(self) -> list[PermissionEntity]:
        return self.safe_execute(self._repo.list_permissions, default=[])

    def create_role(self, command: CreateRoleCommand) -> RoleEntity | None:
        try:
            if self._repo.get_role_by_name(command.name):
                self.logger.warning(f"Роль уже существует: {command.name}")
                return None
            role = RoleEntity(
                id=0,
                name=command.name,
                description=command.description,
                permission_codes=command.permission_codes,
            )
            if self._repo.save_role(role):
                self.logger.info(f"Роль создана: {role.name}")
                return role
            return None
        except Exception as e:
            self.logger.exception(f"Ошибка создания роли: {e}")
            return None

    def update_role(self, command: UpdateRoleCommand) -> bool:
        try:
            role = self._repo.get_role_by_id(command.role_id)
            if not role:
                self.logger.warning(f"Роль {command.role_id} не найдена")
                return False
            if command.name is not None and command.name.strip() != role.name:
                existing = self._repo.get_role_by_name(command.name)
                if existing and existing.id != role.id:
                    self.logger.warning(f"Роль уже существует: {command.name}")
                    return False
                role.name = command.name.strip()
            if command.description is not None:
                role.description = command.description
            if command.permission_codes is not None:
                role.permission_codes = frozenset(command.permission_codes)
            return self._repo.save_role(role)
        except Exception as e:
            self.logger.exception(f"Ошибка обновления роли: {e}")
            return False

    def delete_role(self, role_id: int) -> bool:
        return self.safe_execute(self._repo.delete_role, role_id, default=False)

    def get_employee_roles(self, employee_id: int) -> list[RoleEntity]:
        role_ids = self.safe_execute(
            self._repo.get_employee_role_ids, employee_id, default=set()
        )
        return [r for r in self.list_roles() if r.id in role_ids]

    def set_employee_roles(self, employee_id: int, role_ids: set[int]) -> bool:
        return self.safe_execute(
            self._repo.set_employee_roles, employee_id, role_ids, default=False
        )

    def get_employee_permission_codes(self, employee_id: int) -> frozenset[str]:
        return self.safe_execute(
            self._repo.get_employee_permission_codes, employee_id, default=frozenset()
        )

    def has_permission(self, employee_id: int, permission_code: str) -> bool:
        """Реальная проверка (не заглушка) — используется
        EmployeeService.has_permission() как естественный checker."""
        return permission_code in self.get_employee_permission_codes(employee_id)

    def seed_default_rbac(
        self, declared_permission_objects: list, all_employee_ids: list[int]
    ) -> None:
        """Разовый (идемпотентный) сид: гарантирует существование полномочий
        для каждой уже объявленной PermissionObject, создаёт роль "admin" со
        ВСЕМИ известными полномочиями, и переносит в неё сотрудников, у
        которых ЕЩЁ нет ни одной назначенной роли — чтобы включение реальной
        ролевой модели не отняло доступ ни у кого молча (см.
        TODO_RBAC_ROADMAP.md, шаг 1 плана внедрения).

        Безопасно вызывать при КАЖДОМ старте приложения: уже созданные
        полномочия/роль не дублируются (ensure_permission/get_role_by_name),
        а сотрудники с уже назначенными ролями (в т.ч. переназначенными
        вручную на что-то ДРУГОЕ, чем "admin") — пропускаются.
        """
        all_codes: set[str] = set()
        for po in declared_permission_objects:
            for op in po.operations:
                code = f"{po.name}.{op}"
                self._repo.ensure_permission(code, description=f"{po.name}: {op}")
                all_codes.add(code)

        admin_role = self._repo.get_role_by_name("admin")
        if admin_role is None:
            admin_role = RoleEntity(id=0, name="admin", description="Полный доступ")
            admin_role.permission_codes = frozenset(all_codes)
            self._repo.save_role(admin_role)
            admin_role = self._repo.get_role_by_name("admin")
        elif not all_codes.issubset(admin_role.permission_codes):
            # Новые PermissionObject появились после первого сида — "admin"
            # должен оставаться ролью с ПОЛНЫМ доступом, а не застывшим
            # снимком на момент первого запуска.
            admin_role.permission_codes = admin_role.permission_codes | all_codes
            self._repo.save_role(admin_role)

        if admin_role is None:
            return
        for employee_id in all_employee_ids:
            if not self._repo.employee_has_any_roles(employee_id):
                self._repo.set_employee_roles(employee_id, {admin_role.id})


__all__ = [
    "CreateRoleCommand",
    "IRoleRepository",
    "PermissionEntity",
    "RoleEntity",
    "RoleService",
    "UpdateRoleCommand",
]
