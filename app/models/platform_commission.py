from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class PlatformCommission(Base):
    """
    Registro de comisión de plataforma por cada transacción.
    Detalla cuánto se cobró al cliente, cuánto retiene la plataforma y cuánto recibe el taller.
    """
    
    __tablename__ = "platform_commissions"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False, unique=True)
    workshop_id = Column(Integer, ForeignKey("workshops.id"), nullable=False, index=True)
    
    # Financial breakdown
    total_amount = Column(Numeric(10, 2), nullable=False)       # Amount charged to client
    commission_rate = Column(Numeric(5, 4), nullable=False)      # Rate applied (e.g. 0.1000)
    commission_amount = Column(Numeric(10, 2), nullable=False)   # Platform's cut
    workshop_amount = Column(Numeric(10, 2), nullable=False)     # Workshop's cut
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    transaction = relationship("Transaction", back_populates="platform_commission")
    workshop = relationship("Workshop")

    def __repr__(self):
        return (
            f"<PlatformCommission(id={self.id}, transaction_id={self.transaction_id}, "
            f"commission={self.commission_amount})>"
        )

    def to_dict(self):
        """Convert commission to dictionary."""
        return {
            "id": self.id,
            "transaction_id": self.transaction_id,
            "workshop_id": self.workshop_id,
            "total_amount": float(self.total_amount),
            "commission_rate": float(self.commission_rate),
            "commission_amount": float(self.commission_amount),
            "workshop_amount": float(self.workshop_amount),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
