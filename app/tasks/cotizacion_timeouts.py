"""
Cotizaciones Timeout Handler.

Verifica cotizaciones que necesitan accion automatica:
- Cotizaciones sin respuesta despues de 24h -> rechazadas
- Respuestas de taller expiradas (valida_hasta vencida) -> marcadas como expiradas
"""
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging import get_logger
from ..core.database import get_session_factory
from ..models.cotizacion import Cotizacion
from ..models.cotizacion_respuesta import CotizacionRespuesta

logger = get_logger(__name__)


async def process_cotizacion_timeouts():
    async with get_session_factory()() as session:
        await _expirar_respuestas(session)
        await _rechazar_sin_respuesta(session)
        await session.commit()


async def _expirar_respuestas(session: AsyncSession):
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(CotizacionRespuesta).where(
            CotizacionRespuesta.estado == "pendiente",
            CotizacionRespuesta.valida_hasta < now,
        )
    )
    expiradas = result.scalars().all()
    for r in expiradas:
        r.estado = "expirada"
        logger.info(f"CotizacionRespuesta {r.id} expirada (cotizacion={r.cotizacion_id})")


async def _rechazar_sin_respuesta(session: AsyncSession):
    from datetime import timedelta
    limite = datetime.now(timezone.utc) - timedelta(hours=24)
    result = await session.execute(
        select(Cotizacion).where(
            Cotizacion.estado.in_(["pendiente_cotizacion", "cotizando"]),
            Cotizacion.created_at < limite,
        )
    )
    sin_respuesta = result.scalars().all()
    for c in sin_respuesta:
        c.estado = "rechazado"
        logger.info(f"Cotizacion {c.id} rechazada por timeout (sin respuesta en 24h)")
