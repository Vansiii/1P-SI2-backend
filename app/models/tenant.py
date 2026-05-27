from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = (
        Index("idx_tenants_status", "status"),
        Index("idx_tenants_nit", "nit"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workshop_id: Mapped[int] = mapped_column(
        ForeignKey("workshops.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    nit: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    slug: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    business_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workshop = relationship("Workshop", foreign_keys=[workshop_id], uselist=False)
    owner = relationship("User", foreign_keys=[owner_user_id])
    subscriptions = relationship("TenantSubscription", back_populates="tenant")
    invoices = relationship("SubscriptionInvoice", back_populates="tenant")
