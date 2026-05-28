from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ServicioTaller(Base):
    """
    Tabla intermedia N:M entre Taller y Servicio.
    Indica qué servicios ofrece cada taller y a qué precio.
    """

    __tablename__ = "servicios_taller"
    __table_args__ = (
        UniqueConstraint("taller_id", "servicio_id", name="uq_taller_servicio"),
        CheckConstraint("precio >= 0", name="check_precio_positive"),
        Index("idx_st_servicio_active", "servicio_id", "is_active"),
        Index("idx_st_taller_active", "taller_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    taller_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"), nullable=False, index=True)
    servicio_id: Mapped[int] = mapped_column(ForeignKey("servicios.id"), nullable=False, index=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    precio: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    modalidad: Mapped[str] = mapped_column(
        String(20), nullable=False, default="taller"
    )
    tiempo_estimado_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    descripcion: Mapped[str | None] = mapped_column(String(500), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    servicio = relationship("Servicio", back_populates="talleres")
    taller = relationship("Workshop", back_populates="catalogo")

