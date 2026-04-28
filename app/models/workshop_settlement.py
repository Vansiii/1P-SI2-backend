from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class WorkshopSettlement(Base):
    """
    Liquidación del taller por período.
    Resume los ingresos, comisiones y retiros en un rango de fechas.
    """
    
    __tablename__ = "workshop_settlements"

    id = Column(Integer, primary_key=True, index=True)
    workshop_id = Column(Integer, ForeignKey("workshops.id"), nullable=False, index=True)
    
    # Period
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    
    # Financial summary
    total_collected = Column(Numeric(10, 2), nullable=False, default=0)   # Total paid by clients
    total_commission = Column(Numeric(10, 2), nullable=False, default=0)  # Platform commission
    total_net = Column(Numeric(10, 2), nullable=False, default=0)         # Net for workshop (90%)
    total_withdrawn = Column(Numeric(10, 2), nullable=False, default=0)   # Amount withdrawn in period
    balance_at_close = Column(Numeric(10, 2), nullable=False, default=0)  # Balance at period end
    transactions_count = Column(Integer, nullable=False, default=0)
    
    # Status and metadata
    status = Column(
        String(50), nullable=False, default="generated"
    )  # generated, reviewed, finalized
    
    generated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)
    
    # Timestamps
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    workshop = relationship("Workshop", foreign_keys=[workshop_id])

    def __repr__(self):
        return (
            f"<WorkshopSettlement(id={self.id}, workshop_id={self.workshop_id}, "
            f"period={self.period_start}-{self.period_end})>"
        )

    def to_dict(self):
        """Convert settlement to dictionary."""
        return {
            "id": self.id,
            "workshop_id": self.workshop_id,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "total_collected": float(self.total_collected),
            "total_commission": float(self.total_commission),
            "total_net": float(self.total_net),
            "total_withdrawn": float(self.total_withdrawn),
            "balance_at_close": float(self.balance_at_close),
            "transactions_count": self.transactions_count,
            "status": self.status,
            "generated_by": self.generated_by,
            "notes": self.notes,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
        }
