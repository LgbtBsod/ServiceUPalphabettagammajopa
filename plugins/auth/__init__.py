"""Auth Plugin - Authentication and Authorization functionality.

This plugin provides security capabilities:
- User authentication (login/logout)
- Role-based access control (RBAC)
- Permission management
- Session management
- API token generation

Principles:
- SRP: Only auth-related logic
- DIP: Depends on abstractions
- Security First: Password hashing, token validation
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional, Set

from core.base import BaseService
from core.plugin_system import IPlugin, PluginMetadata, get_plugin_manager

# =============================================================================
# DOMAIN ENTITIES
# =============================================================================


class UserRole(Enum):
    """User roles for RBAC."""

    ADMIN = "admin"
    MANAGER = "manager"
    TECHNICIAN = "technician"
    RECEPTIONIST = "receptionist"
    VIEWER = "viewer"


class Permission(Enum):
    """Granular permissions."""

    # Orders
    ORDER_CREATE = "order.create"
    ORDER_READ = "order.read"
    ORDER_UPDATE = "order.update"
    ORDER_DELETE = "order.delete"

    # Clients
    CLIENT_CREATE = "client.create"
    CLIENT_READ = "client.read"
    CLIENT_UPDATE = "client.update"
    CLIENT_DELETE = "client.delete"

    # Reports
    REPORT_GENERATE = "report.generate"
    REPORT_PRINT = "report.print"

    # Settings
    SETTINGS_READ = "settings.read"
    SETTINGS_UPDATE = "settings.update"

    # Admin
    USER_MANAGE = "user.manage"
    SYSTEM_ADMIN = "system.admin"


@dataclass
class UserEntity:
    """User aggregate root."""

    id: int
    username: str
    email: str
    password_hash: str  # Never store plain text passwords
    role: UserRole
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_login: datetime | None = None
    failed_login_attempts: int = 0
    locked_until: datetime | None = None

    # Permissions (computed from role, but can be overridden)
    custom_permissions: set[Permission] = field(default_factory=set)


@dataclass
class SessionEntity:
    """User session entity."""

    session_id: str
    user_id: int
    created_at: datetime
    expires_at: datetime
    ip_address: str
    user_agent: str
    is_valid: bool = True


@dataclass
class ApiToken:
    """API token for programmatic access."""

    token: str
    user_id: int
    permissions: list[Permission]
    created_at: datetime
    expires_at: datetime | None = None
    description: str = ""


# =============================================================================
# COMMANDS
# =============================================================================


@dataclass
class LoginCommand:
    """Command to authenticate a user."""

    username: str
    password: str
    ip_address: str
    user_agent: str


@dataclass
class LogoutCommand:
    """Command to end a user session."""

    session_id: str


@dataclass
class CreateUserCommand:
    """Command to create a new user."""

    username: str
    email: str
    password: str
    role: UserRole
    custom_permissions: set[Permission] = field(default_factory=set)


@dataclass
class UpdateUserCommand:
    """Command to update user information."""

    user_id: int
    email: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    custom_permissions: set[Permission] | None = None


@dataclass
class ChangePasswordCommand:
    """Command to change user password."""

    user_id: int
    old_password: str
    new_password: str


@dataclass
class GenerateApiTokenCommand:
    """Command to generate API token."""

    user_id: int
    permissions: list[Permission]
    expires_in_days: int = 30
    description: str = ""


@dataclass
class RevokeApiTokenCommand:
    """Command to revoke API token."""

    token: str


# =============================================================================
# QUERIES
# =============================================================================


@dataclass
class GetUserByIdQuery:
    """Query to get user by ID."""

    user_id: int


@dataclass
class GetUserByUsernameQuery:
    """Query to get user by username."""

    username: str


@dataclass
class ValidateSessionQuery:
    """Query to validate a session."""

    session_id: str


@dataclass
class ValidateTokenQuery:
    """Query to validate an API token."""

    token: str


@dataclass
class CheckPermissionQuery:
    """Query to check if user has permission."""

    user_id: int
    permission: Permission


@dataclass
class GetUsersByRoleQuery:
    """Query to get users by role."""

    role: UserRole
    active_only: bool = True


# =============================================================================
# INTERFACES
# =============================================================================


class IPasswordHasher:
    """Interface for password hashing."""

    def hash(self, password: str) -> str:
        """Hash a password."""

    def verify(self, password: str, hash: str) -> bool:
        """Verify password against hash."""


class ISessionRepository:
    """Interface for session storage."""

    def create_session(self, session: SessionEntity) -> bool:
        """Create a new session."""

    def get_session(self, session_id: str) -> SessionEntity | None:
        """Get session by ID."""

    def invalidate_session(self, session_id: str) -> bool:
        """Invalidate a session (logout)."""

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count removed."""


class IUserRepository:
    """Interface for user storage."""

    def get_by_id(self, user_id: int) -> UserEntity | None:
        """Get user by ID."""

    def get_by_username(self, username: str) -> UserEntity | None:
        """Get user by username."""

    def get_by_email(self, email: str) -> UserEntity | None:
        """Get user by email."""

    def save(self, user: UserEntity) -> bool:
        """Save user (insert or update)."""

    def get_by_role(self, role: UserRole, active_only: bool = True) -> list[UserEntity]:
        """Get users by role."""

    def get_all(self, active_only: bool = True) -> list[UserEntity]:
        """Get all users."""


class ITokenManager:
    """Interface for API token management."""

    def generate_token(
        self, user_id: int, permissions: list[Permission], expires_in_days: int
    ) -> ApiToken:
        """Generate a new API token."""

    def validate_token(self, token: str) -> ApiToken | None:
        """Validate an API token."""

    def revoke_token(self, token: str) -> bool:
        """Revoke an API token."""


# =============================================================================
# SERVICES
# =============================================================================


class AuthService(BaseService):
    """Authentication service.

    Handles:
    - User login/logout
    - Session management
    - Password verification
    - Account lockout protection
    """

    def __init__(
        self,
        password_hasher: IPasswordHasher,
        session_repository: ISessionRepository,
        user_repository: IUserRepository,
    ):
        self._password_hasher = password_hasher
        self._session_repo = session_repository
        self._user_repo = user_repository
        self._max_failed_attempts = 5
        self._lockout_duration = timedelta(minutes=30)

    def login(self, command: LoginCommand) -> SessionEntity | None:
        """Authenticate user and create session."""
        try:
            self.logger.info(f"Login attempt for user: {command.username}")

            # Get user
            user = self._user_repo.get_by_username(command.username)
            if not user:
                self.logger.warning(f"User not found: {command.username}")
                return None

            # Check if account is locked
            if user.locked_until and user.locked_until > datetime.now():
                self.logger.warning(
                    f"Account locked: {command.username} until {user.locked_until}"
                )
                return None

            # Verify password
            if not self._password_hasher.verify(command.password, user.password_hash):
                self._handle_failed_login(user)
                self.logger.warning(f"Invalid password for user: {command.username}")
                return None

            # Reset failed attempts on successful login
            user.failed_login_attempts = 0
            user.locked_until = None
            user.last_login = datetime.now()
            self._user_repo.save(user)

            # Create session
            session = SessionEntity(
                session_id=self._generate_session_id(),
                user_id=user.id,
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(hours=24),
                ip_address=command.ip_address,
                user_agent=command.user_agent,
            )

            if self._session_repo.create_session(session):
                self.logger.info(f"User logged in: {command.username}")
                return session

            return None

        except Exception as e:
            self.logger.exception(f"Error during login: {e}")
            return None

    def logout(self, command: LogoutCommand) -> bool:
        """End user session."""
        try:
            success = self._session_repo.invalidate_session(command.session_id)
            if success:
                self.logger.info(f"Session ended: {command.session_id}")
            return success
        except Exception as e:
            self.logger.exception(f"Error during logout: {e}")
            return False

    def _handle_failed_login(self, user: UserEntity) -> None:
        """Handle failed login attempt."""
        user.failed_login_attempts += 1

        if user.failed_login_attempts >= self._max_failed_attempts:
            user.locked_until = datetime.now() + self._lockout_duration
            self.logger.warning(
                f"Account locked due to failed attempts: {user.username}"
            )

        self._user_repo.save(user)


class UserService(BaseService):
    """User management service.

    Handles:
    - User CRUD operations
    - Role assignment
    - Permission management
    """

    def __init__(
        self, password_hasher: IPasswordHasher, user_repository: IUserRepository
    ):
        self._password_hasher = password_hasher
        self._user_repo = user_repository

    def create_user(self, command: CreateUserCommand) -> UserEntity | None:
        """Create a new user."""
        try:
            self.logger.info(f"Creating user: {command.username}")

            # Check if username exists
            existing = self._user_repo.get_by_username(command.username)
            if existing:
                self.logger.warning(f"Username already exists: {command.username}")
                return None

            # Check if email exists
            if command.email:
                existing = self._user_repo.get_by_email(command.email)
                if existing:
                    self.logger.warning(f"Email already exists: {command.email}")
                    return None

            # Create user
            user = UserEntity(
                id=0,  # Will be assigned by repository
                username=command.username,
                email=command.email,
                password_hash=self._password_hasher.hash(command.password),
                role=command.role,
                custom_permissions=command.custom_permissions,
            )

            if self._user_repo.save(user):
                self.logger.info(f"User created: {command.username}")
                return user

            return None

        except Exception as e:
            self.logger.exception(f"Error creating user: {e}")
            return None

    def change_password(self, command: ChangePasswordCommand) -> bool:
        """Change user password."""
        try:
            user = self._user_repo.get_by_id(command.user_id)
            if not user:
                self.logger.warning(f"User not found: {command.user_id}")
                return False

            # Verify old password
            if not self._password_hasher.verify(
                command.old_password, user.password_hash
            ):
                self.logger.warning(f"Invalid old password for user: {command.user_id}")
                return False

            # Update password
            user.password_hash = self._password_hasher.hash(command.new_password)
            user.updated_at = datetime.now()

            return self._user_repo.save(user)

        except Exception as e:
            self.logger.exception(f"Error changing password: {e}")
            return False

    def has_permission(self, query: CheckPermissionQuery) -> bool:
        """Check if user has specific permission."""
        try:
            user = self._user_repo.get_by_id(query.user_id)
            if not user or not user.is_active:
                return False

            # Check custom permissions first
            if query.permission in user.custom_permissions:
                return True

            # Check role-based permissions
            role_permissions = self._get_role_permissions(user.role)
            return query.permission in role_permissions

        except Exception as e:
            self.logger.exception(f"Error checking permission: {e}")
            return False

    def _get_role_permissions(self, role: UserRole) -> set[Permission]:
        """Get permissions for a role."""
        role_permissions = {
            UserRole.ADMIN: set(Permission),
            UserRole.MANAGER: {
                Permission.ORDER_CREATE,
                Permission.ORDER_READ,
                Permission.ORDER_UPDATE,
                Permission.CLIENT_CREATE,
                Permission.CLIENT_READ,
                Permission.CLIENT_UPDATE,
                Permission.REPORT_GENERATE,
                Permission.REPORT_PRINT,
                Permission.SETTINGS_READ,
                Permission.SETTINGS_UPDATE,
            },
            UserRole.TECHNICIAN: {
                Permission.ORDER_READ,
                Permission.ORDER_UPDATE,
                Permission.CLIENT_READ,
                Permission.REPORT_GENERATE,
            },
            UserRole.RECEPTIONIST: {
                Permission.ORDER_CREATE,
                Permission.ORDER_READ,
                Permission.ORDER_UPDATE,
                Permission.CLIENT_CREATE,
                Permission.CLIENT_READ,
                Permission.REPORT_GENERATE,
                Permission.REPORT_PRINT,
            },
            UserRole.VIEWER: {
                Permission.ORDER_READ,
                Permission.CLIENT_READ,
                Permission.REPORT_GENERATE,
            },
        }
        return role_permissions.get(role, set())

    def _generate_session_id(self) -> str:
        """Generate unique session ID."""
        import secrets

        return secrets.token_urlsafe(32)


# =============================================================================
# PLUGIN IMPLEMENTATION
# =============================================================================


class AuthPlugin(IPlugin):
    """Authentication feature plugin."""

    def __init__(self):
        self._auth_service: AuthService | None = None
        self._user_service: UserService | None = None
        self._password_hasher: IPasswordHasher | None = None
        self._session_repo: ISessionRepository | None = None
        self._user_repo: IUserRepository | None = None
        self._token_manager: ITokenManager | None = None

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="auth",
            version="1.0.0",
            description="Authentication and authorization system",
            author="ServiceUp Team",
            dependencies=[],  # No dependencies - base plugin
            min_core_version="24.0",
            standalone=True,
        )

    def initialize(self) -> bool:
        """Initialize auth plugin."""
        try:
            self.logger.info("Initializing Auth Plugin")

            # TODO: Get dependencies from DI container
            # self._password_hasher = self._app.get_service(IPasswordHasher)
            # self._session_repo = self._app.get_repository(ISessionRepository)
            # self._user_repo = self._app.get_repository(IUserRepository)
            # self._auth_service = AuthService(self._password_hasher, self._session_repo, self._user_repo)
            # self._user_service = UserService(self._password_hasher, self._user_repo)

            self.logger.info("Auth Plugin initialized successfully")
            return True

        except Exception as e:
            self.logger.exception(f"Failed to initialize Auth Plugin: {e}")
            return False

    def shutdown(self) -> None:
        """Cleanup auth plugin resources."""
        self.logger.info("Shutting down Auth Plugin")
        self._auth_service = None
        self._user_service = None
        self._password_hasher = None
        self._session_repo = None
        self._user_repo = None
        self._token_manager = None

    def get_api(self) -> dict:
        """Return auth services API."""
        return {"auth": self._auth_service, "user": self._user_service}

    def configure(self, config: dict) -> None:
        """Configure auth plugin."""
        self.logger.info(f"Configuring Auth Plugin: {config}")


# =============================================================================
# PLUGIN REGISTRATION
# =============================================================================


def register_plugin():
    """Register the Auth plugin with the plugin manager."""
    plugin_manager = get_plugin_manager()
    plugin = AuthPlugin()
    plugin_manager.register(plugin)
    return plugin


__all__ = [
    "ApiToken",
    # Plugin
    "AuthPlugin",
    # Services
    "AuthService",
    "ChangePasswordCommand",
    "CheckPermissionQuery",
    "CreateUserCommand",
    "GenerateApiTokenCommand",
    # Queries
    "GetUserByIdQuery",
    "GetUserByUsernameQuery",
    "GetUsersByRoleQuery",
    # Interfaces
    "IPasswordHasher",
    "ISessionRepository",
    "ITokenManager",
    "IUserRepository",
    # Commands
    "LoginCommand",
    "LogoutCommand",
    "Permission",
    "RevokeApiTokenCommand",
    "SessionEntity",
    "UpdateUserCommand",
    # Entities
    "UserEntity",
    # Enums
    "UserRole",
    "UserService",
    "ValidateSessionQuery",
    "ValidateTokenQuery",
    "register_plugin",
]
