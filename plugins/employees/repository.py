"""Конкретная реализация IEmployeeRepository поверх database.sqlalchemy_models.Employee.

Резолвится через Kernel DI (см. bootstrap.initialize_kernel), использует ту
же SQLite/Postgres БД, что и остальное приложение (database/engines).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from database.sqlalchemy_models import Employee
from plugins.employees import EmployeeEntity, IEmployeeRepository

if TYPE_CHECKING:
    from database.engines.base import IDatabaseEngine


def _to_entity(employee: Employee) -> EmployeeEntity:
    return EmployeeEntity(
        id=employee.id,
        full_name=employee.full_name,
        login=employee.login,
        phone=employee.phone,
        position=employee.position,
        role=employee.role,
        is_active=employee.is_active,
        created_by_id=employee.created_by_id,
        updated_by_id=employee.updated_by_id,
        created_at=employee.created_at,
    )


class SqlAlchemyEmployeeRepository(IEmployeeRepository):
    """Репозиторий сотрудников на SQLAlchemy — реализация для plugins/employees."""

    def __init__(self, db_engine: IDatabaseEngine):
        self._engine = db_engine

    def get_by_id(self, employee_id: int) -> EmployeeEntity | None:
        with self._engine.get_session() as s:
            employee = s.get(Employee, employee_id)
            return _to_entity(employee) if employee else None

    def get_by_login(self, login: str) -> EmployeeEntity | None:
        with self._engine.get_session() as s:
            employee = s.execute(
                select(Employee).where(Employee.login == login)
            ).scalar_one_or_none()
            return _to_entity(employee) if employee else None

    def get_all(self, active_only: bool = True) -> list[EmployeeEntity]:
        with self._engine.get_session() as s:
            stmt = select(Employee).order_by(Employee.full_name)
            if active_only:
                stmt = stmt.where(Employee.is_active.is_(True))
            rows = s.execute(stmt).scalars().all()
            return [_to_entity(e) for e in rows]

    def save(self, employee: EmployeeEntity) -> bool:
        try:
            with self._engine.get_session() as s:
                row = s.get(Employee, employee.id) if employee.id else None
                if row is None:
                    row = Employee(full_name=employee.full_name, login=employee.login)
                    s.add(row)
                row.full_name = employee.full_name
                row.login = employee.login
                row.phone = employee.phone
                row.position = employee.position
                row.role = employee.role
                row.is_active = employee.is_active
                if row.created_by_id is None:
                    row.created_by_id = employee.created_by_id
                row.updated_by_id = employee.updated_by_id
                s.commit()
                employee.id = row.id
                return True
        except Exception as e:
            # Раньше глотал исключение без единой строчки лога (нарушение
            # уникальности login, обрыв БД — исчезали без следа) — не
            # соответствовало принятому в проекте logger.error/exception
            # паттерну, см. AUDIT_REPORT_v25.md.
            self.logger.exception(f"Ошибка сохранения сотрудника: {e}")
            return False

    def delete(self, employee_id: int) -> bool:
        try:
            with self._engine.get_session() as s:
                row = s.get(Employee, employee_id)
                if row is None:
                    return False
                s.delete(row)
                s.commit()
                return True
        except Exception as e:
            self.logger.exception(f"Ошибка удаления сотрудника: {e}")
            return False
