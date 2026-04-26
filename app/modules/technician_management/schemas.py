"""
Schemas for technician management.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class UpdateAvailabilityRequest(BaseModel):
    """Schema for updating technician availability."""
    is_available: bool = Field(..., description="Availability status")


class TechnicianWorkloadResponse(BaseModel):
    """Schema for technician workload response."""
    technician_id: int
    is_available: bool
    is_online: bool
    active_incidents: int
    active_tracking_sessions: int
    has_active_work: bool


class TechnicianStatisticsResponse(BaseModel):
    """Schema for technician statistics."""
    technician_id: int
    total_incidents: int
    resolved_incidents: int
    cancelled_incidents: int
    active_incidents: int
    resolution_rate: float


class AssignSpecialtyRequest(BaseModel):
    """Schema for assigning specialty to technician."""
    specialty_id: int = Field(..., description="ID of the specialty to assign")


class RemoveSpecialtyRequest(BaseModel):
    """Schema for removing specialty from technician."""
    specialty_id: int = Field(..., description="ID of the specialty to remove")
