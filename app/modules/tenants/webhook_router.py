import json
import stripe
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core import get_logger, get_settings
from app.models.stripe_event_log import StripeEventLog
from app.models.tenant_subscription import TenantSubscription
from app.models.subscription_invoice import SubscriptionInvoice
from app.models.subscription_plan import SubscriptionPlan
from app.models.tenant import Tenant
from app.models.audit_log import AuditLog

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    """Procesar webhooks de Stripe. Idempotente via stripe_event_id."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(400, "Missing stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "Invalid signature")
    except ValueError:
        raise HTTPException(400, "Invalid payload")

    existing = await session.scalar(
        select(StripeEventLog).where(StripeEventLog.stripe_event_id == event.id)
    )
    if existing:
        return {"status": "already_processed"}

    log = StripeEventLog(
        stripe_event_id=event.id,
        event_type=event.type,
        payload=json.dumps(event.data if hasattr(event, "data") else {}),
        status="received",
    )
    session.add(log)

    try:
        handler_name = f"_handle_{event.type.replace('.', '_')}"
        handler = globals().get(handler_name)
        if callable(handler):
            await handler(event, session)

        log.status = "processed"
        log.processed_at = datetime.now(UTC)
        await session.commit()
    except Exception as e:
        log.status = "failed"
        log.error_message = str(e)
        await session.commit()
        logger.exception(f"Failed to process webhook {event.type}")

    return {"status": "processed"}


async def _handle_checkout_session_completed(event, session):
    obj = event.data.object
    metadata = obj.get("metadata", {})
    tenant_id = int(metadata.get("tenant_id", 0))
    plan_id = int(metadata.get("plan_id", 0))

    if not tenant_id:
        return

    result = await session.execute(
        select(TenantSubscription).where(
            TenantSubscription.tenant_id == tenant_id,
        ).order_by(TenantSubscription.created_at.desc()).limit(1)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return

    old_status = sub.status
    old_plan_id = sub.plan_id

    sub.payment_provider = "stripe"
    sub.provider_subscription_id = obj.get("subscription")
    sub.provider_customer_id = obj.get("customer")
    if plan_id:
        sub.plan_id = plan_id

    stripe_sub = stripe.Subscription.retrieve(obj.get("subscription"))
    sub.current_period_start = datetime.fromtimestamp(stripe_sub.current_period_start, tz=UTC)
    sub.current_period_end = datetime.fromtimestamp(stripe_sub.current_period_end, tz=UTC)

    if sub.status in ("pending_downgrade", "pending_cancellation"):
        sub.status = "active"
    else:
        sub.status = "active"
    sub.pending_plan_id = None

    session.add(AuditLog(
        tenant_id=tenant_id,
        user_id=None,
        action="STRIPE_CHECKOUT_COMPLETED",
        resource_type="subscription",
        resource_id=sub.id,
        ip_address="system",
        details=json.dumps({
            "stripe_subscription_id": obj.get("subscription"),
            "plan_id": plan_id,
            "old_status": old_status,
            "old_plan_id": old_plan_id,
        }),
    ))


async def _handle_invoice_payment_succeeded(event, session):
    obj = event.data.object
    subscription_id = obj.get("subscription")
    if not subscription_id:
        return

    result = await session.execute(
        select(TenantSubscription).where(
            TenantSubscription.provider_subscription_id == subscription_id,
        )
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return

    sub.grace_until = None

    if sub.status == "past_due":
        sub.status = "active"

    inv = SubscriptionInvoice(
        tenant_id=sub.tenant_id,
        subscription_id=sub.id,
        amount=float(obj.get("amount_paid", 0)) / 100,
        currency=obj.get("currency", "usd"),
        status="paid",
        stripe_invoice_id=obj.get("id"),
        stripe_payment_intent_id=obj.get("payment_intent"),
        invoice_url=obj.get("hosted_invoice_url"),
        paid_at=datetime.now(UTC),
    )
    session.add(inv)


async def _handle_invoice_payment_failed(event, session):
    obj = event.data.object
    subscription_id = obj.get("subscription")
    if not subscription_id:
        return

    result = await session.execute(
        select(TenantSubscription).where(
            TenantSubscription.provider_subscription_id == subscription_id,
        )
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return

    old_status = sub.status
    sub.status = "past_due"
    sub.grace_until = datetime.now(UTC) + timedelta(hours=settings.grace_period_hours)

    session.add(AuditLog(
        tenant_id=sub.tenant_id,
        action="PAYMENT_FAILED",
        resource_type="subscription",
        resource_id=sub.id,
        ip_address="system",
        details=json.dumps({
            "stripe_invoice_id": obj.get("id"),
            "old_status": old_status,
        }),
    ))


async def _handle_customer_subscription_deleted(event, session):
    obj = event.data.object
    result = await session.execute(
        select(TenantSubscription).where(
            TenantSubscription.provider_subscription_id == obj.get("id"),
        )
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return

    old_status = sub.status

    if sub.status == "pending_downgrade" and sub.pending_plan_id:
        sub.plan_id = sub.pending_plan_id
        sub.pending_plan_id = None
        sub.status = "active"
        sub.payment_provider = "free"
        sub.provider_subscription_id = None
        sub.provider_customer_id = None
        sub.current_period_start = datetime.now(UTC)
        sub.current_period_end = datetime.now(UTC) + timedelta(days=30)

        session.add(AuditLog(
            tenant_id=sub.tenant_id,
            action="PLAN_DOWNGRADE_APPLIED",
            resource_type="subscription",
            resource_id=sub.id,
            ip_address="system",
            details=json.dumps({
                "stripe_subscription_deleted": obj.get("id"),
                "applied_plan_id": sub.plan_id,
                "old_status": old_status,
            }),
        ))
        logger.info(
            "Applied pending downgrade for tenant %s. New plan %s",
            sub.tenant_id, sub.plan_id,
        )

    elif sub.status == "pending_cancellation":
        sub.status = "canceled"
        sub.cancel_at_period_end = True

        session.add(AuditLog(
            tenant_id=sub.tenant_id,
            action="SUBSCRIPTION_CANCELLED",
            resource_type="subscription",
            resource_id=sub.id,
            ip_address="system",
            details=json.dumps({
                "stripe_subscription_deleted": obj.get("id"),
                "old_status": old_status,
            }),
        ))

    elif sub.status in ("active", "trialing", "past_due"):
        sub.status = "expired"

        session.add(AuditLog(
            tenant_id=sub.tenant_id,
            action="SUBSCRIPTION_EXPIRED",
            resource_type="subscription",
            resource_id=sub.id,
            ip_address="system",
            details=json.dumps({
                "stripe_subscription_deleted": obj.get("id"),
                "old_status": old_status,
            }),
        ))
