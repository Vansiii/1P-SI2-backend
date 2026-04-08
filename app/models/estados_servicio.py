from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class EstadosServicio(Base):
    """
    Catálogo de estados posibles para un incidente/servicio.
    Ej: pendiente, asignado, en_camino, en_proceso, resuelto, cancelado
    """

    __tablename__ = "estados_servicio"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    descripcion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Relaciones
    # historiales = relationship("HistorialServicio", back_populates="estado")

