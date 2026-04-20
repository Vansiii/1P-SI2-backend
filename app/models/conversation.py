"""
Modelo para conversaciones de chat.
"""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Conversation(Base):
    """
    Conversación de chat asociada a un incidente.
    Agrupa todos los mensajes entre cliente y técnico/taller.
    """

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidentes.id"), nullable=False, unique=True, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    workshop_id: Mapped[int | None] = mapped_column(ForeignKey("workshops.id"), nullable=True, index=True)
    
    # Metadata
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unread_count_client: Mapped[int] = mapped_column(nullable=False, default=0)
    unread_count_workshop: Mapped[int] = mapped_column(nullable=False, default=0)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    # incident = relationship("Incidente", back_populates="conversation")
    # client = relationship("Client", back_populates="conversations")
    # workshop = relationship("Workshop", back_populates="conversations")
