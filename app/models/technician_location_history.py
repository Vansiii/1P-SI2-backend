"""
Modelo para historial de ubicaciones de técnicos.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, func, Index
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class TechnicianLocationHistory(Base):
    """
    Historial de ubicaciones GPS del técnico.
    Permite tracking en tiempo real y análisis de rutas.
    """

    __tablename__ = "technician_location_history"
    __table_args__ = (
        # Performance index for location tracking queries
        Index(
            'idx_tech_location_history_tech_recorded',
            'technician_id', sa.text('recorded_at DESC')
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    technician_id: Mapped[int] = mapped_column(ForeignKey("technicians.id"), nullable=False, index=True)
    
    # Coordenadas GPS
    latitude: Mapped[float] = mapped_column(Numeric(10, 8), nullable=False)
    longitude: Mapped[float] = mapped_column(Numeric(11, 8), nullable=False)
    
    # Metadata de ubicación
    accuracy: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)  # Precisión en metros
    speed: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)  # Velocidad en km/h
    heading: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)  # Dirección en grados (0-360)
    
    # Timestamps
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # Cuando se capturó
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())  # Cuando se guardó
    
    # Relaciones
    technician = relationship("Technician", back_populates="location_history")
