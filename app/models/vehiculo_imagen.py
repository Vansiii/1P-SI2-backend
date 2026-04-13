from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class VehiculoImagen(Base):
    """
    Imagen de un vehículo.
    Un vehículo puede tener múltiples imágenes.
    """

    __tablename__ = "vehiculos_imagenes"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehiculo_id: Mapped[int] = mapped_column(ForeignKey("vehiculos.id"), nullable=False, index=True)
    
    # Información del archivo
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)  # Nombre original del archivo
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)  # URL completa en Supabase Storage
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)  # Tipo: 'image'
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)  # image/jpeg, image/png, etc.
    size: Mapped[int] = mapped_column(Integer, nullable=False)  # Tamaño en bytes
    
    # Usuario que subió el archivo
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    
    # Metadata adicional
    es_principal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # Imagen principal del vehículo
    descripcion: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Descripción opcional
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # Orden de visualización
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
