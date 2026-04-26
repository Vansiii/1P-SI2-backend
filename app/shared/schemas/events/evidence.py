"""Evidence event schemas for incident evidence uploads."""

from datetime import datetime
from typing import Optional, Literal

from pydantic import Field

from .base import BaseEvent, EventPriority


class EvidenceUploadedEvent(BaseEvent):
    """Event emitted when evidence is uploaded to an incident."""
    
    event_type: Literal["evidence.uploaded"] = "evidence.uploaded"
    priority: EventPriority = Field(default=EventPriority.MEDIUM)
    
    evidence_id: int = Field(..., description="ID of the evidence")
    incident_id: int = Field(..., description="ID of the incident")
    evidence_type: str = Field(..., description="Type of evidence (TEXT, IMAGE, AUDIO, VIDEO)")
    uploaded_by: int = Field(..., description="User ID who uploaded")
    uploaded_by_role: str = Field(..., description="Role of uploader (client, technician, admin)")
    file_url: Optional[str] = Field(None, description="URL of the uploaded file")
    file_name: Optional[str] = Field(None, description="Name of the file")
    file_size: Optional[int] = Field(None, description="Size in bytes")
    description: Optional[str] = Field(None, description="Evidence description")
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class EvidenceImageUploadedEvent(BaseEvent):
    """Event emitted when an image evidence is uploaded."""
    
    event_type: Literal["evidence.image_uploaded"] = "evidence.image_uploaded"
    priority: EventPriority = Field(default=EventPriority.MEDIUM)
    
    evidence_id: int = Field(..., description="ID of the evidence")
    evidence_image_id: int = Field(..., description="ID of the evidence image")
    incident_id: int = Field(..., description="ID of the incident")
    file_url: str = Field(..., description="URL of the image")
    file_name: str = Field(..., description="Name of the image file")
    mime_type: str = Field(..., description="MIME type (e.g., image/jpeg)")
    file_size: int = Field(..., description="Size in bytes")
    uploaded_by: int = Field(..., description="User ID who uploaded")
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class EvidenceAudioUploadedEvent(BaseEvent):
    """Event emitted when an audio evidence is uploaded."""
    
    event_type: Literal["evidence.audio_uploaded"] = "evidence.audio_uploaded"
    priority: EventPriority = Field(default=EventPriority.MEDIUM)
    
    evidence_id: int = Field(..., description="ID of the evidence")
    evidence_audio_id: int = Field(..., description="ID of the evidence audio")
    incident_id: int = Field(..., description="ID of the incident")
    file_url: str = Field(..., description="URL of the audio")
    file_name: str = Field(..., description="Name of the audio file")
    mime_type: str = Field(..., description="MIME type (e.g., audio/mpeg)")
    file_size: int = Field(..., description="Size in bytes")
    duration_seconds: Optional[int] = Field(None, description="Duration in seconds")
    uploaded_by: int = Field(..., description="User ID who uploaded")
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class EvidenceDeletedEvent(BaseEvent):
    """Event emitted when evidence is deleted."""
    
    event_type: Literal["evidence.deleted"] = "evidence.deleted"
    priority: EventPriority = Field(default=EventPriority.LOW)
    
    evidence_id: int = Field(..., description="ID of the deleted evidence")
    incident_id: int = Field(..., description="ID of the incident")
    evidence_type: str = Field(..., description="Type of evidence that was deleted")
    deleted_by: int = Field(..., description="User ID who deleted")
    deleted_by_role: str = Field(..., description="Role of deleter")
    deleted_at: datetime = Field(default_factory=datetime.utcnow)
