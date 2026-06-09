from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class CotizacionChatSala(Base):
    __tablename__ = "cotizacion_chat_salas"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('activa', 'cerrada_aceptada', 'cerrada_sin_acuerdo')",
            name="check_cotizacion_chat_sala_estado"
        ),
        Index("ix_cotizacion_chat_salas_cotizacion", "cotizacion_id"),
        Index("ix_cotizacion_chat_salas_conversation", "conversation_id"),
        Index("ix_cotizacion_chat_salas_estado", "estado"),
        Index("ix_cotizacion_chat_salas_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cotizacion_id: Mapped[int] = mapped_column(ForeignKey("cotizaciones.id"), nullable=False)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"), nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True)

    estado: Mapped[str] = mapped_column(String(30), nullable=False, default="activa")
    ultima_oferta_monto: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    ultima_oferta_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    cerrada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cotizacion = relationship("Cotizacion", foreign_keys=[cotizacion_id], viewonly=True)
    conversation = relationship("Conversation", foreign_keys=[conversation_id])
    client = relationship("User", foreign_keys=[client_id])
    workshop = relationship("Workshop", foreign_keys=[workshop_id])
