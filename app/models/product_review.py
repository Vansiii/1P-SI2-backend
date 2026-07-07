from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class ProductReview(Base):
    """Calificaciones y reseñas hechas por clientes sobre productos comprados."""
    __tablename__ = "product_reviews"
    __table_args__ = (
        UniqueConstraint("listing_id", "client_id", "order_id", name="uq_product_review_listing_client_order"),
        Index("idx_product_reviews_listing", "listing_id"),
        Index("idx_product_reviews_client", "client_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("marketplace_listings.id"), nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    order_id: Mapped[int] = mapped_column(ForeignKey("marketplace_orders.id"), nullable=False)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)  # Taller vendedor

    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 a 5 estrellas
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_verified: Mapped[bool] = mapped_column(Boolean, default=True)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    listing = relationship("MarketplaceListing")
    client = relationship("Client")
    order = relationship("MarketplaceOrder")
    tenant = relationship("Tenant")
