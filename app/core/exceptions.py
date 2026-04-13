"""
Core exceptions module with custom exception hierarchy.
"""
from typing import Any


class AppException(Exception):
    """Base application exception."""
    
    def __init__(
        self,
        message: str,
        code: str,
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class ValidationException(AppException):
    """Exception for validation errors."""
    
    def __init__(
        self,
        message: str = "Datos de entrada inválidos",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=400,
            details=details,
        )


class NotFoundException(AppException):
    """Exception for resource not found errors."""
    
    def __init__(
        self,
        resource_type: str = "Recurso",
        resource_id: str | int | None = None,
    ):
        message = f"{resource_type} no encontrado"
        if resource_id:
            message += f" (ID: {resource_id})"
        
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=404,
            details={"resource_type": resource_type, "resource_id": resource_id},
        )


class AuthenticationException(AppException):
    """Exception for authentication errors."""
    
    def __init__(
        self,
        message: str = "Credenciales inválidas",
        code: str = "AUTHENTICATION_FAILED",
        details: dict[str, Any] | None = None,
        status_code: int = 401,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status_code,
            details=details,
        )


class AuthorizationException(AppException):
    """Exception for authorization errors."""
    
    def __init__(
        self,
        message: str = "No tienes permisos para realizar esta acción",
        required_permission: str | None = None,
    ):
        super().__init__(
            message=message,
            code="AUTHORIZATION_FAILED",
            status_code=403,
            details={"required_permission": required_permission},
        )


class ConflictException(AppException):
    """Exception for resource conflict errors."""
    
    def __init__(
        self,
        message: str = "El recurso ya existe",
        conflicting_field: str | None = None,
    ):
        super().__init__(
            message=message,
            code="RESOURCE_CONFLICT",
            status_code=409,
            details={"conflicting_field": conflicting_field},
        )


class RateLimitException(AppException):
    """Exception for rate limiting errors."""
    
    def __init__(
        self,
        message: str = "Demasiadas solicitudes",
        retry_after: int | None = None,
    ):
        super().__init__(
            message=message,
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details={"retry_after": retry_after},
        )


class BusinessLogicException(AppException):
    """Exception for business logic violations."""
    
    def __init__(
        self,
        message: str,
        code: str = "BUSINESS_LOGIC_ERROR",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=422,
            details=details,
        )


class ExternalServiceException(AppException):
    """Exception for external service errors."""
    
    def __init__(
        self,
        service_name: str,
        message: str = "Error en servicio externo",
        original_error: Exception | None = None,
    ):
        super().__init__(
            message=f"{message}: {service_name}",
            code="EXTERNAL_SERVICE_ERROR",
            status_code=502,
            details={
                "service_name": service_name,
                "original_error": str(original_error) if original_error else None,
            },
        )


# Specific exceptions for common use cases
class UserNotFoundException(NotFoundException):
    """Exception for user not found."""
    
    def __init__(self, user_id: str | int | None = None):
        super().__init__(resource_type="Usuario", resource_id=user_id)


class EmailAlreadyExistsException(ConflictException):
    """Exception for duplicate email."""
    
    def __init__(self, email: str):
        super().__init__(
            message=f"El email {email} ya está registrado",
            conflicting_field="email",
        )


class InvalidCredentialsException(AuthenticationException):
    """Exception for invalid login credentials."""
    
    def __init__(
        self,
        message: str = "Email o contraseña incorrectos",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            code="INVALID_CREDENTIALS",
            details=details,
        )


class AccountLockedException(AuthenticationException):
    """Exception for locked account."""
    
    def __init__(
        self,
        unlock_time: str | None = None,
        retry_after: int | None = None,
        details: dict[str, Any] | None = None,
    ):
        message = "Cuenta bloqueada temporalmente por múltiples intentos fallidos"

        payload_details = details.copy() if details else {}
        if unlock_time:
            payload_details["unlock_time"] = unlock_time
        if retry_after is not None:
            payload_details["retry_after"] = retry_after
        
        super().__init__(
            message=message,
            code="ACCOUNT_LOCKED",
            details=payload_details,
            status_code=429,
        )


class TokenExpiredException(AuthenticationException):
    """Exception for expired token."""
    
    def __init__(self, message: str = "Token expirado"):
        super().__init__(
            message=message,
            code="TOKEN_EXPIRED",
        )


class InvalidTokenException(AuthenticationException):
    """Exception for invalid token."""
    
    def __init__(self, message: str = "Token inválido"):
        super().__init__(
            message=message,
            code="INVALID_TOKEN",
        )


class WeakPasswordException(ValidationException):
    """Exception for weak password."""
    
    def __init__(self, reason: str):
        super().__init__(
            message=f"Contraseña no cumple los requisitos: {reason}",
            details={"password_requirement": reason},
        )


# Alias for backward compatibility
ForbiddenException = AuthorizationException