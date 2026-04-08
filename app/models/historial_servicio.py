from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class HistorialServicio(Base):
    """
    Registro de cambios de estado de un incidente.
    Permite trazabilidad completa del servicio desde el reporte hasta la resolución.
    """

    __tablename__ = "historial_servicio"

    id: Mapped[int] = mapped_column(primary_key=True)
    incidente_id: Mapped[int] = mapped_column(ForeignKey("incidentes.id"), nullable=False, index=True)
    estado_id: Mapped[int] = mapped_column(ForeignKey("estados_servicio.id"), nullable=False, index=True)
    changed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    comentario: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Timestamp del cambio de estado
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

