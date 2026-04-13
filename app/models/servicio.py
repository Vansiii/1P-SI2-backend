from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Servicio(Base):
    """
    Tipo de servicio mecánico ofrecido.
    Ej: "Cambio de batería", "Reparación de llanta", "Paso de corriente", etc.
    Cada servicio pertenece a una categoría.
    """

    __tablename__ = "servicios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"), nullable=False, index=True)
    
    # Relaciones
    # categoria = relationship("Categoria", back_populates="servicios")
    # talleres = relationship("ServicioTaller", back_populates="servicio")

