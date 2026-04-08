from datetime import time

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class WorkshopSchedule(Base):
    """
    Horarios de atención del taller por día de la semana.
    Permite filtros SQL eficientes para verificar disponibilidad.
    """

    __tablename__ = "workshop_schedules"
    __table_args__ = (
        CheckConstraint("day_of_week BETWEEN 0 AND 6", name="check_day_of_week_range"),
        UniqueConstraint("workshop_id", "day_of_week", name="uq_workshop_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id"), nullable=False, index=True)
    
    # Día de la semana (0=Lunes, 1=Martes, ..., 6=Domingo)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # Estado de apertura
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    
    # Horarios (tipo TIME de SQL)
    open_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    close_time: Mapped[time | None] = mapped_column(Time, nullable=True)

