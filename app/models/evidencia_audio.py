from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class EvidenciaAudio(Base):
    """
    Audio adjunto como evidencia de un incidente.
    Almacena la URL del archivo de audio y metadata.
    """

    __tablename__ = "evidencias_audios"

    id: Mapped[int] = mapped_column(primary_key=True)
    evidencia_id: Mapped[int] = mapped_column(ForeignKey("evidencias.id"), nullable=False, index=True)
    
    # Información del archivo
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)  # Nombre original del archivo
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)  # URL completa en Supabase Storage
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)  # Tipo: 'audio'
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)  # audio/mpeg, audio/wav, etc.
    size: Mapped[int] = mapped_column(Integer, nullable=False)  # Tamaño en bytes
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Duración en segundos (opcional)
    
    # Usuario que subió el archivo
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
