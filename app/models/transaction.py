from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class Transaction(Base):
    """Model for payment transactions."""
    
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidentes.id"), nullable=False)
    workshop_id = Column(Integer, ForeignKey("workshops.id"), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    
    # Amounts
    amount = Column(Numeric(10, 2), nullable=False)  # Total amount
    commission = Column(Numeric(10, 2), nullable=False)  # Platform commission (10%)
    workshop_amount = Column(Numeric(10, 2), nullable=False)  # Amount for workshop
    
    # Payment details
    status = Column(
        String(50), 
        nullable=False, 
        default="pending"
    )  # pending, processing, completed, failed, refunded
    payment_method = Column(String(50), nullable=False)  # card, cash, transfer
    
    # Stripe integration
    stripe_payment_intent_id = Column(String(255), unique=True, nullable=True)
    stripe_charge_id = Column(String(255), unique=True, nullable=True)
    stripe_customer_id = Column(String(255), nullable=True)
    
    # Metadata
    description = Column(Text, nullable=True)
    failure_reason = Column(Text, nullable=True)
    refund_reason = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    refunded_at = Column(DateTime, nullable=True)

    # Relationships
    incident = relationship("Incidente", back_populates="transactions")
    workshop = relationship("Workshop", back_populates="transactions")
    client = relationship("Client", back_populates="transactions")

    def __repr__(self):
        return f"<Transaction(id={self.id}, incident_id={self.incident_id}, amount={self.amount}, status={self.status})>"

    def to_dict(self):
        """Convert transaction to dictionary."""
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "workshop_id": self.workshop_id,
            "client_id": self.client_id,
            "amount": float(self.amount),
            "commission": float(self.commission),
            "workshop_amount": float(self.workshop_amount),
            "status": self.status,
            "payment_method": self.payment_method,
            "stripe_payment_intent_id": self.stripe_payment_intent_id,
            "stripe_charge_id": self.stripe_charge_id,
            "description": self.description,
            "failure_reason": self.failure_reason,
            "refund_reason": self.refund_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "refunded_at": self.refunded_at.isoformat() if self.refunded_at else None,
        }
