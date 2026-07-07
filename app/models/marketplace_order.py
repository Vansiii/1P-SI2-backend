from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class MarketplaceOrder(Base):
    """Órdenes de compra generadas en el marketplace."""
    __tablename__ = "marketplace_orders"
    __table_args__ = (
        UniqueConstraint("order_number", name="uq_mkt_order_number"),
        Index("idx_mkt_orders_client", "client_id"),
        Index("idx_mkt_orders_tenant", "tenant_id"),
        Index("idx_mkt_orders_status", "status"),
        Index("idx_mkt_orders_number", "order_number"),
        Index("idx_mkt_orders_date", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(50), nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)  # Taller vendedor

    # Montos
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    shipping_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    discount_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    platform_commission: Mapped[float] = mapped_column(Numeric(12, 2), default=0)  # 10% de la plataforma

    # Estado de la Orden
    # pending_payment, paid, confirmed, preparing, ready_pickup, shipped, delivered, completed, cancelled, refunded
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_payment")

    # Pago Stripe
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payment_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, paid, failed, refunded
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Entrega
    delivery_type: Mapped[str] = mapped_column(String(20), default="pickup")  # pickup, shipping
    delivery_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    client = relationship("Client")
    tenant = relationship("Tenant")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
