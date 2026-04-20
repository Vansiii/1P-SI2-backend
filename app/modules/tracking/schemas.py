"""
Schemas for tracking operations.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class LocationUpdate(BaseModel):
    """Schema for location update from technician."""
    latitude: float = Field(..., ge=-90, le=90, description="GPS latitude")
    longitude: float = Field(..., ge=-180, le=180, description="GPS longitude")
    accuracy: Optional[float] = Field(None, ge=0, description="GPS accuracy in meters")
    speed: Optional[float] = Field(None, ge=0, description="Speed in km/h")
    heading: Optional[float] = Field(None, ge=0, lt=360, description="Direction in degrees")
    recorded_at: Optional[datetime] = Field(None, description="When location was captured")

    @field_validator('recorded_at', mode='before')
    @classmethod
    def set_recorded_at(cls, v):
        """Set recorded_at to current time if not provided."""
        return v or datetime.utcnow()


class StartTrackingRequest(BaseModel):
    """Schema for starting a tracking session."""
    incident_id: Optional[int] = Field(None, description="Optional incident ID to track")


class StopTrackingRequest(BaseModel):
    """Schema for stopping a tracking session."""
    calculate_distance: bool = Field(True, description="Whether to calculate total distance")


class TrackingSessionResponse(BaseModel):
    """Schema for tracking session response."""
    id: int
    technician_id: int
    incident_id: Optional[int]
    started_at: datetime
    ended_at: Optional[datetime]
    is_active: bool
    total_distance_km: Optional[float]

    class Config:
        from_attributes = True


class LocationHistoryResponse(BaseModel):
    """Schema for location history response."""
    id: int
    technician_id: int
    latitude: float
    longitude: float
    accuracy: Optional[float]
    speed: Optional[float]
    heading: Optional[float]
    recorded_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class TrackingStatisticsResponse(BaseModel):
    """Schema for tracking statistics response."""
    total_sessions: int
    active_sessions: int
    completed_sessions: int
    total_distance_km: float
    average_distance_km: float
    average_duration_minutes: float


class LocationHistoryRequest(BaseModel):
    """Schema for requesting location history."""
    start_time: Optional[datetime] = Field(None, description="Start time filter")
    end_time: Optional[datetime] = Field(None, description="End time filter")
    limit: int = Field(100, ge=1, le=1000, description="Maximum number of records")
