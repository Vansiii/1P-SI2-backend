"""
Admin Monitoring Schemas

Pydantic models for admin monitoring endpoints.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime


# ============================================================================
# System Metrics Schemas
# ============================================================================

class SystemMetrics(BaseModel):
    """System-wide metrics for admin dashboard"""
    active_incidents: int = Field(..., description="Total active incidents")
    unassigned_incidents: int = Field(..., description="Incidents without workshop")
    pending_incidents: int = Field(..., description="Incidents pending assignment")
    assigned_incidents: int = Field(..., description="Incidents assigned to workshop")
    in_progress_incidents: int = Field(..., description="Incidents in progress")
    resolved_today: int = Field(..., description="Incidents resolved today")
    available_workshops: int = Field(..., description="Workshops available")
    busy_workshops: int = Field(..., description="Workshops busy")
    offline_workshops: int = Field(..., description="Workshops offline")
    # Rating metrics (CU06)
    total_ratings: int = Field(0, description="Total service ratings")
    average_rating: float = Field(0.0, description="Average rating across all services")
    ratings_today: int = Field(0, description="Ratings submitted today")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True


# ============================================================================
# Incident Schemas
# ============================================================================

class IncidentsByStatus(BaseModel):
    """Incidents grouped by status"""
    pendiente: int = 0
    asignado: int = 0
    en_proceso: int = 0
    en_camino: int = 0
    en_sitio: int = 0
    resuelto: int = 0
    cancelado: int = 0
    sin_taller_disponible: int = 0

    class Config:
        from_attributes = True


class IncidentsResponse(BaseModel):
    """Response for incidents endpoint"""
    incidents: List[dict] = Field(..., description="List of incidents")
    total: int = Field(..., description="Total incidents count")
    by_status: IncidentsByStatus = Field(..., description="Incidents grouped by status")

    class Config:
        from_attributes = True


# ============================================================================
# Workshop Schemas
# ============================================================================

class WorkshopWithStatus(BaseModel):
    """Workshop with availability status"""
    id: int
    workshop_name: str
    is_verified: bool
    address: Optional[str] = None
    coverage_radius_km: float
    total_technicians: int
    available_technicians: int
    busy_technicians: int
    active_incidents: int
    availability_status: str = Field(..., description="available, busy, offline, out_of_service")
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkshopsByStatus(BaseModel):
    """Workshops grouped by status"""
    available: int = 0
    busy: int = 0
    offline: int = 0
    out_of_service: int = 0

    class Config:
        from_attributes = True


class WorkshopsResponse(BaseModel):
    """Response for workshops endpoint"""
    workshops: List[WorkshopWithStatus]
    total: int
    by_status: WorkshopsByStatus

    class Config:
        from_attributes = True


# ============================================================================
# Chart Data Schemas
# ============================================================================

class ChartDataPoint(BaseModel):
    """Single data point for charts"""
    name: str
    value: int

    class Config:
        from_attributes = True


class TimelineSeriesPoint(BaseModel):
    """Single series point for timeline charts"""
    name: str
    value: int

    class Config:
        from_attributes = True


class TimelineDataPoint(BaseModel):
    """Timeline data point with multiple series"""
    name: str
    series: List[TimelineSeriesPoint]

    class Config:
        from_attributes = True


class ChartData(BaseModel):
    """Chart data for admin dashboard"""
    incidents_by_status: List[ChartDataPoint]
    incidents_by_category: List[ChartDataPoint]
    incidents_by_priority: List[ChartDataPoint]
    workshops_by_status: List[ChartDataPoint]
    incidents_timeline: List[TimelineDataPoint]
    # Rating charts (CU06)
    ratings_distribution: List[ChartDataPoint] = Field(default_factory=list, description="Distribution of ratings (1-5 stars)")
    top_rated_workshops: List[ChartDataPoint] = Field(default_factory=list, description="Top 10 workshops by rating")

    class Config:
        from_attributes = True
