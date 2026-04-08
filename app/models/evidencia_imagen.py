from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class EvidenciaImagen(Base):
    """
    Imagen adjunta como evidencia de un incidente.
    Almacena la URL de la imagen (puede estar en S3, Supabase Storage, etc.)
    """

    __tablename__ = "evidencias_imagenes"

    id: Mapped[int] = mapped_column(primary_key=True)
    evidencia_id: Mapped[int] = mapped_column(ForeignKey("evidencias.id"), nullable=False, index=True)
    
    # URL de la imagen almacenada
    imagen_url: Mapped[str] = mapped_column(String(500), nullable=False)
    
    # Relaciones
    # evidencia = relationship("Evidencia", back_populates="imagenes")
