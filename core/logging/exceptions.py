"""
Core Exceptions Module

Centralized exception handling for the entire application.
Provides specific exception types for better error management and logging.
All exceptions inherit from BaseAppError for unified handling.
"""

from typing import Optional, Any, Dict


class BaseAppError(Exception):
    """Base exception for all application errors with logging support."""
    
    def __init__(self, message: str, code: str = "APP_ERROR", details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging/API responses."""
        return {
            "error_code": self.code,
            "message": self.message,
            "details": self.details
        }


# Core Layer Exceptions
class CoreError(BaseAppError):
    """Base exception for core layer errors."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="CORE_ERROR", details=details)


class ConfigurationError(CoreError):
    """Raised when configuration is invalid or missing."""
    def __init__(self, config_key: str, message: str):
        details = {"config_key": config_key}
        super().__init__(f"Configuration error for '{config_key}': {message}", details=details)


class AuthenticationError(CoreError):
    """Raised when authentication fails."""
    def __init__(self, user_id: Optional[str] = None, reason: str = ""):
        details = {}
        if user_id:
            details["user_id"] = user_id
        if reason:
            details["reason"] = reason
        super().__init__(f"Authentication failed: {reason}", details=details)


class PermissionError(CoreError):
    """Raised when user lacks required permissions."""
    def __init__(self, action: str, resource: str, user_id: Optional[str] = None):
        details = {"action": action, "resource": resource}
        if user_id:
            details["user_id"] = user_id
        super().__init__(f"Permission denied: {action} on {resource}", details=details)


# Domain Layer Exceptions
class DomainException(BaseAppError):
    """Base exception for domain layer errors."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="DOMAIN_ERROR", details=details)


class NotFoundError(DomainException):
    """Raised when an entity is not found."""
    def __init__(self, entity_type: str, entity_id: Any):
        details = {"entity_type": entity_type, "entity_id": entity_id}
        super().__init__(f"{entity_type} with ID {entity_id} not found", details=details)


class ValidationError(DomainException):
    """Raised when domain validation fails."""
    def __init__(self, field: str, message: str, value: Any = None):
        details = {"field": field, "invalid_value": value}
        super().__init__(f"Validation failed for {field}: {message}", details=details)


class BusinessRuleViolation(DomainException):
    """Raised when a business rule is violated."""
    def __init__(self, rule_name: str, message: str):
        details = {"rule_name": rule_name}
        super().__init__(f"Business rule '{rule_name}' violated: {message}", details=details)


# Application/Service Layer Exceptions
class ServiceError(BaseAppError):
    """Base exception for service layer errors."""
    def __init__(self, message: str, service_name: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        details = details or {}
        if service_name:
            details["service_name"] = service_name
        super().__init__(message, code="SERVICE_ERROR", details=details)


class NotificationError(ServiceError):
    """Raised when notification sending fails."""
    def __init__(self, channel: str, recipient: str, message: str, original_error: Optional[Exception] = None):
        details = {"channel": channel, "recipient": recipient}
        if original_error:
            details["original_error"] = str(original_error)
        super().__init__(f"Notification failed via {channel} to {recipient}: {message}", details=details)


class AnalyticsError(ServiceError):
    """Raised when analytics operations fail."""
    def __init__(self, operation: str, message: str, original_error: Optional[Exception] = None):
        details = {"operation": operation}
        if original_error:
            details["original_error"] = str(original_error)
        super().__init__(f"Analytics {operation} failed: {message}", details=details)


# Infrastructure Layer Exceptions
class InfrastructureError(BaseAppError):
    """Base exception for infrastructure layer errors."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="INFRASTRUCTURE_ERROR", details=details)


class DatabaseError(InfrastructureError):
    """Raised when a database operation fails."""
    def __init__(self, operation: str, message: str, original_error: Optional[Exception] = None):
        details = {"operation": operation}
        if original_error:
            details["original_error"] = str(original_error)
        super().__init__(f"Database {operation} failed: {message}", details=details)


class ExternalServiceError(InfrastructureError):
    """Raised when an external service call fails."""
    def __init__(self, service_name: str, status_code: Optional[int] = None, message: str = ""):
        details = {"service_name": service_name}
        if status_code:
            details["status_code"] = status_code
        if message:
            details["message"] = message
        super().__init__(f"External service '{service_name}' error: {message}", details=details)


class AppFileNotFoundError(InfrastructureError):
    """Raised when a file is not found."""
    def __init__(self, file_path: str, operation: Optional[str] = None):
        details = {"file_path": file_path}
        if operation:
            details["operation"] = operation
        super().__init__(f"File not found: {file_path}", details=details)


class PDFGenerationError(InfrastructureError):
    """Raised when PDF generation fails."""
    def __init__(self, template_name: str, message: str, original_error: Optional[Exception] = None):
        details = {"template_name": template_name}
        if original_error:
            details["original_error"] = str(original_error)
        super().__init__(f"PDF generation failed for '{template_name}': {message}", details=details)


# Bluetooth & Call Exceptions
class BluetoothError(InfrastructureError):
    """Base exception for Bluetooth operations."""
    pass


class BluetoothConnectionError(BluetoothError):
    """Raised when Bluetooth connection fails."""
    def __init__(self, device_name: str, message: str, original_error: Optional[Exception] = None):
        details = {"device_name": device_name}
        if original_error:
            details["original_error"] = str(original_error)
        super().__init__(f"Bluetooth connection to {device_name} failed: {message}", details=details)


class BluetoothCallError(BluetoothError):
    """Raised when Bluetooth call operations fail."""
    def __init__(self, device_name: str, operation: str, message: str, original_error: Optional[Exception] = None):
        details = {"device_name": device_name, "operation": operation}
        if original_error:
            details["original_error"] = str(original_error)
        super().__init__(f"Bluetooth call {operation} failed on {device_name}: {message}", details=details)


# Legacy aliases for backward compatibility
AppException = BaseAppError
CoreException = CoreError
NotFoundError = NotFoundError
EntityNotFoundException = NotFoundError
ApplicationException = ServiceError
ServiceUnavailableError = ServiceError
CommandExecutionError = ServiceError
QueryExecutionError = ServiceError
InfrastructureException = InfrastructureError
RepositoryError = DatabaseError
FileOperationError = AppFileNotFoundError
TemplateNotFoundError = AppFileNotFoundError
QRCodeGenerationError = PDFGenerationError
MobileConnectionError = BluetoothConnectionError
WebSocketError = ExternalServiceError
PresentationException = ServiceError
UIComponentError = ServiceError
DataBindingError = ServiceError
DIContainerError = CoreError
ServiceNotRegisteredError = CoreError


__all__ = [
    # Base
    "BaseAppError",
    "AppException",  # Legacy alias
    
    # Core
    "CoreError",
    "ConfigurationError",
    "AuthenticationError",
    "PermissionError",
    
    # Domain
    "DomainException",
    "NotFoundError",
    "EntityNotFoundException",  # Legacy alias
    "ValidationError",
    "BusinessRuleViolation",
    
    # Application/Service
    "ServiceError",
    "NotificationError",
    "AnalyticsError",
    "ApplicationException",  # Legacy alias
    "ServiceUnavailableError",  # Legacy alias
    "CommandExecutionError",  # Legacy alias
    "QueryExecutionError",  # Legacy alias
    
    # Infrastructure
    "InfrastructureError",
    "DatabaseError",
    "RepositoryError",  # Legacy alias
    "ExternalServiceError",
    "AppFileNotFoundError",
    "FileOperationError",  # Legacy alias
    "PDFGenerationError",
    "TemplateNotFoundError",  # Legacy alias
    "QRCodeGenerationError",  # Legacy alias
    
    # Bluetooth
    "BluetoothError",
    "BluetoothConnectionError",
    "BluetoothCallError",
    "MobileConnectionError",  # Legacy alias
    "WebSocketError",  # Legacy alias
    
    # Presentation (Legacy aliases)
    "PresentationException",
    "UIComponentError",
    "DataBindingError",
    
    # DI (Legacy aliases)
    "DIContainerError",
    "ServiceNotRegisteredError",
]
