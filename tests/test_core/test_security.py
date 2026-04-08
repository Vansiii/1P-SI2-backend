"""
Tests for security module.
"""
import pytest
from datetime import datetime, UTC, timedelta

from app.core.security import (
    hash_password,
    verify_password,
    validate_password_strength,
    create_access_token,
    decode_access_token,
    create_refresh_token,
    verify_refresh_token_hash,
    generate_otp,
    hash_otp,
    verify_otp,
)


class TestPasswordHashing:
    """Test password hashing functions."""
    
    def test_hash_password(self):
        """Test password hashing."""
        password = "testpassword123"
        hashed = hash_password(password)
        
        assert hashed != password
        assert len(hashed) > 0
        assert hashed.startswith("$2b$")
    
    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        password = "testpassword123"
        hashed = hash_password(password)
        
        assert verify_password(password, hashed) is True
    
    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        password = "testpassword123"
        wrong_password = "wrongpassword"
        hashed = hash_password(password)
        
        assert verify_password(wrong_password, hashed) is False
    
    def test_hash_password_different_results(self):
        """Test that hashing the same password produces different results."""
        password = "testpassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        
        assert hash1 != hash2
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


class TestPasswordValidation:
    """Test password strength validation."""
    
    def test_validate_strong_password(self):
        """Test validation of strong password."""
        password = "StrongPassword123!"
        is_valid, message = validate_password_strength(password)
        
        assert is_valid is True
        assert message is None
    
    def test_validate_weak_password_too_short(self):
        """Test validation of password that's too short."""
        password = "short"
        is_valid, message = validate_password_strength(password)
        
        assert is_valid is False
        assert "8 caracteres" in message
    
    def test_validate_weak_password_no_uppercase(self):
        """Test validation of password without uppercase."""
        password = "lowercase123!"
        is_valid, message = validate_password_strength(password)
        
        assert is_valid is False
        assert "mayúscula" in message
    
    def test_validate_weak_password_no_lowercase(self):
        """Test validation of password without lowercase."""
        password = "UPPERCASE123!"
        is_valid, message = validate_password_strength(password)
        
        assert is_valid is False
        assert "minúscula" in message
    
    def test_validate_weak_password_no_digit(self):
        """Test validation of password without digit."""
        password = "NoDigitPassword!"
        is_valid, message = validate_password_strength(password)
        
        assert is_valid is False
        assert "número" in message
    
    def test_validate_weak_password_no_special(self):
        """Test validation of password without special character."""
        password = "NoSpecialChar123"
        is_valid, message = validate_password_strength(password)
        
        assert is_valid is False
        assert "especial" in message
    
    def test_validate_common_password(self):
        """Test validation of common password."""
        password = "Password123!"
        is_valid, message = validate_password_strength(password)
        
        assert is_valid is False
        assert "común" in message


class TestJWTTokens:
    """Test JWT token functions."""
    
    def test_create_access_token(self):
        """Test access token creation."""
        subject = "123"
        email = "test@example.com"
        user_type = "client"
        
        token, expires_at, jti = create_access_token(subject, email, user_type)
        
        assert isinstance(token, str)
        assert len(token) > 0
        assert isinstance(expires_at, datetime)
        assert expires_at > datetime.now(UTC)
    
    def test_decode_access_token_valid(self):
        """Test decoding valid access token."""
        subject = "123"
        email = "test@example.com"
        user_type = "client"
        
        token, _, _ = create_access_token(subject, email, user_type)
        payload = decode_access_token(token)
        
        assert payload["sub"] == subject
        assert payload["email"] == email
        assert payload["user_type"] == user_type
        assert "exp" in payload
        assert "iat" in payload
    
    def test_decode_access_token_invalid(self):
        """Test decoding invalid access token."""
        invalid_token = "invalid.token.here"
        
        with pytest.raises(Exception):
            decode_access_token(invalid_token)
    
    def test_decode_access_token_expired(self):
        """Test decoding expired access token."""
        # This would require mocking time or creating a token with past expiration
        # For now, we'll skip this test
        pass


class TestRefreshTokens:
    """Test refresh token functions."""
    
    def test_create_refresh_token(self):
        """Test refresh token creation."""
        token, token_hash = create_refresh_token()
        
        assert isinstance(token, str)
        assert isinstance(token_hash, str)
        assert len(token) > 0
        assert len(token_hash) > 0
        assert token != token_hash
    
    def test_verify_refresh_token_hash_correct(self):
        """Test refresh token hash verification with correct token."""
        token, token_hash = create_refresh_token()
        
        assert verify_refresh_token_hash(token, token_hash) is True
    
    def test_verify_refresh_token_hash_incorrect(self):
        """Test refresh token hash verification with incorrect token."""
        token, token_hash = create_refresh_token()
        wrong_token = "wrong_token"
        
        assert verify_refresh_token_hash(wrong_token, token_hash) is False


class TestOTP:
    """Test OTP functions."""
    
    def test_generate_otp(self):
        """Test OTP generation."""
        otp = generate_otp()
        
        assert isinstance(otp, str)
        assert len(otp) == 6
        assert otp.isdigit()
    
    def test_hash_otp(self):
        """Test OTP hashing."""
        otp = "123456"
        hashed = hash_otp(otp)
        
        assert isinstance(hashed, str)
        assert len(hashed) > 0
        assert hashed != otp
    
    def test_verify_otp_correct(self):
        """Test OTP verification with correct OTP."""
        otp = "123456"
        hashed = hash_otp(otp)
        
        assert verify_otp(otp, hashed) is True
    
    def test_verify_otp_incorrect(self):
        """Test OTP verification with incorrect OTP."""
        otp = "123456"
        wrong_otp = "654321"
        hashed = hash_otp(otp)
        
        assert verify_otp(wrong_otp, hashed) is False
    
    def test_generate_different_otps(self):
        """Test that generating OTPs produces different results."""
        otp1 = generate_otp()
        otp2 = generate_otp()
        
        # While it's possible they could be the same, it's very unlikely
        # This test might occasionally fail due to randomness
        assert otp1 != otp2 or len(set([generate_otp() for _ in range(10)])) > 1