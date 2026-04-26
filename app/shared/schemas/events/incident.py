"""
Incident event schemas for real-time communication.

These events cover the complete incident lifecycle:
- Creation and assignment
- Status transitions
- Technician tracking
- Work completion
- Cancellation
- AI analysis
"""

from datetime import datetime
from typing import List, Optional, Literal

from pydantic import Field

from .base import BaseEvent, EventPriority


class IncidentCreatedEvent(BaseEvent):
    """Event emitted when a new incident is created."""
    
    event_type: Literal["incident.created"] = "incident.created"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    incident_id: int = Field(..., description="ID of the created incident")
    client_id: int = Field(..., description="ID of the client who created the incident")
    location: dict = Field(..., description="Incident location (lat, lng, address)")
    description: str = Field(..., description="Incident description")
    photos: List[str] = Field(default_factory=list, description="List of photo URLs")
    vehicle_id: Optional[int] = Field(None, description="Associated vehicle ID")


class IncidentPhotosUploadedEvent(BaseEvent):
    """Event emitted when photos are uploaded to an incident."""
    
    event_type: Literal["incident.photos_uploaded"] = "incident.photos_uploaded"
    priority: EventPriority = Field(default=EventPriority.MEDIUM)
    
    incident_id: int = Field(..., description="ID of the incident")
    photo_urls: List[str] = Field(..., description="List of uploaded photo URLs")
    uploaded_by: int = Field(..., description="User ID who uploaded the photos")
    uploaded_by_role: str = Field(..., description="Role of the uploader")
    uploaded_at: datetime = Field(default_factory=datetime.utcnow, description="When uploaded")


class IncidentAssignedEvent(BaseEvent):
    """Event emitted when an incident is assigned to a workshop."""
    
    event_type: Literal["incident.assigned"] = "incident.assigned"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    incident_id: int = Field(..., description="ID of the incident")
    workshop_id: int = Field(..., description="ID of the assigned workshop")
    workshop_name: str = Field(..., description="Name of the workshop")
    technician_id: Optional[int] = Field(None, description="ID of the assigned technician")
    technician_name: Optional[str] = Field(None, description="Name of the technician")
    estimated_time: Optional[int] = Field(None, description="Estimated arrival time in minutes")
    assignment_strategy: Optional[str] = Field(None, description="Strategy used for assignment")


class IncidentAssignmentAcceptedEvent(BaseEvent):
    """Event emitted when a workshop accepts an incident assignment."""
    
    event_type: Literal["incident.assignment_accepted"] = "incident.assignment_accepted"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    incident_id: int = Field(..., description="ID of the incident")
    workshop_id: int = Field(..., description="ID of the workshop")
    workshop_name: str = Field(..., description="Name of the workshop")
    technician_id: int = Field(..., description="ID of the assigned technician")
    technician_name: str = Field(..., description="Name of the technician")
    eta: Optional[int] = Field(None, description="Estimated time of arrival in minutes")
    accepted_at: datetime = Field(default_factory=datetime.utcnow, description="When accepted")


class IncidentAssignmentRejectedEvent(BaseEvent):
    """Event emitted when a workshop rejects an incident assignment."""
    
    event_type: Literal["incident.assignment_rejected"] = "incident.assignment_rejected"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    incident_id: int = Field(..., description="ID of the incident")
    workshop_id: int = Field(..., description="ID of the workshop")
    workshop_name: str = Field(..., description="Name of the workshop")
    reason: Optional[str] = Field(None, description="Reason for rejection")
    rejected_at: datetime = Field(default_factory=datetime.utcnow, description="When rejected")


class IncidentAssignmentTimeoutEvent(BaseEvent):
    """Event emitted when a workshop doesn't respond to assignment within timeout."""
    
    event_type: Literal["incident.assignment_timeout"] = "incident.assignment_timeout"
    priority: EventPriority = Field(default=EventPriority.MEDIUM)
    
    incident_id: int = Field(..., description="ID of the incident")
    workshop_id: int = Field(..., description="ID of the workshop")
    workshop_name: str = Field(..., description="Name of the workshop")
    timeout_minutes: int = Field(default=5, description="Timeout duration in minutes")
    timed_out_at: datetime = Field(default_factory=datetime.utcnow, description="When timed out")


class IncidentStatusChangedEvent(BaseEvent):
    """Event emitted when an incident's status changes."""
    
    event_type: Literal["incident.status_changed"] = "incident.status_changed"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    incident_id: int = Field(..., description="ID of the incident")
    old_status: str = Field(..., description="Previous status")
    new_status: str = Field(..., description="New status")
    changed_by: int = Field(..., description="User ID who changed the status")
    changed_by_role: str = Field(..., description="Role of the user (client, technician, admin)")
    reason: Optional[str] = Field(None, description="Reason for status change")


class IncidentTechnicianOnWayEvent(BaseEvent):
    """Event emitted when technician starts traveling to incident location."""
    
    event_type: Literal["incident.technician_on_way"] = "incident.technician_on_way"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    incident_id: int = Field(..., description="ID of the incident")
    technician_id: int = Field(..., description="ID of the technician")
    technician_name: str = Field(..., description="Name of the technician")
    current_location: dict = Field(..., description="Current location (lat, lng)")
    eta: Optional[int] = Field(None, description="Estimated time of arrival in minutes")
    distance_km: Optional[float] = Field(None, description="Distance to incident in km")


class IncidentTechnicianArrivedEvent(BaseEvent):
    """Event emitted when technician arrives at incident location."""
    
    event_type: Literal["incident.technician_arrived"] = "incident.technician_arrived"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    incident_id: int = Field(..., description="ID of the incident")
    technician_id: int = Field(..., description="ID of the technician")
    technician_name: str = Field(..., description="Name of the technician")
    arrival_time: datetime = Field(default_factory=datetime.utcnow, description="When arrived")
    location: dict = Field(..., description="Arrival location (lat, lng)")


class IncidentWorkStartedEvent(BaseEvent):
    """Event emitted when technician starts working on the incident."""
    
    event_type: Literal["incident.work_started"] = "incident.work_started"
    priority: EventPriority = Field(default=EventPriority.MEDIUM)
    
    incident_id: int = Field(..., description="ID of the incident")
    technician_id: int = Field(..., description="ID of the technician")
    technician_name: str = Field(..., description="Name of the technician")
    start_time: datetime = Field(default_factory=datetime.utcnow, description="When work started")


class IncidentWorkCompletedEvent(BaseEvent):
    """Event emitted when work on the incident is completed."""
    
    event_type: Literal["incident.work_completed"] = "incident.work_completed"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    incident_id: int = Field(..., description="ID of the incident")
    technician_id: int = Field(..., description="ID of the technician")
    technician_name: str = Field(..., description="Name of the technician")
    completion_time: datetime = Field(default_factory=datetime.utcnow, description="When completed")
    summary: Optional[str] = Field(None, description="Work summary")
    duration_minutes: Optional[int] = Field(None, description="Total work duration")


class IncidentCancelledEvent(BaseEvent):
    """Event emitted when an incident is cancelled."""
    
    event_type: Literal["incident.cancelled"] = "incident.cancelled"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    incident_id: int = Field(..., description="ID of the incident")
    cancelled_by: int = Field(..., description="User ID who cancelled")
    cancelled_by_role: str = Field(..., description="Role of the user")
    reason: Optional[str] = Field(None, description="Cancellation reason")


class IncidentUpdatedEvent(BaseEvent):
    """Event emitted when an incident is updated with new information."""
    
    event_type: Literal["incident.updated"] = "incident.updated"
    priority: EventPriority = Field(default=EventPriority.MEDIUM)
    
    incident_id: int = Field(..., description="ID of the incident")
    updated_fields: dict = Field(..., description="Dictionary of updated fields and their new values")
    cancelled_at: datetime = Field(default_factory=datetime.utcnow, description="When cancelled")


class IncidentAnalysisStartedEvent(BaseEvent):
    """Event emitted when AI analysis of an incident starts."""
    
    event_type: Literal["incident.analysis_started"] = "incident.analysis_started"
    priority: EventPriority = Field(default=EventPriority.LOW)
    
    incident_id: int = Field(..., description="ID of the incident")
    analysis_id: int = Field(..., description="ID of the analysis record")


class IncidentAnalysisCompletedEvent(BaseEvent):
    """Event emitted when AI analysis of an incident completes successfully."""
    
    event_type: Literal["incident.analysis_completed"] = "incident.analysis_completed"
    priority: EventPriority = Field(default=EventPriority.MEDIUM)
    
    incident_id: int = Field(..., description="ID of the incident")
    analysis_id: int = Field(..., description="ID of the analysis record")
    diagnosis: str = Field(..., description="AI diagnosis")
    severity: str = Field(..., description="Severity level")
    category: Optional[str] = Field(None, description="Incident category")
    priority_level: Optional[str] = Field(None, description="Priority level")
    recommendations: Optional[List[str]] = Field(None, description="Recommendations")
    confidence: Optional[float] = Field(None, description="Confidence score (0-1)")


class IncidentAnalysisFailedEvent(BaseEvent):
    """Event emitted when AI analysis of an incident fails."""
    
    event_type: Literal["incident.analysis_failed"] = "incident.analysis_failed"
    priority: EventPriority = Field(default=EventPriority.MEDIUM)
    
    incident_id: int = Field(..., description="ID of the incident")
    analysis_id: int = Field(..., description="ID of the analysis record")
    error: str = Field(..., description="Error message")
    error_type: Optional[str] = Field(None, description="Error type/category")


class IncidentAnalysisSlowEvent(BaseEvent):
    """Event emitted when AI analysis is taking longer than expected."""
    
    event_type: Literal["incident.analysis_slow"] = "incident.analysis_slow"
    priority: EventPriority = Field(default=EventPriority.LOW)
    
    incident_id: int = Field(..., description="ID of the incident")
    analysis_id: int = Field(..., description="ID of the analysis record")
    elapsed_seconds: int = Field(..., description="Seconds elapsed since analysis started")
    threshold_seconds: int = Field(..., description="Slow threshold in seconds")


class IncidentAnalysisTimeoutEvent(BaseEvent):
    """Event emitted when AI analysis times out."""
    
    event_type: Literal["incident.analysis_timeout"] = "incident.analysis_timeout"
    priority: EventPriority = Field(default=EventPriority.MEDIUM)
    
    incident_id: int = Field(..., description="ID of the incident")
    analysis_id: int = Field(..., description="ID of the analysis record")
    timeout_seconds: int = Field(..., description="Timeout threshold in seconds")
    analysis_id: int = Field(..., description="ID of the analysis record")
    timeout_seconds: int = Field(..., description="Timeout duration in seconds")


class IncidentSearchingWorkshopEvent(BaseEvent):
    """Event emitted when system starts searching for a workshop."""
    
    event_type: Literal["incident.searching_workshop"] = "incident.searching_workshop"
    priority: EventPriority = Field(default=EventPriority.MEDIUM)
    
    incident_id: int = Field(..., description="ID of the incident")
    search_attempt: int = Field(default=1, description="Number of search attempt")
    message: str = Field(default="Buscando el mejor taller disponible", description="Status message")


class IncidentNoWorkshopAvailableEvent(BaseEvent):
    """Event emitted when no workshop is available for an incident."""
    
    event_type: Literal["incident.no_workshop_available"] = "incident.no_workshop_available"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    incident_id: int = Field(..., description="ID of the incident")
    reason: str = Field(..., description="Reason why no workshop is available")
    workshops_contacted: int = Field(default=0, description="Number of workshops contacted")
    message: str = Field(default="No hay talleres disponibles en este momento", description="User-facing message")


class IncidentReassignmentStartedEvent(BaseEvent):
    """Event emitted when reassignment process starts after rejection or timeout."""
    
    event_type: Literal["incident.reassignment_started"] = "incident.reassignment_started"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    incident_id: int = Field(..., description="ID of the incident")
    previous_workshop_id: Optional[int] = Field(None, description="ID of previous workshop")
    reason: str = Field(..., description="Reason for reassignment (rejection, timeout, etc)")
    message: str = Field(default="Buscando un nuevo taller disponible", description="Status message")
