"""Assignment attempt tracking model for intelligent assignment system."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AssignmentAttempt(Base):
    """
    Registro de intentos de asignación de incidentes a talleres.
    Permite tracking del proceso de asignación y reasignación automática.
    """

    __tablename__ = "assignment_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Relaciones
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidentes.id"), nullable=False, index=True)
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"), nullable=False, index=True)
    technician_id: Mapped[Optional[int]] = mapped_column(ForeignKey("technicians.id"), nullable=True, index=True)
    
    # Scoring y estrategia
    algorithmic_score: Mapped[float] = mapped_column(Numeric(5, 3), nullable=False)  # 0.000 - 1.000
    ai_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 3), nullable=True)  # 0.000 - 1.000
    final_score: Mapped[float] = mapped_column(Numeric(5, 3), nullable=False)  # 0.000 - 1.000
    assignment_strategy: Mapped[str] = mapped_column(String(50), nullable=False)  # algorithm_only, ai_assisted, ai_override
    
    # Detalles del intento
    distance_km: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    ai_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Estado del intento
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")  # pending, accepted, rejected, timeout, cancelled
    response_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    timeout_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )