from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class CartItem(Base):
    """Ítems dentro del carrito de compras."""
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("cart_id", "listing_id", name="uq_cart_item_cart_listing"),
        Index("idx_cart_items_cart", "cart_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cart_id: Mapped[int] = mapped_column(ForeignKey("shopping_carts.id", ondelete="CASCADE"), nullable=False)
    listing_id: Mapped[int] = mapped_column(ForeignKey("marketplace_listings.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)  # Precio al momento de agregar
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    cart = relationship("ShoppingCart", back_populates="items")
    listing = relationship("MarketplaceListing")
