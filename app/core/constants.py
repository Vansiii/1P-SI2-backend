"""
Core constants module for centralized application constants.
"""

# HTTP Status Codes
class StatusCode:
    """HTTP status codes."""
    OK = 200
    CREATED = 201
    NO_CONTENT = 204
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    UNPROCESSABLE_ENTITY = 422
    TOO_MANY_REQUESTS = 429
    INTERNAL_SERVER_ERROR = 500


# Error Codes
class ErrorCode:
    """Application error codes."""
    # Authentication
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_TOKEN = "INVALID_TOKEN"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    
    # Authorization
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"
    ACCESS_DENIED = "ACCESS_DENIED"
    
    # Validation
    VALIDATION_ERROR = "VALIDATION_ERROR"
    WEAK_PASSWORD = "WEAK_PASSWORD"
    INVALID_EMAIL_FORMAT = "INVALID_EMAIL_FORMAT"
    
    # Resources
    USER_NOT_FOUND = "USER_NOT_FOUND"
    EMAIL_ALREADY_EXISTS = "EMAIL_ALREADY_EXISTS"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    RESOURCE_CONFLICT = "RESOURCE_CONFLICT"
    
    # Rate Limiting
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    
    # External Services
    EMAIL_SERVICE_ERROR = "EMAIL_SERVICE_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    
    # Business Logic
    BUSINESS_LOGIC_ERROR = "BUSINESS_LOGIC_ERROR"
    INVALID_OPERATION = "INVALID_OPERATION"


# Error Messages
class ErrorMessage:
    """Standardized error messages."""
    # Authentication
    INVALID_CREDENTIALS = "Email o contraseña incorrectos"
    TOKEN_EXPIRED = "Token expirado"
    INVALID_TOKEN = "Token inválido"
    ACCOUNT_LOCKED = "Cuenta bloqueada por múltiples intentos fallidos"
    
    # Authorization
    INSUFFICIENT_PERMISSIONS = "No tienes permisos para realizar esta acción"
    ACCESS_DENIED = "Acceso denegado"
    
    # Validation
    VALIDATION_ERROR = "Datos de entrada inválidos"
    WEAK_PASSWORD = "La contraseña no cumple los requisitos de seguridad"
    INVALID_EMAIL_FORMAT = "Formato de email inválido"
    
    # Resources
    USER_NOT_FOUND = "Usuario no encontrado"
    EMAIL_ALREADY_EXISTS = "El email ya está registrado"
    RESOURCE_NOT_FOUND = "Recurso no encontrado"
    RESOURCE_CONFLICT = "El recurso ya existe"
    
    # Rate Limiting
    RATE_LIMIT_EXCEEDED = "Demasiadas solicitudes. Intenta más tarde"
    
    # External Services
    EMAIL_SERVICE_ERROR = "Error al enviar email"
    DATABASE_ERROR = "Error de base de datos"
    
    # Business Logic
    BUSINESS_LOGIC_ERROR = "Error en lógica de negocio"
    INVALID_OPERATION = "Operación no válida"
    
    # Generic
    INTERNAL_SERVER_ERROR = "Error interno del servidor"


# User Types
class UserType:
    """User type constants."""
    CLIENT = "client"
    WORKSHOP = "workshop"
    TECHNICIAN = "technician"
    ADMINISTRATOR = "administrator"
    
    @classmethod
    def all(cls) -> list[str]:
        """Get all user types."""
        return [cls.CLIENT, cls.WORKSHOP, cls.TECHNICIAN, cls.ADMINISTRATOR]


# Audit Actions
class AuditAction:
    """Audit action constants."""
    # Authentication
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    REGISTER = "register"
    
    # Password
    PASSWORD_CHANGE = "password_change"
    PASSWORD_RESET_REQUEST = "password_reset_request"
    PASSWORD_RESET = "password_reset"
    
    # 2FA
    TWO_FA_ENABLED = "2fa_enabled"
    TWO_FA_DISABLED = "2fa_disabled"
    TWO_FA_VERIFIED = "2fa_verified"
    
    # CRUD Operations
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    
    # Failed Operations
    CREATE_FAILED = "create_failed"
    READ_FAILED = "read_failed"
    UPDATE_FAILED = "update_failed"
    DELETE_FAILED = "delete_failed"


# Resource Types
class ResourceType:
    """Resource type constants for audit."""
    USER = "user"
    CLIENT = "client"
    WORKSHOP = "workshop"
    TECHNICIAN = "technician"
    ADMINISTRATOR = "administrator"
    VEHICLE = "vehicle"
    INCIDENT = "incident"
    SERVICE = "service"
    EVIDENCE = "evidence"


# Email Templates
class EmailTemplate:
    """Email template constants."""
    WELCOME = "welcome"
    PASSWORD_RESET = "password_reset"
    PASSWORD_CHANGED = "password_changed"
    OTP = "otp"
    SECURITY_NOTIFICATION = "security_notification"
    ACCOUNT_UNLOCKED = "account_unlocked"


# Cache Keys
class CacheKey:
    """Cache key patterns."""
    USER_BY_ID = "user:id:{user_id}"
    USER_BY_EMAIL = "user:email:{email}"
    REVOKED_TOKEN = "revoked_token:{jti}"
    RATE_LIMIT = "rate_limit:{key}"
    OTP = "otp:{user_id}"


# Rate Limit Keys
class RateLimitKey:
    """Rate limit key patterns."""
    LOGIN = "login:{ip}"
    REGISTER = "register:{ip}"
    PASSWORD_RESET = "password_reset:{ip}"
    OTP_REQUEST = "otp_request:{user_id}"
    TOKEN_REFRESH = "token_refresh:{user_id}"


# Pagination
class Pagination:
    """Pagination constants."""
    DEFAULT_PAGE = 1
    DEFAULT_SIZE = 20
    MAX_SIZE = 100


# Security
class Security:
    """Security-related constants."""
    # Password requirements
    MIN_PASSWORD_LENGTH = 8
    MAX_PASSWORD_LENGTH = 128
    
    # Token expiration (in minutes)
    DEFAULT_ACCESS_TOKEN_EXPIRE = 30
    DEFAULT_REFRESH_TOKEN_EXPIRE_DAYS = 7
    DEFAULT_PASSWORD_RESET_EXPIRE = 60
    DEFAULT_OTP_EXPIRE = 5
    
    # Login attempts
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_DURATION_MINUTES = 5
    
    # Rate limiting (requests per time period)
    RATE_LIMIT_LOGIN = "5/minute"
    RATE_LIMIT_REGISTER = "3/hour"
    RATE_LIMIT_PASSWORD_RESET = "5/hour"
    RATE_LIMIT_OTP = "10/hour"


# Environment
class Environment:
    """Environment constants."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


# Log Levels
class LogLevel:
    """Logging level constants."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"