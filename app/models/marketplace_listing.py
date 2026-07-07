from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class MarketplaceListing(Base):
    """Listado de productos publicados en el marketplace."""
    __tablename__ = "marketplace_listings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "product_id", name="uq_mkt_listing_tenant_product"),
        Index("idx_mkt_listings_status", "status", postgresql_where="status = 'active'"),
        Index("idx_mkt_listings_tenant", "tenant_id"),
        Index("idx_mkt_listings_featured", "is_featured", "status"),
        Index("idx_mkt_listings_price", "public_price", postgresql_where="status = 'active'"),
        Index("idx_mkt_listings_rating", "avg_rating", postgresql_where="status = 'active'"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("inventory_products.id"), nullable=False, index=True)

    # Precios
    public_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    compare_at_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    # Visibilidad y Destacados
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)

    # Información override
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    slug: Mapped[str | None] = mapped_column(String(350), nullable=True)
    tags: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=list)

    # Stats
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    sale_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_rating: Mapped[float] = mapped_column(Numeric(3, 2), default=0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)

    # Envío / Retiro
    shipping_available: Mapped[bool] = mapped_column(Boolean, default=False)
    shipping_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    pickup_only: Mapped[bool] = mapped_column(Boolean, default=True)

    # Compatibilidad override (si difiere del producto de inventario)
    compatibility_override: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Estado
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, paused, sold_out, draft

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relaciones
    product = relationship("InventoryProduct")
    images_gallery = relationship("MarketplaceListingImage", back_populates="listing", cascade="all, delete-orphan")
