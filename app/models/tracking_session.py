"""
Modelo para sesiones de tracking de técnicos.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, func, Index
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class TrackingSession(Base):
    """
    Sesión de tracking de un técnico.
    Representa un período de tiempo donde el técnico está siendo rastreado.
    """

    __tablename__ = "tracking_sessions"
    __table_args__ = (
        # Performance indexes for tracking queries
        Index(
            'idx_tracking_sessions_active',
            'is_active', 'started_at',
            postgresql_where=sa.text("is_active = true")
        ),
        Index(
            'idx_tracking_sessions_incident_started',
            'incidente_id', sa.text('started_at DESC'),
            postgresql_where=sa.text("incidente_id IS NOT NULL")
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    technician_id: Mapped[int] = mapped_column(ForeignKey("technicians.id"), nullable=False, index=True)
    incidente_id: Mapped[int | None] = mapped_column(ForeignKey("incidentes.id"), nullable=True)
    
    # Control de sesión
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    
    # Métricas
    total_distance_km: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    
    # Relaciones
    technician = relationship("Technician", back_populates="tracking_sessions")
    incidente = relationship("Incidente", back_populates="tracking_sessions")
