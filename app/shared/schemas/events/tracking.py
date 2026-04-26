"""Tracking event schemas for real-time location updates."""

from datetime import datetime
from typing import Optional, Literal

from pydantic import Field

from .base import BaseEvent, EventPriority


class TrackingLocationUpdatedEvent(BaseEvent):
    """Event emitted when technician's location is updated."""
    
    event_type: Literal["tracking.location_updated"] = "tracking.location_updated"
    priority: EventPriority = Field(default=EventPriority.MEDIUM)
    
    incident_id: int = Field(..., description="ID of the incident")
    technician_id: int = Field(..., description="ID of the technician")
    latitude: float = Field(..., description="Latitude coordinate")
    longitude: float = Field(..., description="Longitude coordinate")
    accuracy: Optional[float] = Field(None, description="GPS accuracy in meters")
    speed: Optional[float] = Field(None, description="Speed in km/h")
    heading: Optional[float] = Field(None, description="Heading in degrees")


class TrackingSessionStartedEvent(BaseEvent):
    """Event emitted when a tracking session starts."""
    
    event_type: Literal["tracking.session_started"] = "tracking.session_started"
    priority: EventPriority = Field(default=EventPriority.MEDIUM)
    
    incident_id: int = Field(..., description="ID of the incident")
    technician_id: int = Field(..., description="ID of the technician")
    session_id: int = Field(..., description="ID of the tracking session")
    start_time: datetime = Field(default_factory=datetime.utcnow)
    start_location: dict = Field(..., description="Starting location (lat, lng)")


class TrackingSessionEndedEvent(BaseEvent):
    """Event emitted when a tracking session ends."""
    
    event_type: Literal["tracking.session_ended"] = "tracking.session_ended"
    priority: EventPriority = Field(default=EventPriority.MEDIUM)
    
    incident_id: int = Field(..., description="ID of the incident")
    technician_id: int = Field(..., description="ID of the technician")
    session_id: int = Field(..., description="ID of the tracking session")
    end_time: datetime = Field(default_factory=datetime.utcnow)
    end_location: dict = Field(..., description="Ending location (lat, lng)")
    total_distance: Optional[float] = Field(None, description="Total distance in km")
    duration_minutes: Optional[int] = Field(None, description="Duration in minutes")


class TrackingRouteUpdatedEvent(BaseEvent):
    """Event emitted when the route to incident is updated."""
    
    event_type: Literal["tracking.route_updated"] = "tracking.route_updated"
    priority: EventPriority = Field(default=EventPriority.MEDIUM)
    
    incident_id: int = Field(..., description="ID of the incident")
    technician_id: int = Field(..., description="ID of the technician")
    eta: int = Field(..., description="Estimated time of arrival in minutes")
    distance_remaining: float = Field(..., description="Distance remaining in km")
    current_location: dict = Field(..., description="Current location (lat, lng)")
