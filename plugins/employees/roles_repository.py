"""Конкретная реализация IRoleRepository поверх database.sqlalchemy_models
(Role/Permission/RolePermission/EmployeeRole).

Резолвится через Kernel DI (см. bootstrap.initialize_kernel), использует ту
же БД, что и остальное приложение (database/engines) — тот же паттерн, что
plugins/employees/repository.py::SqlAlchemyEmployeeRepository.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from database.sqlalchemy_models import EmployeeRole, Permission, Role, RolePermission
from plugins.employees.roles import IRoleRepository, PermissionEntity, RoleEntity

if TYPE_CHECKING:
    from database.engines.base import IDatabaseEngine


class SqlAlchemyRoleRepository(IRoleRepository):
    """Репозиторий ролей/полномочий на SQLAlchemy."""

    def __init__(self, db_engine: IDatabaseEngine):
        self._engine = db_engine

    def _to_entity(self, session, role: Role) -> RoleEntity:
        codes = session.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
        ).scalars().all()
        return RoleEntity(
            id=role.id,
            name=role.name,
            description=role.description,
            permission_codes=frozenset(codes),
        )

    def get_role_by_id(self, role_id: int) -> RoleEntity | None:
        with self._engine.get_session() as s:
            role = s.get(Role, role_id)
            return self._to_entity(s, role) if role else None

    def get_role_by_name(self, name: str) -> RoleEntity | None:
        with self._engine.get_session() as s:
            role = s.execute(select(Role).where(Role.name == name)).scalar_one_or_none()
            return self._to_entity(s, role) if role else None

    def list_roles(self) -> list[RoleEntity]:
        with self._engine.get_session() as s:
            rows = s.execute(select(Role).order_by(Role.name)).scalars().all()
            return [self._to_entity(s, r) for r in rows]

    def save_role(self, role: RoleEntity) -> bool:
        try:
            with self._engine.get_session() as s:
                row = s.get(Role, role.id) if role.id else None
                if row is None:
                    row = Role(name=role.name)
                    s.add(row)
                row.name = role.name
                row.description = role.description
                s.flush()  # нужен row.id ниже для новой роли

                existing_links = s.execute(
                    select(RolePermission).where(RolePermission.role_id == row.id)
                ).scalars().all()
                existing_by_perm_id = {link.permission_id: link for link in existing_links}

                wanted_permission_ids: set[int] = set()
                for code in role.permission_codes:
                    perm = s.execute(
                        select(Permission).where(Permission.code == code)
                    ).scalar_one_or_none()
                    if perm is None:
                        # Полномочие с этим кодом ещё не создано (ensure_permission
                        # не звался) — пропускаем молча, а не падаем: UI не должен
                        # уметь назначить роли код, которого физически нет.
                        continue
                    wanted_permission_ids.add(perm.id)

                for perm_id, link in existing_by_perm_id.items():
                    if perm_id not in wanted_permission_ids:
                        s.delete(link)
                for perm_id in wanted_permission_ids - existing_by_perm_id.keys():
                    s.add(RolePermission(role_id=row.id, permission_id=perm_id))

                s.commit()
                role.id = row.id
                return True
        except Exception as e:
            self.logger.exception(f"Ошибка сохранения роли: {e}")
            return False

    def delete_role(self, role_id: int) -> bool:
        try:
            with self._engine.get_session() as s:
                row = s.get(Role, role_id)
                if row is None:
                    return False
                s.delete(row)  # CASCADE снимает role_permissions/employee_roles
                s.commit()
                return True
        except Exception as e:
            self.logger.exception(f"Ошибка удаления роли: {e}")
            return False

    def ensure_permission(self, code: str, description: str | None = None) -> PermissionEntity:
        with self._engine.get_session() as s:
            row = s.execute(
                select(Permission).where(Permission.code == code)
            ).scalar_one_or_none()
            if row is None:
                row = Permission(code=code, description=description)
                s.add(row)
                s.commit()
            return PermissionEntity(id=row.id, code=row.code, description=row.description)

    def list_permissions(self) -> list[PermissionEntity]:
        with self._engine.get_session() as s:
            rows = s.execute(select(Permission).order_by(Permission.code)).scalars().all()
            return [PermissionEntity(id=r.id, code=r.code, description=r.description) for r in rows]

    def get_employee_role_ids(self, employee_id: int) -> set[int]:
        with self._engine.get_session() as s:
            rows = s.execute(
                select(EmployeeRole.role_id).where(EmployeeRole.employee_id == employee_id)
            ).scalars().all()
            return set(rows)

    def set_employee_roles(self, employee_id: int, role_ids: set[int]) -> bool:
        try:
            with self._engine.get_session() as s:
                existing = s.execute(
                    select(EmployeeRole).where(EmployeeRole.employee_id == employee_id)
                ).scalars().all()
                existing_role_ids = {link.role_id for link in existing}
                for link in existing:
                    if link.role_id not in role_ids:
                        s.delete(link)
                for role_id in role_ids - existing_role_ids:
                    s.add(EmployeeRole(employee_id=employee_id, role_id=role_id))
                s.commit()
                return True
        except Exception as e:
            self.logger.exception(f"Ошибка назначения ролей сотруднику {employee_id}: {e}")
            return False

    def get_employee_permission_codes(self, employee_id: int) -> frozenset[str]:
        with self._engine.get_session() as s:
            codes = s.execute(
                select(Permission.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(EmployeeRole, EmployeeRole.role_id == RolePermission.role_id)
                .where(EmployeeRole.employee_id == employee_id)
                .distinct()
            ).scalars().all()
            return frozenset(codes)

    def employee_has_any_roles(self, employee_id: int) -> bool:
        with self._engine.get_session() as s:
            row = s.execute(
                select(EmployeeRole.id).where(EmployeeRole.employee_id == employee_id).limit(1)
            ).scalar_one_or_none()
            return row is not None
