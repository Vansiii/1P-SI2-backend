import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from fastapi import HTTPException, status
from jwt import InvalidTokenError

from .config import get_settings

PBKDF2_ITERATIONS = 390_000


def hash_password(password: str) -> str:
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


def create_access_token(subject: str, email: str, role: str) -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    token_payload = {
        "sub": subject,
        "email": email,
        "role": role,
        "jti": str(uuid4()),
        "exp": expires_at,
    }
    encoded_token = jwt.encode(
        token_payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return encoded_token, expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()

    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o expirado",
        ) from exc
