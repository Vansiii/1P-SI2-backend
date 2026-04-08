"""
Tests for exceptions module.
"""
import pytest

from app.core.exceptions import (
    AppException,
    ValidationException,
    NotFoundException,
    AuthenticationException,
    AuthorizationException,
    ConflictException,
    RateLimitException,
    BusinessLogicException,
    ExternalServiceException,
    UserNotFoundException,
    EmailAlreadyExistsException,
    InvalidCredentialsException,
    AccountLockedException,
    TokenExpiredException,
    InvalidTokenException,
    WeakPasswordException,
)


class TestAppException:
    """Test base AppException."""
    
    def test_app_exception_creation(self):
        """Test AppException creation."""
        message = "Test error message"
        code = "TEST_ERROR"
        
        exc = AppException(message, code)
        
        assert str(exc) == message
        assert exc.message == message
        assert exc.code == code
        assert exc.status_code == 500
    
    def test_app_exception_with_custom_status(self):
        """Test AppException with custom status code."""
        message = "Test error"
        code = "TEST_ERROR"
        status_code = 400
        
        exc = AppException(message, code, status_code)
        
        assert exc.status_code == status_code


class TestValidationException:
    """Test ValidationException."""
    
    def test_validation_exception_creation(self):
        """Test ValidationException creation."""
        message = "Validation failed"
        
        exc = ValidationException(message)
        
        assert str(exc) == message
        assert exc.message == message
        assert exc.code == "VALIDATION_ERROR"
        assert exc.status_code == 400


class TestNotFoundException:
    """Test NotFoundException."""
    
    def test_not_found_exception_creation(self):
        """Test NotFoundException creation."""
        resource = "User"
        
        exc = NotFoundException(resource)
        
        assert resource in str(exc)
        assert exc.code == "NOT_FOUND"
        assert exc.status_code == 404


class TestAuthenticationException:
    """Test AuthenticationException."""
    
    def test_authentication_exception_creation(self):
        """Test AuthenticationException creation."""
        message = "Authentication failed"
        
        exc = AuthenticationException(message)
        
        assert str(exc) == message
        assert exc.code == "AUTHENTICATION_ERROR"
        assert exc.status_code == 401


class TestAuthorizationException:
    """Test AuthorizationException."""
    
    def test_authorization_exception_creation(self):
        """Test AuthorizationException creation."""
        message = "Access denied"
        
        exc = AuthorizationException(message)
        
        assert str(exc) == message
        assert exc.code == "AUTHORIZATION_ERROR"
        assert exc.status_code == 403


class TestConflictException:
    """Test ConflictException."""
    
    def test_conflict_exception_creation(self):
        """Test ConflictException creation."""
        message = "Resource conflict"
        
        exc = ConflictException(message)
        
        assert str(exc) == message
        assert exc.code == "CONFLICT_ERROR"
        assert exc.status_code == 409


class TestRateLimitException:
    """Test RateLimitException."""
    
    def test_rate_limit_exception_creation(self):
        """Test RateLimitException creation."""
        message = "Rate limit exceeded"
        
        exc = RateLimitException(message)
        
        assert str(exc) == message
        assert exc.code == "RATE_LIMIT_ERROR"
        assert exc.status_code == 429


class TestBusinessLogicException:
    """Test BusinessLogicException."""
    
    def test_business_logic_exception_creation(self):
        """Test BusinessLogicException creation."""
        message = "Business rule violation"
        
        exc = BusinessLogicException(message)
        
        assert str(exc) == message
        assert exc.code == "BUSINESS_LOGIC_ERROR"
        assert exc.status_code == 422


class TestExternalServiceException:
    """Test ExternalServiceException."""
    
    def test_external_service_exception_creation(self):
        """Test ExternalServiceException creation."""
        service = "Email Service"
        
        exc = ExternalServiceException(service)
        
        assert service in str(exc)
        assert exc.code == "EXTERNAL_SERVICE_ERROR"
        assert exc.status_code == 502


class TestSpecificExceptions:
    """Test specific exception types."""
    
    def test_user_not_found_exception(self):
        """Test UserNotFoundException."""
        user_id = "123"
        
        exc = UserNotFoundException(user_id)
        
        assert user_id in str(exc)
        assert exc.code == "USER_NOT_FOUND"
        assert exc.status_code == 404
    
    def test_email_already_exists_exception(self):
        """Test EmailAlreadyExistsException."""
        email = "test@example.com"
        
        exc = EmailAlreadyExistsException(email)
        
        assert email in str(exc)
        assert exc.code == "EMAIL_ALREADY_EXISTS"
        assert exc.status_code == 409
    
    def test_invalid_credentials_exception(self):
        """Test InvalidCredentialsException."""
        exc = InvalidCredentialsException()
        
        assert "credenciales" in str(exc).lower()
        assert exc.code == "INVALID_CREDENTIALS"
        assert exc.status_code == 401
    
    def test_account_locked_exception(self):
        """Test AccountLockedException."""
        exc = AccountLockedException()
        
        assert "bloqueada" in str(exc).lower()
        assert exc.code == "ACCOUNT_LOCKED"
        assert exc.status_code == 423
    
    def test_token_expired_exception(self):
        """Test TokenExpiredException."""
        exc = TokenExpiredException()
        
        assert "expirado" in str(exc).lower()
        assert exc.code == "TOKEN_EXPIRED"
        assert exc.status_code == 401
    
    def test_invalid_token_exception(self):
        """Test InvalidTokenException."""
        exc = InvalidTokenException()
        
        assert "token" in str(exc).lower()
        assert exc.code == "INVALID_TOKEN"
        assert exc.status_code == 401
    
    def test_weak_password_exception(self):
        """Test WeakPasswordException."""
        message = "Password too weak"
        
        exc = WeakPasswordException(message)
        
        assert str(exc) == message
        assert exc.code == "WEAK_PASSWORD"
        assert exc.status_code == 400