"""
Modelo para notificaciones del sistema.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Notification(Base):
    """
    Notificación enviada a un usuario.
    Puede ser push, email, o in-app.
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    
    # Contenido
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # incident_assigned, status_change, etc.
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Datos adicionales (JSON)
    data_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string con datos extra
    
    # Estado
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
