from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .user import User


class Client(User):
    """
    Cliente (usuario final de la app móvil).
    Persona natural que conduce un vehículo y puede reportar emergencias vehiculares.
    Los campos first_name, last_name, email y phone se heredan de User.
    """

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    
    # Información adicional del cliente
    direccion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ci: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True, index=True)
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date, nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "client",
    }

