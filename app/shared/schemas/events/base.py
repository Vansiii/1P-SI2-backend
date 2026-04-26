"""
Base event schema for all real-time events.

All events inherit from BaseEvent and include:
- Unique event_id for deduplication
- Timestamp for ordering
- Version for schema evolution
- Priority for processing order
- Optional metadata for extensibility
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventPriority(str, Enum):
    """Priority levels for event processing."""
    
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BaseEvent(BaseModel):
    """
    Base schema for all real-time events.
    
    All events must inherit from this class to ensure consistent structure,
    validation, and metadata across the system.
    
    Attributes:
        event_id: Unique identifier for deduplication (auto-generated UUID)
        event_type: Type of event (auto-set by subclass)
        timestamp: When the event was created (auto-generated)
        version: Schema version for evolution (default "1.0")
        priority: Processing priority (default MEDIUM)
        metadata: Optional additional data
    """
    
    event_id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier for event deduplication"
    )
    event_type: str = Field(
        ...,
        description="Type of event (e.g., 'incident.created')"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the event was created (UTC)"
    )
    version: str = Field(
        default="1.0",
        description="Schema version for evolution"
    )
    priority: EventPriority = Field(
        default=EventPriority.MEDIUM,
        description="Processing priority"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional additional metadata"
    )
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v),
        }
    
    def dict(self, **kwargs) -> Dict[str, Any]:
        """
        Override dict() to ensure proper serialization.
        
        Converts UUIDs to strings and datetimes to ISO format.
        """
        data = super().dict(**kwargs)
        
        # Ensure event_id is string
        if "event_id" in data and isinstance(data["event_id"], UUID):
            data["event_id"] = str(data["event_id"])
        
        # Ensure timestamp is ISO string
        if "timestamp" in data and isinstance(data["timestamp"], datetime):
            data["timestamp"] = data["timestamp"].isoformat()
        
        return data
    
    def json(self, **kwargs) -> str:
        """
        Override json() to ensure proper serialization.
        """
        return super().json(**kwargs)
