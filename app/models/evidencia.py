from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Evidencia(Base):
    """
    Evidencia multimedia adjunta a un incidente.
    Puede ser imagen, audio o texto.
    """

    __tablename__ = "evidencias"
    __table_args__ = (
        CheckConstraint("tipo IN ('TEXT', 'IMAGE', 'AUDIO')", name="check_tipo_evidencia_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    incidente_id: Mapped[int] = mapped_column(ForeignKey("incidentes.id"), nullable=False, index=True)
    uploaded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    
    # Tipo de evidencia
    tipo: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # 'TEXT', 'IMAGE', 'AUDIO'
    
    # Contenido
    descripcion: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    # Metadata adicional (JSONB para flexibilidad)
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
