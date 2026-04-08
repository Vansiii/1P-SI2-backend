from sqlalchemy import CheckConstraint, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

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
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    taller_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"), nullable=False, index=True)
    servicio_id: Mapped[int] = mapped_column(ForeignKey("servicios.id"), nullable=False, index=True)
    precio: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)  # Precio del servicio en este taller

