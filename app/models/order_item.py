from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class OrderItem(Base):
    """Items individuales pertenecientes a una orden del marketplace."""
    __tablename__ = "order_items"
    __table_args__ = (
        Index("idx_order_items_order", "order_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("marketplace_orders.id", ondelete="CASCADE"), nullable=False)
    listing_id: Mapped[int] = mapped_column(ForeignKey("marketplace_listings.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("inventory_products.id"), nullable=False)

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    total_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    # Snapshot al momento de la compra
    product_name: Mapped[str] = mapped_column(String(300), nullable=False)
    product_sku: Mapped[str | None] = mapped_column(String(50), nullable=True)
    product_brand: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    order = relationship("MarketplaceOrder", back_populates="items")
    listing = relationship("MarketplaceListing")
    product = relationship("InventoryProduct")
