"""
Event Log Model for tracking all emitted events.

This model provides an audit trail of all events delivered via WebSocket/FCM,
enabling event recovery, debugging, and analytics.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID
import uuid

from .base import Base


class EventLog(Base):
    """
    Event Log for tracking delivered events.
    
    This table records all events that have been successfully delivered
    via WebSocket or FCM. It enables:
    - Event recovery for disconnected clients (/events/missed endpoint)
    - Debugging and troubleshooting
    - Analytics and monitoring
    - Audit trail of real-time communications
    
    Attributes:
        id: Primary key
        event_id: UUID of the original event (from OutboxEvent)
        event_type: Type of event
        payload: JSON payload of the event
        delivered_via: Delivery method (websocket, fcm, both)
        delivered_to: User ID who received the event
        delivered_at: When event was delivered
    """
    
    __tablename__ = "event_log"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Event identification
    event_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="UUID of the original event"
    )
    
    event_type = Column(
        String(100),
        nullable=False,
        index=True,
        comment="Type of event (e.g., 'incident.created')"
    )
    
    # Event data
    payload = Column(
        Text,
        nullable=False,
        comment="JSON payload of the event"
    )
    
    # Delivery information
    delivered_via = Column(
        String(20),
        nullable=False,
        comment="Delivery method: websocket, fcm, or both"
    )
    
    delivered_to = Column(
        Integer,
        nullable=False,
        index=True,
        comment="User ID who received the event"
    )
    
    delivered_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
        comment="When event was delivered"
    )
    
    # Indexes for efficient querying
    __table_args__ = (
        # Composite index for missed events recovery
        Index(
            'idx_event_log_user_time',
            'delivered_to',
            'delivered_at'
        ),
        # Composite index for event type analytics
        Index(
            'idx_event_log_type_time',
            'event_type',
            'delivered_at'
        ),
        # Index for event_id lookups (deduplication)
        Index(
            'idx_event_log_event_id',
            'event_id'
        ),
    )
    
    def __repr__(self) -> str:
        return (
            f"<EventLog(id={self.id}, "
            f"event_type='{self.event_type}', "
            f"delivered_to={self.delivered_to}, "
            f"delivered_via='{self.delivered_via}', "
            f"delivered_at='{self.delivered_at}')>"
        )
