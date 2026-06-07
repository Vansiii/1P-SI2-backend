from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class CotizacionRespuesta(Base):
    __tablename__ = "cotizacion_respuestas"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('pendiente', 'aceptada', 'rechazada', 'expirada')",
            name="check_cotizacion_respuesta_estado_valid"
        ),
        Index("idx_cotizacion_resp_cotizacion", "cotizacion_id"),
        Index("idx_cotizacion_resp_workshop", "workshop_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cotizacion_id: Mapped[int] = mapped_column(ForeignKey("cotizaciones.id"), nullable=False, index=True)
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"), nullable=False, index=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)

    servicios: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    costo_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    tiempo_estimado_minutos: Mapped[int] = mapped_column(nullable=False)
    tiempo_estimado_texto: Mapped[str] = mapped_column(String(200), nullable=False)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    valida_hasta: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    estado: Mapped[str] = mapped_column(String(50), nullable=False, default="pendiente", index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    cotizacion = relationship("Cotizacion", back_populates="respuestas")
    workshop = relationship("Workshop", foreign_keys=[workshop_id])
