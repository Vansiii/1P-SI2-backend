from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class InventoryProduct(Base):
    """Producto de inventario del taller."""
    __tablename__ = "inventory_products"
    __table_args__ = (
        CheckConstraint("current_stock >= 0", name="check_inv_stock_non_negative"),
        CheckConstraint("min_stock >= 0", name="check_inv_min_stock_non_negative"),
        CheckConstraint("cost_price >= 0", name="check_inv_cost_non_negative"),
        Index("idx_inv_products_tenant", "tenant_id"),
        Index("idx_inv_products_category", "category_id"),
        Index("idx_inv_products_supplier", "supplier_id"),
        Index("idx_inv_products_sku", "tenant_id", "sku", unique=True),
        Index("idx_inv_products_low_stock", "tenant_id",
              postgresql_where="current_stock <= min_stock AND is_active = true"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_categories.id"), nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)

    # Identificación
    sku: Mapped[str | None] = mapped_column(String(50), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    part_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Stock
    current_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    min_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_stock: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="unidad")
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Costos
    cost_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    avg_cost_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    # Compatibilidad vehicular
    compatible_brands: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=list)
    compatible_models: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=list)
    compatible_years: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    universal: Mapped[bool] = mapped_column(Boolean, default=False)

    # Estado
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)

    # Imágenes
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    images: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=list)

    # Timestamps + soft delete
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    category = relationship("InventoryCategory", back_populates="products")
    supplier = relationship("Supplier", back_populates="products")
    movements = relationship("InventoryMovement", back_populates="product", order_by="desc(InventoryMovement.created_at)")
