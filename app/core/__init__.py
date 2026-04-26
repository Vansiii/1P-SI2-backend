"""
Core module for centralized configuration and utilities.
"""

from .config import Settings, get_settings
from .database import (
    close_database_connection,
    create_database_tables,
    get_database_health,
    get_db_session,
    get_engine,
    get_session_factory,
    test_database_connection,
)
from .exceptions import (
    AccountLockedException,
    AppException,
    AuthenticationException,
    AuthorizationException,
    BusinessLogicException,
    ConflictException,
    EmailAlreadyExistsException,
    ExternalServiceException,
    ForbiddenException,
    InvalidCredentialsException,
    InvalidTokenException,
    NotFoundException,
    RateLimitException,
    TokenExpiredException,
    UserNotFoundException,
    ValidationException,
    WeakPasswordException,
)
from .logging import configure_logging, get_logger
from .middleware import (
    AuditMiddleware,
    ErrorHandlingMiddleware,
    LoggingMiddleware,
    RequestIDMiddleware,
)
from .responses import (
    create_error_response,
    create_paginated_response,
    create_success_response,
    get_request_id,
)
from .security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    generate_otp,
    generate_password_reset_token,
    generate_secure_token,
    hash_otp,
    hash_password,
    validate_password_strength,
    verify_otp,
    verify_password,
    verify_refresh_token_hash,
)
from .state_machine import IncidentState, IncidentStateMachine, Transition, UserRole
from .state_validators import StateValidators

__all__ = [
    # Config
    "Settings",
    "get_settings",
    # Database
    "get_engine",
    "get_session_factory",
    "get_db_session",
    "test_database_connection",
    "create_database_tables",
    "get_database_health",
    "close_database_connection",
    # Exceptions
    "AppException",
    "ValidationException",
    "NotFoundException",
    "AuthenticationException",
    "AuthorizationException",
    "ForbiddenException",
    "ConflictException",
    "RateLimitException",
    "BusinessLogicException",
    "ExternalServiceException",
    "UserNotFoundException",
    "EmailAlreadyExistsException",
    "InvalidCredentialsException",
    "AccountLockedException",
    "TokenExpiredException",
    "InvalidTokenException",
    "WeakPasswordException",
    # Logging
    "configure_logging",
    "get_logger",
    # Middleware
    "RequestIDMiddleware",
    "LoggingMiddleware",
    "ErrorHandlingMiddleware",
    "AuditMiddleware",
    # Responses
    "create_error_response",
    "create_success_response",
    "create_paginated_response",
    "get_request_id",
    # Security
    "hash_password",
    "verify_password",
    "validate_password_strength",
    "create_access_token",
    "create_refresh_token",
    "verify_refresh_token_hash",
    "decode_access_token",
    "generate_otp",
    "hash_otp",
    "verify_otp",
    "generate_password_reset_token",
    "generate_secure_token",
    # State Machine
    "IncidentState",
    "IncidentStateMachine",
    "Transition",
    "UserRole",
    "StateValidators",
]