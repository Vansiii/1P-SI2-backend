from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class InventoryCategory(Base):
    """Categorías de inventario por taller."""
    __tablename__ = "inventory_categories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", "parent_id", name="uq_inv_category_tenant_name_parent"),
        Index("idx_inv_categories_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_categories.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    parent = relationship("InventoryCategory", remote_side="InventoryCategory.id", back_populates="children")
    children = relationship("InventoryCategory", back_populates="parent")
    products = relationship("InventoryProduct", back_populates="category")
