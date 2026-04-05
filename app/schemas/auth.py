from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkshopRegistrationRequest(BaseModel):
    workshop_name: str = Field(min_length=3, max_length=120)
    owner_name: str = Field(min_length=3, max_length=120)
    email: str = Field(min_length=6, max_length=255)
    phone: str | None = Field(default=None, min_length=7, max_length=20)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("workshop_name", "owner_name")
    @classmethod
    def strip_text_fields(cls, value: str) -> str:
        cleaned_value = value.strip()
        if not cleaned_value:
            raise ValueError("Este campo no puede estar vacio")
        return cleaned_value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        cleaned_value = value.strip().lower()
        if "@" not in cleaned_value:
            raise ValueError("El correo electronico no es valido")
        return cleaned_value

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned_value = value.strip()
        if not cleaned_value:
            return None
        return cleaned_value


class WorkshopLoginRequest(BaseModel):
    email: str = Field(min_length=6, max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        cleaned_value = value.strip().lower()
        if "@" not in cleaned_value:
            raise ValueError("El correo electronico no es valido")
        return cleaned_value


class WorkshopPublic(BaseModel):
    id: int
    workshop_name: str
    owner_name: str
    email: str
    phone: str | None
    role: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: WorkshopPublic


class TokenPayload(BaseModel):
    sub: str
    email: str
    role: str
    jti: str
    exp: int


class LogoutResponse(BaseModel):
    message: str
