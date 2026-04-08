from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Vehiculo(Base):
    """
    Vehículo registrado por un cliente.
    Un cliente puede tener múltiples vehículos.
    """

    __tablename__ = "vehiculos"
    __table_args__ = (
        CheckConstraint("anio > 1900", name="check_anio_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    
    # Información del vehículo
    matricula: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)  # Placa
    marca: Mapped[str | None] = mapped_column(String(60), nullable=True)  # Ej: "Toyota"
    modelo: Mapped[str] = mapped_column(String(100), nullable=False)  # Ej: "Corolla"
    anio: Mapped[int] = mapped_column(Integer, nullable=False)  # Año de fabricación
    color: Mapped[str | None] = mapped_column(String(50), nullable=True)
    imagen: Mapped[str | None] = mapped_column(String(500), nullable=True)  # URL de la imagen del vehículo
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

