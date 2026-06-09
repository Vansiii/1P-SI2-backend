"""
Cotizaciones Reminders - CU32 v2.

Envia recordatorios push a:
- Talleres con cotizaciones v2 pendientes de responder (>30 min sin respuesta)
- Talleres con negociaciones activas sin actividad reciente (>1h)
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.logging import get_logger
from ..core.database import get_session_factory
from ..models.cotizacion import Cotizacion
from ..models.cotizacion_chat_sala import CotizacionChatSala

logger = get_logger(__name__)


async def process_cotizacion_reminders():
    async with get_session_factory()() as session:
        await _recordar_talleres_pendientes(session)
        await _recordar_negociaciones_inactivas(session)
        await session.commit()


async def _recordar_talleres_pendientes(session: AsyncSession):
    limite = datetime.now(timezone.utc) - timedelta(minutes=30)
    result = await session.execute(
        select(Cotizacion)
        .where(
            Cotizacion.estado == "cotizando",
            Cotizacion.version == "v2",
            Cotizacion.created_at < limite,
        )
        .options(selectinload(Cotizacion.workshop))
    )
    pendientes = result.scalars().all()

    from ..modules.push_notifications.services import PushNotificationService, PushNotificationData
    push = PushNotificationService(session)

    for c in pendientes:
        if not c.workshop_id:
            continue
        notif = PushNotificationData(
            title="Cotizacion pendiente",
            body=f"Tienes una solicitud de cotizacion sin responder desde hace mas de 30 minutos",
            data={"type": "recordatorio_cotizacion", "cotizacion_id": c.id},
        )
        try:
            await push.send_to_user(c.workshop_id, notif)
            logger.info(f"Recordatorio enviado a workshop {c.workshop_id} por cotizacion {c.id}")
        except Exception as e:
            logger.warning(f"No se pudo enviar recordatorio: {e}")


async def _recordar_negociaciones_inactivas(session: AsyncSession):
    limite = datetime.now(timezone.utc) - timedelta(hours=1)
    result = await session.execute(
        select(CotizacionChatSala)
        .where(
            CotizacionChatSala.estado == "activa",
            CotizacionChatSala.ultima_oferta_at < limite,
        )
    )
    salas = result.scalars().all()

    from ..modules.push_notifications.services import PushNotificationService, PushNotificationData
    push = PushNotificationService(session)

    for sala in salas:
        notif = PushNotificationData(
            title="Negociacion inactiva",
            body="La negociacion de cotizacion no tiene actividad en la ultima hora",
            data={"type": "recordatorio_negociacion", "cotizacion_id": sala.cotizacion_id},
        )
        try:
            await push.send_to_user(sala.client_id, notif)
            await push.send_to_user(sala.workshop_id, notif)
            logger.info(f"Recordatorio de negociacion enviado para cotizacion {sala.cotizacion_id}")
        except Exception as e:
            logger.warning(f"No se pudo enviar recordatorio de negociacion: {e}")
