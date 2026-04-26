"""
Modelo para solicitudes de cancelación mutua de incidentes ambiguos.
"""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class CancellationRequest(Base):
    """
    Solicitud de cancelación mutua para casos ambiguos.
    Requiere aceptación de ambas partes (cliente y taller).
    """

    __tablename__ = "cancellation_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'expired')",
            name="check_cancellation_status_valid"
        ),
        CheckConstraint(
            "requested_by IN ('client', 'workshop')",
            name="check_requested_by_valid"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidentes.id"), nullable=False, unique=True, index=True)
    
    # Quién solicitó la cancelación
    requested_by: Mapped[str] = mapped_column(String(20), nullable=False)  # 'client' o 'workshop'
    requested_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    
    # Motivo de la cancelación
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Estado de la solicitud
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    
    # Respuesta de la otra parte
    response_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    response_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # 24 horas
    
    # Relationships
    incident = relationship("Incidente", backref="cancellation_request")
    requested_by_user = relationship("User", foreign_keys=[requested_by_user_id])
    response_by_user = relationship("User", foreign_keys=[response_by_user_id])
