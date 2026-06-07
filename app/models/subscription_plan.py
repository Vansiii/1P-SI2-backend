from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, func
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    billing_period: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")
    stripe_price_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_product_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    max_technicians: Mapped[int] = mapped_column(Integer, default=5)
    max_services: Mapped[int] = mapped_column(Integer, default=20)
    enable_kpis: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_reports: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_realtime_tracking: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_quotes: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_voice_reports: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sa.text('true'))
    enable_priority_support: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_api_access: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_white_label: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    subscriptions = relationship(
        "TenantSubscription",
        back_populates="plan",
        foreign_keys="[TenantSubscription.plan_id]"
    )
