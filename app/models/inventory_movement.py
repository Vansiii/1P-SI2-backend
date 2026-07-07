from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class InventoryMovement(Base):
    """Movimiento de inventario (entrada, salida, ajuste)."""
    __tablename__ = "inventory_movements"
    __table_args__ = (
        Index("idx_inv_movements_tenant", "tenant_id"),
        Index("idx_inv_movements_product", "product_id"),
        Index("idx_inv_movements_type", "tenant_id", "type"),
        Index("idx_inv_movements_date", "tenant_id", "created_at"),
        Index("idx_inv_movements_reference", "reference_type", "reference_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("inventory_products.id"), nullable=False, index=True)

    type: Mapped[str] = mapped_column(String(20), nullable=False)  # entrada, salida, ajuste, devolucion, venta_marketplace
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)  # positivo=entrada, negativo=salida

    # Costos en el momento
    unit_cost: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    total_cost: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    # Referencia
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # compra, incidente, ajuste_manual, orden_marketplace
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Stock resultante
    stock_before: Mapped[int] = mapped_column(Integer, nullable=False)
    stock_after: Mapped[int] = mapped_column(Integer, nullable=False)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product = relationship("InventoryProduct", back_populates="movements")
