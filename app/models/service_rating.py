from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ServiceRating(Base):
    """
    Calificación del servicio recibido por el cliente.
    Permite al cliente evaluar la calidad del servicio después de que el incidente sea resuelto.
    """

    __tablename__ = "service_ratings"
    __table_args__ = (
        CheckConstraint(
            "rating >= 1 AND rating <= 5",
            name="check_rating_range"
        ),
        # Ensure one rating per incident
        Index('idx_service_ratings_incident_unique', 'incident_id', unique=True),
        # Performance indexes
        Index('idx_service_ratings_workshop', 'workshop_id', 'created_at'),
        Index('idx_service_ratings_technician', 'technician_id', 'created_at'),
        Index('idx_service_ratings_client', 'client_id', 'created_at'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Tenant isolation
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    
    # Relaciones principales
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidentes.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    workshop_id: Mapped[int] = mapped_column(
        ForeignKey("workshops.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    technician_id: Mapped[int | None] = mapped_column(
        ForeignKey("technicians.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # Calificación y comentario
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5 estrellas
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)  # Comentario opcional
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # Relaciones ORM
    incident = relationship("Incidente", backref="rating")
    client = relationship("Client", backref="ratings_given")
    workshop = relationship("Workshop", backref="ratings_received")
    technician = relationship("Technician", backref="ratings_received")
