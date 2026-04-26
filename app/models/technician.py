from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .user import User


class Technician(User):
    """
    Técnico de taller (personal operativo).
    Asignado por el taller para atención presencial de incidentes.
    Accede desde app móvil con vista simplificada.
    
    Campos heredados de User:
    - id, first_name, last_name, email, phone
    - password_hash, user_type, is_active
    - email_verified, last_login, blocked_until, two_factor_enabled
    - created_at, updated_at
    """

    __tablename__ = "technicians"

    id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    
    # Relación con el taller
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"), nullable=False, index=True)
    
    # Ubicación en tiempo real (actualizada por GPS desde app móvil)
    current_latitude: Mapped[float | None] = mapped_column(Numeric(10, 8), nullable=True)
    current_longitude: Mapped[float | None] = mapped_column(Numeric(11, 8), nullable=True)
    location_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location_accuracy: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)  # Precisión en metros
    
    # Disponibilidad y estado laboral
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    is_on_duty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    # Estado de conexión en tiempo real
    is_online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relaciones
    workshop = relationship("Workshop", back_populates="technicians", foreign_keys=[workshop_id])
    incidentes = relationship("Incidente", back_populates="technician")
    
    # Relación muchos-a-muchos con especialidades
    especialidades = relationship(
        "TechnicianEspecialidad",
        back_populates="technician",
        cascade="all, delete-orphan"
    )
    
    # Historial de ubicaciones GPS
    location_history = relationship(
        "TechnicianLocationHistory",
        back_populates="technician",
        cascade="all, delete-orphan",
        order_by="desc(TechnicianLocationHistory.recorded_at)"
    )
    
    # Sesiones de tracking activas/históricas
    tracking_sessions = relationship(
        "TrackingSession",
        back_populates="technician",
        cascade="all, delete-orphan",
        order_by="desc(TrackingSession.started_at)"
    )

    __mapper_args__ = {
        "polymorphic_identity": "technician",
    }

