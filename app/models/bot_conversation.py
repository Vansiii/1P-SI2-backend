from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class BotConversation(Base):
    """
    Representa una conversación del bot de asistencia interactivo con un usuario.
    """
    __tablename__ = "bot_conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)  # Título autogenerado basado en el primer mensaje
    vehicle_id: Mapped[int | None] = mapped_column(
        ForeignKey("vehiculos.id", ondelete="SET NULL"), nullable=True, index=True
    )  # Vehículo de contexto (opcional)

    # Relaciones
    user = relationship("User")
    vehicle = relationship("Vehiculo")
    messages = relationship(
        "BotMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="BotMessage.created_at.asc()",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
