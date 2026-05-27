from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core import get_logger, get_settings
from app.models.tenant_subscription import TenantSubscription
from app.models.tenant import Tenant

logger = get_logger(__name__)
settings = get_settings()


async def check_expired_subscriptions():
    """
    Tarea periodica: verificar suscripciones vencidas.
    - Suspender past_due cuyo grace_until expiro
    - Notificar suscripciones que vencen en 7 dias

    Ejecutar con un scheduler (APScheduler, Celery, o cron) cada hora.
    """
    async for session in get_db_session():
        now = datetime.now(UTC)

        result = await session.execute(
            select(TenantSubscription).where(
                TenantSubscription.status == "past_due",
                TenantSubscription.grace_until < now,
            )
        )
        expired = result.scalars().all()

        for sub in expired:
            sub.status = "suspended"
            sub.suspended_reason = "Pago no recibido dentro del periodo de gracia"

            tenant = await session.get(Tenant, sub.tenant_id)
            if tenant and tenant.status == "active":
                tenant.status = "suspended"

            logger.info("Subscription suspended", tenant_id=sub.tenant_id, subscription_id=sub.id)

        if expired:
            await session.commit()
            logger.info(f"Suspended {len(expired)} expired subscriptions")

        seven_days = now + timedelta(days=7)
        result2 = await session.execute(
            select(TenantSubscription).where(
                TenantSubscription.status == "active",
                TenantSubscription.current_period_end < seven_days,
                TenantSubscription.current_period_end > now,
                TenantSubscription.cancel_at_period_end == False,
            )
        )
        expiring = result2.scalars().all()

        for sub in expiring:
            days_remaining = (sub.current_period_end - now).days
            logger.info(
                "Subscription expiring soon",
                tenant_id=sub.tenant_id,
                subscription_id=sub.id,
                days_remaining=days_remaining,
            )

        break


async def run_subscription_checker():
    """Entry point para scheduler."""
    try:
        await check_expired_subscriptions()
    except Exception:
        logger.exception("Subscription checker failed")


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_subscription_checker())
