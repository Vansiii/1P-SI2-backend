from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class ShoppingCart(Base):
    """Encabezado del carrito de compras del cliente."""
    __tablename__ = "shopping_carts"
    __table_args__ = (
        UniqueConstraint("client_id", name="uq_shopping_cart_client"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, converted, abandoned
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    client = relationship("Client")
    items = relationship("CartItem", back_populates="cart", cascade="all, delete-orphan")
