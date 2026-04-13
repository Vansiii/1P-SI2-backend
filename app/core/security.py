"""
Core security module with enhanced password validation and token management.
"""
import base64
import hashlib
import hmac
import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from fastapi import HTTPException, status
from jwt import InvalidTokenError

from .config import get_settings

logger = logging.getLogger(__name__)

PBKDF2_ITERATIONS = 390_000

# Extended list of common passwords
COMMON_PASSWORDS = {
    "password", "12345678", "qwerty123", "abc123456", "password1", "Password1!",
    "123456789", "qwertyuiop", "1234567890", "password123", "admin", "letmein",
    "welcome", "monkey", "dragon", "master", "hello", "freedom", "whatever",
    "qazwsx", "trustno1", "jordan23", "harley", "robert", "matthew", "jordan",
    "michelle", "daniel", "andrew", "joshua", "christopher", "john", "martin",
    "jessica", "jennifer", "ashley", "amanda", "nicole", "melissa", "deborah",
    "rachel", "carolyn", "janet", "virginia", "maria", "heather", "diane",
    "julie", "joyce", "victoria", "kelly", "christina", "joan", "evelyn",
    "lauren", "judith", "megan", "cheryl", "andrea", "hannah", "jacqueline",
    "martha", "gloria", "teresa", "sara", "janice", "marie", "julia", "kathryn",
    "frances", "jean", "abigail", "alice", "judy", "ruth", "anna", "denise",
    "marilyn", "beverly", "charlotte", "marie", "diana", "helen", "rebecca",
    "sharon", "michelle", "laura", "sarah", "kimberly", "deborah", "dorothy",
    "lisa", "nancy", "karen", "betty", "helen", "sandra", "donna", "carol",
    "ruth", "sharon", "michelle", "laura", "sarah", "kimberly", "deborah",
}


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-SHA256 with secure parameters."""
    password_salt = os.urandom(16)
    password_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        password_salt,
        PBKDF2_ITERATIONS,
    )
    encoded_salt = base64.urlsafe_b64encode(password_salt).decode("utf-8")
    encoded_digest = base64.urlsafe_b64encode(password_digest).decode("utf-8")
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${encoded_salt}${encoded_digest}"


def verify_password(plain_password: str, encoded_password: str) -> bool:
    """Verify password against hash with timing attack protection."""
    try:
        algorithm, iterations, encoded_salt, encoded_digest = encoded_password.split("$", 3)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    try:
        password_salt = base64.urlsafe_b64decode(encoded_salt.encode("utf-8"))
        expected_digest = base64.urlsafe_b64decode(encoded_digest.encode("utf-8"))
        numeric_iterations = int(iterations)
    except Exception:
        return False

    computed_digest = hashlib.pbkdf2_hmac(
        "sha256",
        plain_password.encode("utf-8"),
        password_salt,
        numeric_iterations,
    )
    return hmac.compare_digest(expected_digest, computed_digest)


def validate_password_strength(password: str) -> tuple[bool, str | None]:
    """
    Validate password strength with comprehensive checks.
    Returns (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres"
    
    if len(password) > 128:
        return False, "La contraseña no puede tener más de 128 caracteres"

    if not any(c.isupper() for c in password):
        return False, "La contraseña debe contener al menos una letra mayúscula"

    if not any(c.islower() for c in password):
        return False, "La contraseña debe contener al menos una letra minúscula"

    if not any(c.isdigit() for c in password):
        return False, "La contraseña debe contener al menos un número"

    special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    if not any(c in special_chars for c in password):
        return False, "La contraseña debe contener al menos un carácter especial"

    # Check against common passwords
    if password.lower() in COMMON_PASSWORDS:
        return False, "La contraseña es demasiado común"
    
    # Check for simple patterns
    if password.lower() in ["12345678", "87654321", "abcdefgh", "qwertyui"]:
        return False, "La contraseña no puede ser una secuencia simple"
    
    # Check for repeated characters
    if len(set(password)) < 4:
        return False, "La contraseña debe tener al menos 4 caracteres diferentes"

    return True, None


def create_access_token(
    subject: str, 
    email: str, 
    user_type: str,
    additional_claims: dict[str, Any] | None = None
) -> tuple[str, datetime, str]:
    """Create JWT access token with optional additional claims.
    
    Returns:
        tuple: (encoded_token, expires_at, jti)
    """
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    jti = str(uuid4())
    
    token_payload = {
        "sub": subject,
        "email": email,
        "user_type": user_type,
        "jti": jti,
        "exp": expires_at,
        "iat": datetime.now(UTC),
        "iss": settings.app_name,
    }
    
    if additional_claims:
        token_payload.update(additional_claims)
    
    try:
        encoded_token = jwt.encode(
            token_payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        logger.debug("Access token created for user %s", email)
        return encoded_token, expires_at, jti
    except Exception as exc:
        logger.error("Failed to create access token for user %s", email, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating access token"
        ) from exc


def create_refresh_token() -> tuple[str, str]:
    """
    Create a random refresh token and return (token, hash_of_token).
    Token is sent to client, hash is stored in database.
    """
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return token, token_hash


def verify_refresh_token_hash(token: str, stored_hash: str) -> bool:
    """Verify refresh token against stored hash with timing attack protection."""
    computed_hash = hashlib.sha256(token.encode()).hexdigest()
    return hmac.compare_digest(computed_hash, stored_hash)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate JWT access token."""
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        
        # Validate required claims
        required_claims = ["sub", "email", "user_type", "jti", "exp"]
        for claim in required_claims:
            if claim not in payload:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Token missing required claim: {claim}",
                )
        
        return payload
        
    except jwt.ExpiredSignatureError as exc:
        logger.debug("Token expired for token: %s", token[:20] + "...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado",
        ) from exc
    except jwt.InvalidSignatureError as exc:
        logger.warning("Invalid token signature: %s", token[:20] + "...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token con firma inválida",
        ) from exc
    except InvalidTokenError as exc:
        logger.warning("Invalid token: %s", token[:20] + "...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        ) from exc


def generate_otp() -> str:
    """Generate a 6-digit OTP code."""
    return f"{secrets.randbelow(1000000):06d}"


def hash_otp(otp: str) -> str:
    """Generate hash of OTP code for secure storage."""
    return hashlib.sha256(otp.encode()).hexdigest()


def verify_otp(plain_otp: str, hashed_otp: str) -> bool:
    """Verify OTP code against hash with timing attack protection."""
    computed_hash = hashlib.sha256(plain_otp.encode()).hexdigest()
    return hmac.compare_digest(computed_hash, hashed_otp)


def generate_password_reset_token() -> str:
    """Generate unique token for password recovery."""
    return secrets.token_urlsafe(32)


def generate_secure_token(length: int = 32) -> str:
    """Generate cryptographically secure random token."""
    return secrets.token_urlsafe(length)


def constant_time_compare(a: str, b: str) -> bool:
    """Compare two strings in constant time to prevent timing attacks."""
    return hmac.compare_digest(a.encode(), b.encode())