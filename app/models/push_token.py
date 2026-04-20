"""
Modelo para tokens de notificaciones push.
"""
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PushToken(Base):
    """
    Token de Firebase Cloud Messaging para notificaciones push.
    Un usuario puede tener múltiples tokens (varios dispositivos).
    """

    __tablename__ = "push_tokens"
    __table_args__ = (
        CheckConstraint("platform IN ('android', 'ios', 'web')", name="check_platform_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    
    # Token de FCM
    token: Mapped[str] = mapped_column(String(500), nullable=False, unique=True, index=True)
    
    # Información del dispositivo
    platform: Mapped[str] = mapped_column(String(20), nullable=False)  # android, ios, web
    device_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Estado
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
