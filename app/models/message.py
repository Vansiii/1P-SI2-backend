"""
Modelo para mensajes de chat.
"""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text, func, Index
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Message(Base):
    """
    Mensaje de chat entre cliente y técnico en un incidente.
    """

    __tablename__ = "messages"
    __table_args__ = (
        # Performance indexes for chat queries
        Index(
            'idx_messages_incident_created',
            'incident_id', sa.text('created_at DESC')
        ),
        Index(
            'idx_messages_unread',
            'is_read', 'created_at',
            postgresql_where=sa.text("is_read = false")
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidentes.id"), nullable=False, index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    
    # Contenido del mensaje
    message: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")  # text, image, audio, system
    
    # Metadata
    is_read: Mapped[bool] = mapped_column(nullable=False, default=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    # incident = relationship("Incidente", back_populates="messages")
    # sender = relationship("User", back_populates="messages")
