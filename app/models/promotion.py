from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class Promotion(Base):
    """Promociones y descuentos creados por los talleres."""
    __tablename__ = "promotions"
    __table_args__ = (
        Index("idx_promotions_tenant", "tenant_id"),
        Index("idx_promotions_active", "tenant_id", "is_active", "starts_at", "ends_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Tipo: percentage, fixed_amount, buy_x_get_y
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    # Aplicabilidad: all, category, product, listing
    applies_to: Mapped[str] = mapped_column(String(20), nullable=False, default="all")
    target_ids: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=list)  # Lista de IDs de categorías, productos o listings

    # Vigencia
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Límites
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_uses: Mapped[int] = mapped_column(Integer, default=0)
    min_purchase: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant")
