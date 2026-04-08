from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .user import User


class Technician(User):
    """
    Técnico de taller (personal operativo).
    Asignado por el taller para atención presencial de incidentes.
    Accede desde app móvil con vista simplificada.
    Los campos first_name, last_name, email y phone se heredan de User.
    """

    __tablename__ = "technicians"

    id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    
    # Relación con el taller
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"), nullable=False, index=True)
    
    # Ubicación en tiempo real (actualizada por GPS)
    current_latitude: Mapped[float | None] = mapped_column(Numeric(10, 8), nullable=True)
    current_longitude: Mapped[float | None] = mapped_column(Numeric(11, 8), nullable=True)
    
    # Disponibilidad
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    is_on_duty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __mapper_args__ = {
        "polymorphic_identity": "technician",
    }

