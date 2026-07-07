from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, Text, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class BotMessage(Base):
    """
    Representa un mensaje individual (pregunta o respuesta) dentro de una conversación del bot.
    """
    __tablename__ = "bot_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("bot_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # "user" o "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Metadata IA (solo se completa en mensajes del asistente)
    model_used: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool_calls: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)

    # Relaciones
    conversation = relationship("BotConversation", back_populates="messages")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
