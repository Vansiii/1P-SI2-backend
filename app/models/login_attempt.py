from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class LoginAttempt(Base):
    """
    Registro de intentos de login para detectar y prevenir ataques de fuerza bruta.
    Permite bloquear cuentas después de múltiples intentos fallidos.
    """

    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False, index=True)  # IPv4 o IPv6
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    failure_reason: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # 'invalid_credentials', 'account_locked', etc.
    locked_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

