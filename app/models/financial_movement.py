from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class WorkshopFinancialMovement(Base):
    """
    Movimiento financiero del taller.
    Registra cada cambio en el saldo: ingresos por pagos, retiros, reembolsos, etc.
    """
    
    __tablename__ = "workshop_financial_movements"

    id = Column(Integer, primary_key=True, index=True)
    workshop_id = Column(Integer, ForeignKey("workshops.id"), nullable=False, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    withdrawal_id = Column(Integer, ForeignKey("withdrawals.id"), nullable=True)
    
    # Movement details
    movement_type = Column(
        String(50), nullable=False
    )  # payment_received, withdrawal_requested, withdrawal_completed, withdrawal_reversed, refund
    
    amount = Column(Numeric(10, 2), nullable=False)  # Positive = income, negative = expense
    balance_after = Column(Numeric(10, 2), nullable=False)  # Balance after this movement
    description = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    workshop = relationship("Workshop", foreign_keys=[workshop_id])
    transaction = relationship("Transaction", back_populates="financial_movement")
    withdrawal = relationship("Withdrawal")

    def __repr__(self):
        return (
            f"<WorkshopFinancialMovement(id={self.id}, workshop_id={self.workshop_id}, "
            f"type={self.movement_type}, amount={self.amount})>"
        )

    def to_dict(self):
        """Convert movement to dictionary."""
        return {
            "id": self.id,
            "workshop_id": self.workshop_id,
            "transaction_id": self.transaction_id,
            "withdrawal_id": self.withdrawal_id,
            "movement_type": self.movement_type,
            "amount": float(self.amount),
            "balance_after": float(self.balance_after),
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
