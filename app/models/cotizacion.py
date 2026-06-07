from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
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


class Cotizacion(Base):
    __tablename__ = "cotizaciones"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('pendiente_cotizacion', 'cotizando', 'cotizado', 'taller_seleccionado', "
            "'pago_pendiente', 'pagado', 'en_proceso', 'completado', 'cancelado', 'rechazado')",
            name="check_cotizacion_estado_valid"
        ),
        Index("idx_cotizaciones_client_estado", "client_id", "estado"),
        Index("idx_cotizaciones_tenant_estado", "tenant_id", "estado"),
        Index("idx_cotizaciones_workshop", "workshop_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    vehiculo_id: Mapped[int] = mapped_column(ForeignKey("vehiculos.id"), nullable=False, index=True)
    workshop_id: Mapped[int | None] = mapped_column(ForeignKey("workshops.id"), nullable=True, index=True)

    latitud: Mapped[float] = mapped_column(Numeric(10, 8), nullable=False)
    longitud: Mapped[float] = mapped_column(Numeric(11, 8), nullable=False)
    direccion_referencia: Mapped[str | None] = mapped_column(String(500), nullable=True)

    descripcion_dano: Mapped[str] = mapped_column(Text, nullable=False)
    imagenes_dano: Mapped[list | None] = mapped_column(ARRAY(String), nullable=True)
    audio_diagnostico: Mapped[str | None] = mapped_column(String(500), nullable=True)

    categoria_ia: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prioridad_ia: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resumen_ia: Mapped[str | None] = mapped_column(Text, nullable=True)
    es_ambiguo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    servicios_cotizados: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    costo_total_estimado: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    tiempo_total_estimado_minutos: Mapped[int | None] = mapped_column(nullable=True)
    notas_cotizacion: Mapped[str | None] = mapped_column(Text, nullable=True)

    estado: Mapped[str] = mapped_column(String(50), nullable=False, default="pendiente_cotizacion", index=True)

    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    monto_pagado: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    cotizado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    taller_seleccionado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pagado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    respuestas = relationship("CotizacionRespuesta", back_populates="cotizacion", cascade="all, delete-orphan")

    client = relationship("User", foreign_keys=[client_id])
    vehiculo = relationship("Vehiculo", foreign_keys=[vehiculo_id])
    workshop = relationship("Workshop", foreign_keys=[workshop_id])
