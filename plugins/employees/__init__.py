"""Employees Plugin - учёт сотрудников без авторизации.

Второй реальный плагин (после plugins/clients) — сотрудник выбирается в
приложении вручную ("текущий сотрудник"), без пароля/логина, и используется
только для проставления created_by/updated_by на записях (заказах).

Principles:
- SRP: только логика сотрудников
- DIP: зависит от абстракций (IEmployeeRepository)
- SSOT: единый источник сущности сотрудника
"""

from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from core.base import BaseRepository, BaseService, PermissionObject
from core.plugin_system import BasePlugin, PluginMetadata, get_plugin_manager

# =============================================================================
# DOMAIN ENTITIES (SSOT)
# =============================================================================


@dataclass
class EmployeeEntity:
    """Сотрудник."""

    id: int
    full_name: str
    login: str
    phone: str | None = None
    position: str | None = None
    role: str = "all"  # не enforced нигде — задел на будущее
    is_active: bool = True
    created_by_id: int | None = None
    updated_by_id: int | None = None
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if not self.full_name or not self.full_name.strip():
            raise ValueError("Имя сотрудника не может быть пустым")
        self.full_name = self.full_name.strip()
        if not self.login or not self.login.strip():
            raise ValueError("Логин сотрудника не может быть пустым")
        self.login = self.login.strip()
        if self.phone:
            from utils.formatters import normalize_phone

            self.phone = normalize_phone(self.phone) or self.phone

    @property
    def display_label(self) -> str:
        """Формат для дропдауна выбора учётки: 'ФИО — логин'."""
        return f"{self.full_name} — {self.login}"


# =============================================================================
# COMMANDS
# =============================================================================


@dataclass
class CreateEmployeeCommand:
    """Команда создания сотрудника."""

    full_name: str
    login: str
    phone: str | None = None
    position: str | None = None


@dataclass
class UpdateEmployeeCommand:
    """Команда обновления сотрудника."""

    employee_id: int
    full_name: str | None = None
    login: str | None = None
    phone: str | None = None
    position: str | None = None
    is_active: bool | None = None


# =============================================================================
# QUERIES
# =============================================================================


@dataclass
class GetEmployeeByIdQuery:
    """Запрос сотрудника по ID."""

    employee_id: int


@dataclass
class ListEmployeesQuery:
    """Запрос списка сотрудников."""

    active_only: bool = True


# =============================================================================
# REPOSITORIES
# =============================================================================


class IEmployeeRepository(BaseRepository[EmployeeEntity]):
    """Интерфейс репозитория сотрудников.

    @abstractmethod на каждом методе — без него ABCMeta не блокирует
    инстанцирование неполной реализации (забытый override молча вернул бы
    None вместо ошибки при создании объекта), см. AUDIT_REPORT_v25.md.
    """

    @abstractmethod
    def get_by_id(self, employee_id: int) -> EmployeeEntity | None:
        """Получить сотрудника по ID."""

    @abstractmethod
    def get_by_login(self, login: str) -> EmployeeEntity | None:
        """Получить сотрудника по логину."""

    @abstractmethod
    def get_all(self, active_only: bool = True) -> list[EmployeeEntity]:
        """Получить всех сотрудников."""

    @abstractmethod
    def save(self, employee: EmployeeEntity) -> bool:
        """Сохранить сотрудника (создать или обновить)."""

    @abstractmethod
    def delete(self, employee_id: int) -> bool:
        """Удалить сотрудника (жёсткое удаление — используется редко, обычно
        деактивация через save(is_active=False))."""


# =============================================================================
# SERVICES
# =============================================================================


class EmployeeService(BaseService):
    """Сервис сотрудников.

    "Текущий сотрудник" — состояние на время работы процесса (без
    персистентности/авторизации): пока приложение открыто, пользователь
    один раз выбирает, кто он, и все создаваемые/изменяемые заказы
    помечаются его ID. Перевыбор — в любой момент через тот же диалог.
    """

    # Декларация для будущего enforcement полномочий (см. TODO_RBAC_ROADMAP.md
    # и core.base.PermissionObject) — пока ничего не проверяет.
    permission_object = PermissionObject(
        name="EMPLOYEES",
        operations=("create", "read", "update", "delete", "manage_roles"),
        table="employees",
    )

    def __init__(self, employee_repository: IEmployeeRepository):
        self._repo = employee_repository
        self._current_employee_id: int | None = None

    def suggest_login(self, full_name: str) -> str:
        """Предлагает свободный логин по ФИО (транслитерация, фамилия +
        инициалы, до 12 символов, см. plugins/employees/login_generator.py)."""
        from plugins.employees.login_generator import generate_unique_login

        return generate_unique_login(
            full_name, is_taken=lambda login: self._repo.get_by_login(login) is not None
        )

    def has_permission(self, employee_id: int | None, permission: str) -> bool:
        """Точка входа для проверки полномочий — ЗАГЛУШКА.

        Единственная существующая роль — "all" (нет реальной ролевой модели/
        авторизации), поэтому сейчас любой сотрудник (и employee_id=None —
        сотрудник не выбран) проходит любую проверку. Код, которому в
        будущем понадобится проверять права, может звать этот метод уже
        сейчас — когда появится реальная ролевая модель, поведение
        изменится только там, где прав действительно не хватает, вызывающий
        код переписывать не придётся. Полный план — TODO_RBAC_ROADMAP.md.

        Естественная реализация checker'а для core.base.PermissionAwareMixin.
        require_permission()/check_permission() — другой сервис может
        вызвать: ``self.require_permission("delete", checker=lambda op:
        employees_api.has_permission(current_employee_id, op))``.
        """
        return True

    def create_employee(self, command: CreateEmployeeCommand) -> EmployeeEntity | None:
        """Создать сотрудника. Логин должен быть уникален."""
        try:
            if self._repo.get_by_login(command.login):
                self.logger.warning(f"Логин уже занят: {command.login}")
                return None
            employee = EmployeeEntity(
                id=0,
                full_name=command.full_name,
                login=command.login,
                phone=command.phone,
                position=command.position,
                # NULL для самой первой записи ("создано системой") —
                # иначе ID того, кто был выбран текущим на момент создания.
                created_by_id=self._current_employee_id,
                updated_by_id=self._current_employee_id,
            )
            if self._repo.save(employee):
                self.logger.info(f"Сотрудник создан: {employee.full_name}")
                return employee
            return None
        except Exception as e:
            self.logger.exception(f"Ошибка создания сотрудника: {e}")
            return None

    def update_employee(self, command: UpdateEmployeeCommand) -> bool:
        """Обновить сотрудника — только если данные РЕАЛЬНО отличаются от
        текущих (BOBF-стиль change detection: просмотр — не правка). Если
        ни одно из переданных полей не отличается от того, что уже есть,
        запись не сохраняется вообще — updated_at/updated_by_id не меняются."""
        try:
            employee = self._repo.get_by_id(command.employee_id)
            if not employee:
                self.logger.warning(f"Сотрудник {command.employee_id} не найден")
                return False

            changed = False

            if command.login is not None and command.login.strip() != employee.login:
                existing = self._repo.get_by_login(command.login)
                if existing and existing.id != employee.id:
                    self.logger.warning(f"Логин уже занят: {command.login}")
                    return False
                employee.login = command.login.strip()
                changed = True
            if command.full_name is not None and command.full_name.strip() != employee.full_name:
                employee.full_name = command.full_name.strip()
                changed = True
            if command.phone is not None and command.phone != employee.phone:
                employee.phone = command.phone
                changed = True
            if command.position is not None and command.position != employee.position:
                employee.position = command.position
                changed = True
            if command.is_active is not None and command.is_active != employee.is_active:
                employee.is_active = command.is_active
                changed = True

            if not changed:
                return True

            employee.updated_by_id = self._current_employee_id
            return self._repo.save(employee)
        except Exception as e:
            self.logger.exception(f"Ошибка обновления сотрудника: {e}")
            return False

    def delete_employee(self, employee_id: int) -> bool:
        """Удалить сотрудника."""
        try:
            if self._current_employee_id == employee_id:
                self._current_employee_id = None
            return self._repo.delete(employee_id)
        except Exception as e:
            self.logger.exception(f"Ошибка удаления сотрудника: {e}")
            return False

    def get_employee(self, query: GetEmployeeByIdQuery) -> EmployeeEntity | None:
        """Получить сотрудника по ID."""
        return self.safe_execute(
            self._repo.get_by_id, query.employee_id, default=None
        )

    def list_employees(self, query: ListEmployeesQuery) -> list[EmployeeEntity]:
        """Получить список сотрудников."""
        return self.safe_execute(
            self._repo.get_all, query.active_only, default=[]
        )

    def set_current_employee(self, employee_id: int | None) -> bool:
        """Устанавливает "текущего сотрудника" (для created_by/updated_by).

        employee_id=None — сбросить выбор (записи будут сохраняться без
        привязки к сотруднику, как и раньше до этой функции).
        """
        if employee_id is None:
            self._current_employee_id = None
            return True
        employee = self._repo.get_by_id(employee_id)
        if not employee or not employee.is_active:
            self.logger.warning(
                f"Нельзя выбрать несуществующего/неактивного сотрудника {employee_id}"
            )
            return False
        self._current_employee_id = employee_id
        return True

    def get_current_employee(self) -> EmployeeEntity | None:
        """Возвращает текущего выбранного сотрудника (или None, если не выбран)."""
        if self._current_employee_id is None:
            return None
        return self._repo.get_by_id(self._current_employee_id)

    def get_current_employee_id(self) -> int | None:
        """Возвращает ID текущего сотрудника без похода в БД."""
        return self._current_employee_id


# =============================================================================
# PLUGIN IMPLEMENTATION
# =============================================================================


class EmployeesPlugin(BasePlugin):
    """Плагин учёта сотрудников.

    Доступ к сервисам через ядро (Core), а не напрямую — как и plugins/clients.
    """

    def __init__(self):
        super().__init__()
        self._service: EmployeeService | None = None
        self._repository: IEmployeeRepository | None = None

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="employees",
            version="1.0.0",
            description="Employee tracking (no auth) for created_by/updated_by",
            author="ServiceUp Team",
            dependencies=[],
            min_core_version="25.0",
            standalone=True,
        )

    def on_initialize(self, context) -> bool:
        """Инициализация плагина сотрудников через Core (context)."""
        self.logger.info("Initializing Employees Plugin")

        self._repository = context.get_service(IEmployeeRepository)
        self._service = EmployeeService(self._repository)
        context.register_module("employees", self, EmployeesPlugin, api=self._service)

        self.logger.info("Employees Plugin initialized successfully via Core")
        return True

    def shutdown(self) -> None:
        """Очистка ресурсов плагина сотрудников."""
        self.logger.info("Shutting down Employees Plugin")
        self._service = None
        self._repository = None
        super().shutdown()

    def get_api(self) -> EmployeeService | None:
        """Другие модули получают доступ к функциональности сотрудников
        только через этот API, используя core.call_module_method()."""
        return self._service

    def configure(self, config: dict) -> None:
        """Настройка плагина сотрудников."""
        self.logger.info(f"Configuring Employees Plugin: {config}")


# =============================================================================
# PLUGIN REGISTRATION
# =============================================================================


def register_plugin():
    """Регистрирует плагин Employees в менеджере плагинов."""
    plugin_manager = get_plugin_manager()
    plugin = EmployeesPlugin()
    plugin_manager.register(plugin)
    return plugin


__all__ = [
    "CreateEmployeeCommand",
    "EmployeeEntity",
    "EmployeeService",
    "EmployeesPlugin",
    "GetEmployeeByIdQuery",
    "IEmployeeRepository",
    "ListEmployeesQuery",
    "UpdateEmployeeCommand",
    "register_plugin",
]
