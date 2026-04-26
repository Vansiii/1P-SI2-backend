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
    """Technician response schema with complete professional information."""
    workshop_id: int
    
    # Ubicación en tiempo real
    current_latitude: Optional[float] = None
    current_longitude: Optional[float] = None
    location_updated_at: Optional[datetime] = None
    location_accuracy: Optional[float] = None
    
    # Disponibilidad y estado
    is_available: bool = True
    is_on_duty: bool = False
    is_online: bool = False
    last_seen_at: Optional[datetime] = None
    
    # Especialidades
    especialidades: Optional[list[dict]] = None


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


class ToggleWorkshopAvailabilityRequest(BaseModel):
    """Request to toggle workshop availability."""
    is_available: bool


class VerifyWorkshopRequest(BaseModel):
    """Request to verify or un-verify a workshop."""
    is_verified: bool


class UpdateWorkshopBalanceRequest(BaseModel):
    """Request to update workshop balance fields."""
    available_balance: Optional[float] = None
    pending_balance: Optional[float] = None
    total_earned: Optional[float] = None
    total_withdrawn: Optional[float] = None


class WorkshopBalanceResponse(BaseModel):
    """Response schema for workshop balance."""
    id: int
    workshop_id: int
    available_balance: float
    pending_balance: float
    total_earned: float
    total_withdrawn: float
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class UpdateTechnicianRequest(BaseModel):
    """Request to update technician information."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    current_latitude: Optional[float] = None
    current_longitude: Optional[float] = None
    location_accuracy: Optional[float] = None
    is_available: Optional[bool] = None
    is_on_duty: Optional[bool] = None
    specialty_ids: Optional[list[int]] = None


class LocationRequest(BaseModel):
    """Request for location-based queries."""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(default=10.0, gt=0, le=100)


class UserListResponse(BaseModel):
    """Response for user list operations."""
    users: list[UserResponse]
    total: int