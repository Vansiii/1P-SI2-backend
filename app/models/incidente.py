from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Incidente(Base):
    """
    Emergencia vehicular reportada por un cliente.
    Contiene ubicación GPS, descripción, evidencias y estado del servicio.
    """

    __tablename__ = "incidentes"
    __table_args__ = (
        CheckConstraint(
            "prioridad_ia IN ('alta', 'media', 'baja') OR prioridad_ia IS NULL",
            name="check_prioridad_ia_valid"
        ),
        CheckConstraint(
            "estado_actual IN ('pendiente', 'asignado', 'en_proceso', 'resuelto', 'cancelado', 'sin_taller_disponible')",
            name="check_estado_actual_valid"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Relaciones principales
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    vehiculo_id: Mapped[int] = mapped_column(ForeignKey("vehiculos.id"), nullable=False, index=True)
    taller_id: Mapped[int | None] = mapped_column(ForeignKey("workshops.id"), nullable=True, index=True)
    tecnico_id: Mapped[int | None] = mapped_column(ForeignKey("technicians.id"), nullable=True, index=True)
    
    # Relaciones ORM
    client = relationship("Client", back_populates="incidentes")
    vehiculo = relationship("Vehiculo", back_populates="incidentes")
    workshop = relationship("Workshop", back_populates="incidentes")
    technician = relationship("Technician", back_populates="incidentes")
    
    # Sesiones de tracking asociadas al incidente
    tracking_sessions = relationship(
        "TrackingSession",
        back_populates="incidente",
        cascade="all, delete-orphan"
    )
    
    # Ubicación del incidente
    latitude: Mapped[float] = mapped_column(Numeric(10, 8), nullable=False, index=True)
    longitude: Mapped[float] = mapped_column(Numeric(11, 8), nullable=False, index=True)
    direccion_referencia: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Descripción del problema
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Clasificación por IA
    categoria_ia: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Categoría detectada por IA
    prioridad_ia: Mapped[str | None] = mapped_column(String(20), nullable=True)  # alta, media, baja
    resumen_ia: Mapped[str | None] = mapped_column(Text, nullable=True)  # Resumen generado por IA
    es_ambiguo: Mapped[bool] = mapped_column(nullable=False, default=False)  # Si la IA no pudo clasificar
    
    # Estado actual del incidente
    estado_actual: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pendiente", index=True
    )  # pendiente, asignado, en_proceso, resuelto, cancelado
    
    # Timestamps de tracking
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

