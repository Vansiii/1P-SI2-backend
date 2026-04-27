from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime
from .base import Base


class StripeEventLog(Base):
    """
    Log de eventos de Stripe (webhooks).
    Garantiza idempotencia: un evento de Stripe solo se procesa una vez.
    """
    
    __tablename__ = "stripe_event_log"

    id = Column(Integer, primary_key=True, index=True)
    stripe_event_id = Column(String(255), unique=True, nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    payload = Column(Text, nullable=True)  # JSON string of the event payload
    
    # Processing status
    status = Column(
        String(50), nullable=False, default="received"
    )  # received, processed, failed, ignored
    
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return (
            f"<StripeEventLog(id={self.id}, stripe_event_id={self.stripe_event_id}, "
            f"type={self.event_type}, status={self.status})>"
        )

    def to_dict(self):
        """Convert stripe event log to dictionary."""
        return {
            "id": self.id,
            "stripe_event_id": self.stripe_event_id,
            "event_type": self.event_type,
            "status": self.status,
            "error_message": self.error_message,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
        }
