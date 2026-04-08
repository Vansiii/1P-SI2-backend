from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class EvidenciaAudio(Base):
    """
    Audio adjunto como evidencia de un incidente.
    Almacena la URL del archivo de audio y su transcripción (si aplica).
    """

    __tablename__ = "evidencias_audios"

    id: Mapped[int] = mapped_column(primary_key=True)
    evidencia_id: Mapped[int] = mapped_column(ForeignKey("evidencias.id"), nullable=False, index=True)
    
    # URL del audio almacenado
    audio_url: Mapped[str] = mapped_column(String(500), nullable=False)
    
    # Relaciones
    # evidencia = relationship("Evidencia", back_populates="audios")

