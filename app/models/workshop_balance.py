from sqlalchemy import Column, Integer, Numeric, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class WorkshopBalance(Base):
    """Model for workshop balance and withdrawals."""
    
    __tablename__ = "workshop_balances"

    id = Column(Integer, primary_key=True, index=True)
    workshop_id = Column(Integer, ForeignKey("workshops.id"), nullable=False, unique=True)
    
    # Balance
    available_balance = Column(Numeric(10, 2), nullable=False, default=0.00)
    pending_balance = Column(Numeric(10, 2), nullable=False, default=0.00)
    total_earned = Column(Numeric(10, 2), nullable=False, default=0.00)
    total_withdrawn = Column(Numeric(10, 2), nullable=False, default=0.00)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    workshop = relationship("Workshop", back_populates="balance")
    withdrawals = relationship("Withdrawal", back_populates="workshop_balance", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<WorkshopBalance(workshop_id={self.workshop_id}, available={self.available_balance})>"

    def to_dict(self):
        """Convert balance to dictionary."""
        return {
            "id": self.id,
            "workshop_id": self.workshop_id,
            "available_balance": float(self.available_balance),
            "pending_balance": float(self.pending_balance),
            "total_earned": float(self.total_earned),
            "total_withdrawn": float(self.total_withdrawn),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Withdrawal(Base):
    """Model for workshop withdrawal requests."""
    
    __tablename__ = "withdrawals"

    id = Column(Integer, primary_key=True, index=True)
    workshop_balance_id = Column(Integer, ForeignKey("workshop_balances.id"), nullable=False)
    workshop_id = Column(Integer, ForeignKey("workshops.id"), nullable=False)
    
    # Withdrawal details
    amount = Column(Numeric(10, 2), nullable=False)
    status = Column(
        String(50), 
        nullable=False, 
        default="pending"
    )  # pending, approved, rejected, paid
    
    # Bank details
    bank_name = Column(String(100), nullable=True)
    account_number = Column(String(50), nullable=True)
    account_holder = Column(String(100), nullable=True)
    
    # Stripe transfer
    stripe_transfer_id = Column(String(255), unique=True, nullable=True)
    
    # Metadata
    notes = Column(Text, nullable=True)
    failure_reason = Column(Text, nullable=True)
    
    # Timestamps
    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Admin processing
    admin_notes = Column(Text, nullable=True)
    processed_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships
    workshop_balance = relationship("WorkshopBalance", back_populates="withdrawals", foreign_keys=[workshop_balance_id])
    workshop = relationship("Workshop", back_populates="withdrawals", foreign_keys=[workshop_id])

    def __repr__(self):
        return f"<Withdrawal(id={self.id}, workshop_id={self.workshop_id}, amount={self.amount}, status={self.status})>"

    def to_dict(self):
        """Convert withdrawal to dictionary."""
        return {
            "id": self.id,
            "workshop_balance_id": self.workshop_balance_id,
            "workshop_id": self.workshop_id,
            "amount": float(self.amount),
            "status": self.status,
            "bank_name": self.bank_name,
            "account_number": self.account_number,
            "account_holder": self.account_holder,
            "stripe_transfer_id": self.stripe_transfer_id,
            "notes": self.notes,
            "admin_notes": self.admin_notes,
            "processed_by": self.processed_by,
            "failure_reason": self.failure_reason,
            "requested_at": self.requested_at.isoformat() if self.requested_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
