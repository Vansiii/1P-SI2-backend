from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Configuracion(Base):
    """
    Parámetros de configuración del sistema.
    Ej: comisión de la plataforma, radio de cobertura por defecto, etc.
    """

    __tablename__ = "configuracion"

    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Comisión de la plataforma (porcentaje)
    comision: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=10.0)  # 10% por defecto
    
    # Otros parámetros pueden agregarse según necesidad
    # Ej: tiempo_max_respuesta, radio_busqueda_default, etc.

