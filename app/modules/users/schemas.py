"""
Schemas for user management operations.
"""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from ...shared.schemas.base import BaseSchema


class UserBase(BaseSchema):
    """Base user schema."""
    email: EmailStr
    user_type: str
    is_active: bool = True


class UserResponse(UserBase):
    """User response schema."""
    id: int
    two_factor_enabled: bool
    created_at: datetime
    updated_at: datetime


class ClientResponse(UserResponse):
    """Client response schema."""
    direccion: str
    ci: str
    fecha_nacimiento: date


class WorkshopResponse(UserResponse):
    """Workshop response schema."""
    workshop_name: str
    owner_name: str
    latitude: float
    longitude: float
    coverage_radius_km: float


class TechnicianResponse(UserResponse):
    """Technician response schema."""
    workshop_id: int
    current_latitude: Optional[float] = None
    current_longitude: Optional[float] = None
    is_available: bool = True


class AdministratorResponse(UserResponse):
    """Administrator response schema."""
    role_level: int


class UpdateClientRequest(BaseModel):
    """Request to update client information."""
    direccion: Optional[str] = None


class UpdateWorkshopRequest(BaseModel):
    """Request to update workshop information."""
    workshop_name: Optional[str] = None
    owner_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    coverage_radius_km: Optional[float] = None


class UpdateTechnicianRequest(BaseModel):
    """Request to update technician information."""
    current_latitude: Optional[float] = None
    current_longitude: Optional[float] = None
    is_available: Optional[bool] = None


class LocationRequest(BaseModel):
    """Request for location-based queries."""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(default=10.0, gt=0, le=100)


class UserListResponse(BaseModel):
    """Response for user list operations."""
    users: list[UserResponse]
    total: int