from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class MarketplaceListingImage(Base):
    """Galería de imágenes adicionales para un listado del marketplace."""
    __tablename__ = "marketplace_listing_images"
    __table_args__ = (
        Index("idx_mkt_images_listing", "listing_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("marketplace_listings.id", ondelete="CASCADE"), nullable=False)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    listing = relationship("MarketplaceListing", back_populates="images_gallery")
