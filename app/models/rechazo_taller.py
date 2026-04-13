from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class RechazoTaller(Base):
    """
    Registro de rechazos de solicitudes por parte de talleres.
    Permite rastrear qué talleres rechazaron una solicitud y por qué.
    """

    __tablename__ = "rechazos_taller"

    id: Mapped[int] = mapped_column(primary_key=True)
    incidente_id: Mapped[int] = mapped_column(ForeignKey("incidentes.id"), nullable=False, index=True)
    taller_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"), nullable=False, index=True)
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Timestamp del rechazo
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
