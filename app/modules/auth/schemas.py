"""
Authentication schemas with consolidated validation.
"""
from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from ...core.constants import UserType
from ...shared.schemas.base import BaseCreateSchema, BasePublicSchema, BaseResponseSchema
from ...shared.utils.validators import (
    normalize_email_validator,
    normalize_phone_validator,
    normalize_ci_validator,
    strip_text_validator,
)


class TokenPayload(BaseCreateSchema):
    """JWT token payload schema."""
    
    sub: str = Field(..., description="Subject (user ID)")
    email: str = Field(..., description="User email")
    user_type: str = Field(..., description="User type")
    jti: str = Field(..., description="JWT ID")
    exp: datetime = Field(..., description="Expiration time")
    iat: datetime | None = Field(None, description="Issued at")
    iss: str | None = Field(None, description="Issuer")


class BaseUserRegistrationRequest(BaseCreateSchema):
    """Base user registration schema."""
    
    email: str = Field(..., description="Email address")
    password: str = Field(..., min_length=8, max_length=128, description="Password")
    
    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: Any) -> str:
        return normalize_email_validator(cls, value)


class ClientRegistrationRequest(BaseUserRegistrationRequest):
    """Client registration request schema."""
    
    first_name: str = Field(..., max_length=60, description="First name")
    last_name: str = Field(..., max_length=60, description="Last name")
    phone: str = Field(..., max_length=20, description="Phone number")
    direccion: str = Field(..., max_length=255, description="Address")
    ci: str = Field(..., max_length=20, description="CI (Cédula de Identidad)")
    fecha_nacimiento: datetime = Field(..., description="Birth date")
    
    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def strip_names(cls, value: Any) -> str:
        return strip_text_validator(cls, value)
    
    @field_validator("phone", mode="before")
    @classmethod
    def normalize_phone(cls, value: Any) -> str:
        return normalize_phone_validator(cls, value)
    
    @field_validator("ci", mode="before")
    @classmethod
    def normalize_ci(cls, value: Any) -> str:
        return normalize_ci_validator(cls, value)
    
    @field_validator("direccion", mode="before")
    @classmethod
    def strip_direccion(cls, value: Any) -> str:
        return strip_text_validator(cls, value)


class WorkshopRegistrationRequest(BaseUserRegistrationRequest):
    """Workshop registration request schema."""
    
    first_name: str = Field(..., max_length=60, description="First name")
    last_name: str = Field(..., max_length=60, description="Last name")
    phone: str = Field(..., max_length=20, description="Phone number")
    workshop_name: str = Field(..., max_length=255, description="Workshop name")
    owner_name: str = Field(..., max_length=255, description="Owner name")
    address: str | None = Field(None, max_length=255, description="Workshop address")
    latitude: float = Field(..., ge=-90, le=90, description="Latitude")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude")
    coverage_radius_km: float = Field(
        default=10.0, 
        ge=1.0, 
        le=100.0, 
        description="Coverage radius in kilometers"
    )
    
    @field_validator("first_name", "last_name", "workshop_name", "owner_name", mode="before")
    @classmethod
    def strip_names(cls, value: Any) -> str:
        return strip_text_validator(cls, value)
    
    @field_validator("phone", mode="before")
    @classmethod
    def normalize_phone(cls, value: Any) -> str:
        return normalize_phone_validator(cls, value)
    
    @field_validator("address", mode="before")
    @classmethod
    def strip_address(cls, value: Any) -> str | None:
        if value is None:
            return value
        return strip_text_validator(cls, value)


class TechnicianRegistrationRequest(BaseUserRegistrationRequest):
    """Technician registration request schema."""
    
    first_name: str = Field(..., max_length=60, description="First name")
    last_name: str = Field(..., max_length=60, description="Last name")
    phone: str = Field(..., max_length=20, description="Phone number")
    workshop_id: int = Field(..., description="Workshop ID")
    current_latitude: float | None = Field(
        None, ge=-90, le=90, description="Current latitude"
    )
    current_longitude: float | None = Field(
        None, ge=-180, le=180, description="Current longitude"
    )
    is_available: bool = Field(default=True, description="Is available for work")
    specialty_ids: list[int] | None = Field(None, description="List of specialty IDs")
    
    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def strip_names(cls, value: Any) -> str:
        return strip_text_validator(cls, value)
    
    @field_validator("phone", mode="before")
    @classmethod
    def normalize_phone(cls, value: Any) -> str:
        return normalize_phone_validator(cls, value)


class AdministratorRegistrationRequest(BaseUserRegistrationRequest):
    """Administrator registration request schema."""
    
    first_name: str = Field(..., max_length=60, description="First name")
    last_name: str = Field(..., max_length=60, description="Last name")
    phone: str = Field(..., max_length=20, description="Phone number")
    role_level: int = Field(default=1, ge=1, le=10, description="Role level")


class LoginRequest(BaseCreateSchema):
    """Login request schema."""
    
    email: str = Field(..., description="Email address")
    password: str = Field(..., description="Password")
    
    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: Any) -> str:
        return normalize_email_validator(cls, value)


class UnifiedLoginRequest(LoginRequest):
    """Unified login request for all user types."""
    pass


class Login2FARequest(BaseCreateSchema):
    """2FA login completion request."""
    
    email: str = Field(..., description="Email address")
    otp_code: str = Field(..., min_length=6, max_length=6, description="OTP code")
    
    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: Any) -> str:
        return normalize_email_validator(cls, value)


class UpdateProfileRequest(BaseCreateSchema):
    """Update profile request schema."""
    
    # Common fields that can be updated
    first_name: str | None = Field(None, max_length=60, description="First name")
    last_name: str | None = Field(None, max_length=60, description="Last name")
    phone: str | None = Field(None, max_length=20, description="Phone number")
    direccion: str | None = Field(None, max_length=255, description="Address")
    ci: str | None = Field(None, max_length=20, description="CI (Cédula de Identidad)")
    fecha_nacimiento: datetime | None = Field(None, description="Birth date")
    workshop_name: str | None = Field(None, max_length=255, description="Workshop name")
    owner_name: str | None = Field(None, max_length=255, description="Owner name")
    latitude: float | None = Field(None, ge=-90, le=90, description="Latitude")
    longitude: float | None = Field(None, ge=-180, le=180, description="Longitude")
    coverage_radius_km: float | None = Field(
        None, ge=1.0, le=100.0, description="Coverage radius"
    )
    current_latitude: float | None = Field(None, ge=-90, le=90, description="Current latitude")
    current_longitude: float | None = Field(None, ge=-180, le=180, description="Current longitude")
    is_available: bool | None = Field(None, description="Is available")
    
    @field_validator("first_name", "last_name", "direccion", "workshop_name", "owner_name", mode="before")
    @classmethod
    def strip_text_fields(cls, value: Any) -> str | None:
        if value is None:
            return value
        return strip_text_validator(cls, value)
    
    @field_validator("phone", mode="before")
    @classmethod
    def normalize_phone(cls, value: Any) -> str | None:
        if value is None:
            return value
        return normalize_phone_validator(cls, value)
    
    @field_validator("ci", mode="before")
    @classmethod
    def normalize_ci(cls, value: Any) -> str | None:
        if value is None:
            return value
        return normalize_ci_validator(cls, value)


class DeleteAccountRequest(BaseCreateSchema):
    """Delete account request schema."""
    
    password: str = Field(..., description="Current password for confirmation")


# Response schemas
class BaseUserPublic(BasePublicSchema):
    """Base user public schema."""
    
    email: str = Field(..., description="Email address")
    user_type: str = Field(..., description="User type")
    is_active: bool = Field(..., description="Is account active")
    two_factor_enabled: bool = Field(..., description="Is 2FA enabled")


class ClientPublic(BaseUserPublic):
    """Client public schema."""
    
    first_name: str = Field(..., description="First name")
    last_name: str = Field(..., description="Last name")
    phone: str = Field(..., description="Phone number")
    direccion: str = Field(..., description="Address")
    ci: str = Field(..., description="CI")
    fecha_nacimiento: datetime = Field(..., description="Birth date")


class WorkshopPublic(BaseUserPublic):
    """Workshop public schema."""
    
    workshop_name: str = Field(..., description="Workshop name")
    owner_name: str = Field(..., description="Owner name")
    latitude: float = Field(..., description="Latitude")
    longitude: float = Field(..., description="Longitude")
    coverage_radius_km: float = Field(..., description="Coverage radius")


class TechnicianPublic(BaseUserPublic):
    """Technician public schema."""
    
    workshop_id: int = Field(..., description="Workshop ID")
    current_latitude: float | None = Field(None, description="Current latitude")
    current_longitude: float | None = Field(None, description="Current longitude")
    is_available: bool = Field(..., description="Is available")


class AdministratorPublic(BaseUserPublic):
    """Administrator public schema."""
    
    role_level: int = Field(..., description="Role level")


class TokenResponse(BaseCreateSchema):
    """Token response schema."""
    
    access_token: str = Field(..., description="Access token")
    refresh_token: str = Field(..., description="Refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration in seconds")


class ClientTokenResponse(TokenResponse):
    """Client token response with user data."""
    
    user: ClientPublic = Field(..., description="Client data")


class WorkshopTokenResponse(TokenResponse):
    """Workshop token response with user data."""
    
    user: WorkshopPublic = Field(..., description="Workshop data")


class TechnicianTokenResponse(TokenResponse):
    """Technician token response with user data."""
    
    user: TechnicianPublic = Field(..., description="Technician data")


class AdministratorTokenResponse(TokenResponse):
    """Administrator token response with user data."""
    
    user: AdministratorPublic = Field(..., description="Administrator data")


class UnifiedTokenResponse(BaseCreateSchema):
    """Unified token response for any user type."""
    
    access_token: str = Field(..., description="Access token")
    refresh_token: str = Field(..., description="Refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration in seconds")
    user_type: str = Field(..., description="User type")
    requires_2fa: bool = Field(default=False, description="Requires 2FA completion")


class UserProfileResponse(BaseCreateSchema):
    """User profile response schema."""
    
    user_type: str = Field(..., description="User type")
    data: ClientPublic | WorkshopPublic | TechnicianPublic | AdministratorPublic = Field(
        ..., description="User data"
    )


class ProfileUpdateResponse(BaseCreateSchema):
    """Profile update response schema."""
    
    message: str = Field(..., description="Success message")
    user: ClientPublic | WorkshopPublic | TechnicianPublic | AdministratorPublic = Field(
        ..., description="Updated user data"
    )


class DeleteAccountResponse(BaseCreateSchema):
    """Delete account response schema."""
    
    message: str = Field(..., description="Success message")
    deleted_at: datetime = Field(..., description="Deletion timestamp")