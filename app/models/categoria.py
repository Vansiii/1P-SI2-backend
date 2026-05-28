from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Categoria(Base):
    """
    Categoría de servicios mecánicos.
    Ej: Batería, Llanta, Motor, Choque, Pérdida de llaves, etc.
    """

    __tablename__ = "categorias"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    descripcion: Mapped[str | None] = mapped_column(String(500), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    # Relaciones
    servicios = relationship("Servicio", back_populates="categoria")

