"""
Outbox Event Model for Transactional Outbox Pattern.

This model ensures that events are persisted atomically with business operations,
guaranteeing eventual consistency between database state and emitted events.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Index, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum

from .base import Base


class EventPriority(str, enum.Enum):
    """Priority levels for event processing."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    
    def __str__(self):
        """Return the value instead of the name."""
        return self.value


class OutboxEvent(Base):
    """
    Outbox Event for transactional event publishing.
    
    This table stores events that need to be published to WebSocket/FCM.
    Events are inserted in the same transaction as business operations,
    then processed asynchronously by the OutboxProcessor.
    
    Attributes:
        id: Primary key
        event_id: Unique UUID for deduplication
        event_type: Type of event (e.g., 'incident.created')
        payload: JSON payload of the event
        version: Schema version for evolution
        priority: Processing priority
        processed: Whether event has been processed
        processed_at: When event was processed
        retry_count: Number of processing attempts
        last_error: Last error message if processing failed
        created_at: When event was created
    """
    
    __tablename__ = "outbox_events"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Event identification
    event_id = Column(
        UUID(as_uuid=True),
        unique=True,
        nullable=False,
        default=uuid.uuid4,
        index=True,
        comment="Unique identifier for deduplication"
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
    
    version = Column(
        String(20),
        nullable=False,
        default="1.0",
        comment="Schema version for evolution"
    )
    
    priority = Column(
        SQLEnum(EventPriority, name="event_priority", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=EventPriority.MEDIUM,
        index=True,
        comment="Processing priority"
    )
    
    # Processing status
    processed = Column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        comment="Whether event has been processed"
    )
    
    processed_at = Column(
        DateTime,
        nullable=True,
        comment="When event was processed"
    )
    
    retry_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of processing attempts"
    )
    
    last_error = Column(
        Text,
        nullable=True,
        comment="Last error message if processing failed"
    )
    
    # Timestamps
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
        comment="When event was created"
    )
    
    # Indexes for efficient querying
    __table_args__ = (
        # Composite index for processing pending events
        Index(
            'idx_outbox_pending_priority',
            'processed',
            'priority',
            'created_at',
            postgresql_where=(processed == False)
        ),
        # Index for cleanup of old processed events
        Index(
            'idx_outbox_processed_at',
            'processed_at',
            postgresql_where=(processed == True)
        ),
        # Index for retry logic
        Index(
            'idx_outbox_retry',
            'processed',
            'retry_count',
            'created_at',
            postgresql_where=(processed == False)
        ),
    )
    
    def __repr__(self) -> str:
        return (
            f"<OutboxEvent(id={self.id}, "
            f"event_type='{self.event_type}', "
            f"priority='{self.priority}', "
            f"processed={self.processed}, "
            f"retry_count={self.retry_count})>"
        )
