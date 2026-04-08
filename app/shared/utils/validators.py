"""
Shared validation utilities.
"""
import re
from typing import Any

from pydantic import field_validator


def validate_email(email: str) -> str:
    """
    Validate and normalize email address.
    
    Args:
        email: Email address to validate
        
    Returns:
        Normalized email address
        
    Raises:
        ValueError: If email format is invalid
    """
    if not email or "@" not in email:
        raise ValueError("Formato de email inválido")
    
    # Basic email regex (more permissive than RFC 5322)
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(email_pattern, email):
        raise ValueError("Formato de email inválido")
    
    return email.lower().strip()


def validate_phone_number(phone: str) -> str:
    """
    Validate and normalize phone number.
    
    Args:
        phone: Phone number to validate
        
    Returns:
        Normalized phone number
        
    Raises:
        ValueError: If phone format is invalid
    """
    if not phone:
        raise ValueError("Número de teléfono requerido")
    
    # Remove all non-digit characters
    digits_only = re.sub(r'\D', '', phone)
    
    # Check length (assuming 8-15 digits is valid range)
    if len(digits_only) < 8 or len(digits_only) > 15:
        raise ValueError("Número de teléfono debe tener entre 8 y 15 dígitos")
    
    return digits_only


def validate_ci(ci: str) -> str:
    """
    Validate Bolivian CI (Cédula de Identidad).
    
    Args:
        ci: CI to validate
        
    Returns:
        Normalized CI
        
    Raises:
        ValueError: If CI format is invalid
    """
    if not ci:
        raise ValueError("CI requerido")
    
    # Remove all non-alphanumeric characters
    ci_clean = re.sub(r'[^a-zA-Z0-9]', '', ci).upper()
    
    # Basic validation (7-10 characters, alphanumeric)
    if len(ci_clean) < 7 or len(ci_clean) > 10:
        raise ValueError("CI debe tener entre 7 y 10 caracteres")
    
    if not re.match(r'^[0-9]+[A-Z]*$', ci_clean):
        raise ValueError("Formato de CI inválido")
    
    return ci_clean


# Pydantic field validators
def normalize_email_validator(cls, value: Any) -> str:
    """Pydantic field validator for email normalization."""
    if isinstance(value, str):
        return validate_email(value)
    return value


def normalize_phone_validator(cls, value: Any) -> str:
    """Pydantic field validator for phone normalization."""
    if isinstance(value, str):
        return validate_phone_number(value)
    return value


def normalize_ci_validator(cls, value: Any) -> str:
    """Pydantic field validator for CI normalization."""
    if isinstance(value, str):
        return validate_ci(value)
    return value


def strip_text_validator(cls, value: Any) -> str:
    """Pydantic field validator for text stripping."""
    if isinstance(value, str):
        return value.strip()
    return value


# Decorator versions for use with @field_validator
def email_validator():
    """Decorator for email validation."""
    return field_validator('email', mode='before')(normalize_email_validator)


def phone_validator():
    """Decorator for phone validation."""
    return field_validator('phone', mode='before')(normalize_phone_validator)


def ci_validator():
    """Decorator for CI validation."""
    return field_validator('ci', mode='before')(normalize_ci_validator)


def text_strip_validator(*fields):
    """Decorator for text stripping validation."""
    return field_validator(*fields, mode='before')(strip_text_validator)