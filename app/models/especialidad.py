from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Especialidad(Base):
    """
    Catálogo de especialidades técnicas disponibles.
    Ejemplos: Mecánica general, Electricidad automotriz, Llantas y suspensión, etc.
    """

    __tablename__ = "especialidades"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    descripcion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Relaciones
    technicians = relationship("TechnicianEspecialidad", back_populates="especialidad")

