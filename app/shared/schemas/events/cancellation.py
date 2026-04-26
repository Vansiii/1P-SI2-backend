"""Cancellation event schemas for incident cancellation flow."""

from datetime import datetime
from typing import Optional, Literal

from pydantic import Field

from .base import BaseEvent, EventPriority


class CancellationRequestedEvent(BaseEvent):
    """Event emitted when a cancellation is requested."""
    
    event_type: Literal["cancellation.requested"] = "cancellation.requested"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    incident_id: int = Field(..., description="ID of the incident")
    cancellation_request_id: int = Field(..., description="ID of the cancellation request")
    requested_by: int = Field(..., description="User ID who requested cancellation")
    requested_by_role: str = Field(..., description="Role of the requester")
    reason: Optional[str] = Field(None, description="Cancellation reason")
    requested_at: datetime = Field(default_factory=datetime.utcnow)


class CancellationApprovedEvent(BaseEvent):
    """Event emitted when a cancellation is approved."""
    
    event_type: Literal["cancellation.approved"] = "cancellation.approved"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    incident_id: int = Field(..., description="ID of the incident")
    cancellation_request_id: int = Field(..., description="ID of the cancellation request")
    approved_by: int = Field(..., description="User ID who approved")
    approved_by_role: str = Field(..., description="Role of the approver")
    approved_at: datetime = Field(default_factory=datetime.utcnow)


class CancellationRejectedEvent(BaseEvent):
    """Event emitted when a cancellation is rejected."""
    
    event_type: Literal["cancellation.rejected"] = "cancellation.rejected"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    incident_id: int = Field(..., description="ID of the incident")
    cancellation_request_id: int = Field(..., description="ID of the cancellation request")
    rejected_by: int = Field(..., description="User ID who rejected")
    rejected_by_role: str = Field(..., description="Role of the rejector")
    reason: Optional[str] = Field(None, description="Rejection reason")
    rejected_at: datetime = Field(default_factory=datetime.utcnow)
