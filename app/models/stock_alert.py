from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class StockAlert(Base):
    """Alerta de stock bajo o agotado."""
    __tablename__ = "stock_alerts"
    __table_args__ = (
        Index("idx_stock_alerts_tenant_unread", "tenant_id",
              postgresql_where="is_read = false"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("inventory_products.id"), nullable=False, index=True)

    alert_type: Mapped[str] = mapped_column(String(30), nullable=False)  # low_stock, out_of_stock, overstock
    current_stock: Mapped[int] = mapped_column(Integer, nullable=False)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)

    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product = relationship("InventoryProduct")
