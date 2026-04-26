from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class TechnicianEspecialidad(Base):
    """
    Tabla intermedia para relación muchos-a-muchos entre técnicos y especialidades.
    Un técnico puede tener múltiples especialidades.
    Una especialidad puede pertenecer a múltiples técnicos.
    """

    __tablename__ = "technician_especialidades"
    __table_args__ = (
        UniqueConstraint("technician_id", "especialidad_id", name="uq_technician_especialidad"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    technician_id: Mapped[int] = mapped_column(ForeignKey("technicians.id"), nullable=False, index=True)
    especialidad_id: Mapped[int] = mapped_column(ForeignKey("especialidades.id"), nullable=False, index=True)
    
    # Relaciones
    technician = relationship("Technician", back_populates="especialidades")
    especialidad = relationship("Especialidad", back_populates="technicians")

