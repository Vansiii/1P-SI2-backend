from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .user import User


class Administrator(User):
    """
    Administrador del sistema.
    Responsable de la operación global de la plataforma.
    Accede al panel de administración con privilegios totales.
    Los campos first_name, last_name, email y phone se heredan de User.
    """

    __tablename__ = "administrators"

    id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    
    # Nivel de privilegios (puede ser útil para diferentes tipos de admin)
    role_level: Mapped[str | None] = mapped_column(String(50), nullable=True, default="super_admin")

    __mapper_args__ = {
        "polymorphic_identity": "admin",
    }

