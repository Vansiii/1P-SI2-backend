from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .user import User


class Workshop(User):
    """
    Taller mecánico que atiende emergencias vehiculares.
    El usuario (first_name, last_name, email, phone) representa al responsable/dueño del taller.
    Accede desde la aplicación web para gestionar solicitudes.
    """

    __tablename__ = "workshops"
    __table_args__ = (
        CheckConstraint("coverage_radius_km >= 0", name="check_coverage_radius_positive"),
    )

    id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    
    # Información del taller
    workshop_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    owner_name: Mapped[str] = mapped_column(String(120), nullable=False)  # Nombre del propietario
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    workshop_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)  # Teléfono del taller (diferente al del dueño)
    
    # Ubicación del taller (para asignación geoespacial)
    latitude: Mapped[float] = mapped_column(Numeric(10, 8), nullable=False, index=True)
    longitude: Mapped[float] = mapped_column(Numeric(11, 8), nullable=False, index=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Disponibilidad y cobertura
    coverage_radius_km: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True, default=10.0)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    is_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False)

    __mapper_args__ = {
        "polymorphic_identity": "workshop",
    }

