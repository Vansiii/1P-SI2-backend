from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class SubscriptionInvoice(Base):
    __tablename__ = "subscription_invoices"
    __table_args__ = (
        Index("idx_si_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"), nullable=False
    )
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("tenant_subscriptions.id"), nullable=True
    )
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="usd")
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    stripe_invoice_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invoice_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    tenant = relationship("Tenant", back_populates="invoices")
    subscription = relationship("TenantSubscription", back_populates="invoices")
