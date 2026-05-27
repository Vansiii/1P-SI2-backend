from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import require_role, require_active_tenant, get_tenant_context, TenantContext
from app.core.permissions import UserRole
from app.core.responses import create_success_response
from app.shared.dependencies.auth import get_current_admin, get_current_workshop_user
from app.models.administrator import Administrator
from app.models.workshop import Workshop
from app.models.subscription_plan import SubscriptionPlan

from .schemas import (
    ApproveTenantRequest,
    RejectTenantRequest,
    PlanPublic,
)
from .services import TenantApprovalService
from .subscription_service import SubscriptionService, AdminSubscriptionService

plan_admin_router = APIRouter(prefix="/admin/plans", tags=["Admin - Plans"])
router = APIRouter(tags=["Tenants"])
admin_router = APIRouter(prefix="/admin/tenants", tags=["Admin - Tenants"])


# === Endpoints publicos ===

@router.get("/subscription-plans")
async def list_plans(
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(
        select(SubscriptionPlan)
        .where(SubscriptionPlan.is_active == True)
        .order_by(SubscriptionPlan.sort_order)
    )
    plans = result.scalars().all()
    return create_success_response(
        data=[PlanPublic.model_validate(p) for p in plans],
        message="Planes disponibles",
    )


# === Endpoints admin ===

@admin_router.get("/pending")
async def list_pending_tenants(
    admin: Administrator = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
):
    service = TenantApprovalService(session)
    pending = await service.list_pending()
    return create_success_response(
        data=pending,
        message=f"{len(pending)} solicitudes pendientes",
    )


@admin_router.get("/{tenant_id}")
async def get_tenant(
    tenant_id: int,
    admin: Administrator = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
):
    service = TenantApprovalService(session)
    tenant = await service.get_tenant_by_id(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    return create_success_response(
        data={
            "id": tenant.id,
            "workshop_id": tenant.workshop_id,
            "legal_name": tenant.legal_name,
            "nit": tenant.nit,
            "slug": tenant.slug,
            "business_type": tenant.business_type,
            "status": tenant.status,
            "rejection_reason": tenant.rejection_reason,
            "reviewed_by": tenant.reviewed_by,
            "reviewed_at": tenant.reviewed_at.isoformat() if tenant.reviewed_at else None,
            "created_at": tenant.created_at.isoformat(),
        },
        message="Detalle del tenant",
    )


@admin_router.post("/{tenant_id}/approve")
async def approve_tenant(
    tenant_id: int,
    body: ApproveTenantRequest = ApproveTenantRequest(),
    admin: Administrator = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
):
    service = TenantApprovalService(session)
    tenant = await service.approve(tenant_id, admin, body.plan_id)
    return create_success_response(
        data={"tenant_id": tenant.id, "status": tenant.status},
        message="Taller aprobado exitosamente. Las funcionalidades estan ahora disponibles.",
    )


@admin_router.post("/{tenant_id}/reject")
async def reject_tenant(
    tenant_id: int,
    body: RejectTenantRequest,
    admin: Administrator = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
):
    service = TenantApprovalService(session)
    await service.reject(tenant_id, admin, body.rejection_reason)
    return create_success_response(
        message="Solicitud rechazada. Se ha notificado al taller.",
    )


@admin_router.get("")
async def list_all_tenants(
    status: str | None = None,
    admin: Administrator = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
):
    service = TenantApprovalService(session)
    tenants = await service.list_tenants(status)
    return create_success_response(
        data=[
            {
                "id": t.id,
                "workshop_id": t.workshop_id,
                "legal_name": t.legal_name,
                "nit": t.nit,
                "status": t.status,
                "created_at": t.created_at.isoformat(),
            }
            for t in tenants
        ],
        message="Lista de tenants",
    )


@admin_router.post("/{tenant_id}/suspend")
async def suspend_tenant(
    tenant_id: int,
    admin: Administrator = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
):
    service = TenantApprovalService(session)
    tenant = await service.suspend_tenant(tenant_id, admin.id, "Suspendido por administrador")
    return create_success_response(
        data={"tenant_id": tenant.id, "status": tenant.status},
        message="Tenant suspendido",
    )


@admin_router.post("/{tenant_id}/reactivate")
async def reactivate_tenant(
    tenant_id: int,
    admin: Administrator = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
):
    service = TenantApprovalService(session)
    tenant = await service.reactivate_tenant(tenant_id, admin.id)
    return create_success_response(
        data={"tenant_id": tenant.id, "status": tenant.status},
        message="Tenant reactivado",
    )


# === Endpoints de suscripcion (Workshop) ===

workshop_sub_router = APIRouter(prefix="/workshop/subscription", tags=["Workshop - Subscription"])


@workshop_sub_router.get("")
async def get_my_subscription(
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session),
):
    service = SubscriptionService(session)
    sub = await service.get_my_subscription(ctx.tenant_id)
    if not sub:
        return create_success_response(data=None, message="No tienes suscripcion activa")
    return create_success_response(data=sub, message="Suscripcion actual")


@workshop_sub_router.get("/plans")
async def list_plans_workshop(session: AsyncSession = Depends(get_db_session)):
    service = SubscriptionService(session)
    plans = await service.list_plans()
    return create_success_response(data=plans, message="Planes disponibles")


@workshop_sub_router.get("/invoices")
async def get_invoices(
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session),
):
    service = SubscriptionService(session)
    invoices = await service.get_invoices(ctx.tenant_id)
    return create_success_response(data=invoices, message="Facturas")


@workshop_sub_router.post("/subscribe")
async def subscribe_plan(
    plan_id: int,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session),
):
    from app.models.tenant import Tenant
    from .stripe_service import StripeSubscriptionService

    service = SubscriptionService(session)
    plan = await session.get(SubscriptionPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan no encontrado")

    if plan.price == 0:
        sub = await service.subscribe_free_plan(ctx.tenant_id, plan_id)
        return create_success_response(
            data={"status": "active", "plan": plan.name},
            message="Plan basico activado"
        )

    tenant = await session.get(Tenant, ctx.tenant_id)
    stripe_svc = StripeSubscriptionService(session)
    url = await stripe_svc.create_checkout_session(tenant, plan, "workshop@email.com")
    return create_success_response(
        data={"checkout_url": url},
        message="Redirigiendo a Stripe Checkout"
    )


@workshop_sub_router.post("/change-plan")
async def change_plan(
    plan_id: int,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session),
):
    service = SubscriptionService(session)
    result = await service.change_plan(ctx.tenant_id, plan_id)
    return create_success_response(data=result, message=result.get("message", "Plan cambiado"))


@workshop_sub_router.post("/cancel")
async def cancel_subscription(
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session),
):
    service = SubscriptionService(session)
    result = await service.cancel_subscription(ctx.tenant_id)
    return create_success_response(data=result, message="Suscripcion cancelada")


@workshop_sub_router.post("/reactivate")
async def reactivate_subscription(
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session),
):
    service = SubscriptionService(session)
    result = await service.reactivate_subscription(ctx.tenant_id)
    return create_success_response(data=result, message="Suscripcion reactivada")


@workshop_sub_router.post("/apply-pending-changes")
async def apply_pending_changes(
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session),
):
    service = SubscriptionService(session)
    result = await service.apply_pending_changes(ctx.tenant_id)
    return create_success_response(data=result, message=result.get("message", "OK"))


@workshop_sub_router.post("/verify-payment")
async def verify_payment(
    ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
):
    from app.models.tenant_subscription import TenantSubscription
    from app.models.subscription_invoice import SubscriptionInvoice
    import stripe as _stripe
    from datetime import UTC, datetime
    from app.core.config import get_settings

    _stripe.api_key = get_settings().stripe_secret_key

    result = await session.execute(
        select(TenantSubscription).where(
            TenantSubscription.tenant_id == ctx.tenant_id,
        ).order_by(TenantSubscription.created_at.desc()).limit(1)
    )
    sub = result.scalar_one_or_none()

    if not sub:
        svc = SubscriptionService(session)
        data = await svc.get_my_subscription(ctx.tenant_id)
        return create_success_response(data=data, message="Sin suscripcion")

    stripe_sub = None

    if sub.provider_subscription_id:
        try:
            stripe_sub = _stripe.Subscription.retrieve(sub.provider_subscription_id)
        except Exception:
            pass

    if not stripe_sub and sub.provider_customer_id:
        try:
            subs = _stripe.Subscription.list(customer=sub.provider_customer_id, limit=1, status='active')
            if subs.data:
                stripe_sub = subs.data[0]
        except Exception:
            pass

    if not stripe_sub and sub.provider_customer_id:
        try:
            subs = _stripe.Subscription.list(customer=sub.provider_customer_id, limit=1, status='trialing')
            if subs.data:
                stripe_sub = subs.data[0]
        except Exception:
            pass

    if stripe_sub and stripe_sub.status in ('active', 'trialing', 'past_due'):
        sub.status = stripe_sub.status
        sub.pending_plan_id = None
        sub.provider_subscription_id = stripe_sub.id
        sub.current_period_start = datetime.fromtimestamp(stripe_sub.current_period_start, tz=UTC)
        sub.current_period_end = datetime.fromtimestamp(stripe_sub.current_period_end, tz=UTC)
        sub.payment_provider = "stripe"

        if stripe_sub.get('items', {}).get('data'):
            price_id = stripe_sub['items']['data'][0].get('price', {}).get('id')
            if price_id:
                plan_result = await session.execute(
                    select(SubscriptionPlan).where(SubscriptionPlan.stripe_price_id == price_id)
                )
                plan = plan_result.scalar_one_or_none()
                if plan:
                    sub.plan_id = plan.id

        existing_inv = await session.scalar(
            select(SubscriptionInvoice).where(
                SubscriptionInvoice.tenant_id == ctx.tenant_id,
                SubscriptionInvoice.stripe_invoice_id == stripe_sub.get('latest_invoice')
            )
        )
        if not existing_inv and stripe_sub.get('latest_invoice'):
            try:
                inv = _stripe.Invoice.retrieve(stripe_sub.latest_invoice)
                if inv.status == 'paid':
                    session.add(SubscriptionInvoice(
                        tenant_id=ctx.tenant_id,
                        subscription_id=sub.id,
                        amount=float(inv.amount_paid) / 100,
                        currency=inv.currency or 'usd',
                        status='paid',
                        stripe_invoice_id=inv.id,
                        stripe_payment_intent_id=inv.payment_intent,
                        invoice_url=inv.hosted_invoice_url,
                        paid_at=datetime.now(UTC),
                    ))
            except Exception:
                pass

        # Fallback: query Stripe invoices directly for this subscription
        try:
            stripe_invoices = _stripe.Invoice.list(
                subscription=stripe_sub.id,
                status='paid',
                limit=10,
            )
            for stripe_inv in stripe_invoices.data:
                already_exists = await session.scalar(
                    select(SubscriptionInvoice).where(
                        SubscriptionInvoice.stripe_invoice_id == stripe_inv.id
                    )
                )
                if not already_exists:
                    session.add(SubscriptionInvoice(
                        tenant_id=ctx.tenant_id,
                        subscription_id=sub.id,
                        amount=float(stripe_inv.amount_paid) / 100,
                        currency=stripe_inv.currency or 'usd',
                        status='paid',
                        stripe_invoice_id=stripe_inv.id,
                        stripe_payment_intent_id=stripe_inv.payment_intent,
                        invoice_url=stripe_inv.hosted_invoice_url,
                        paid_at=datetime.fromtimestamp(stripe_inv.status_transitions.paid_at, tz=UTC)
                        if stripe_inv.status_transitions.paid_at else datetime.now(UTC),
                    ))
        except Exception:
            pass

        await session.commit()

    svc = SubscriptionService(session)
    data = await svc.get_my_subscription(ctx.tenant_id)
    return create_success_response(data=data, message="Suscripcion actual")


# === Endpoints admin suscripcion ===

admin_sub_router = APIRouter(prefix="/admin/subscriptions", tags=["Admin - Subscriptions"])


@admin_sub_router.get("")
async def list_subscriptions(
    status: str | None = None,
    admin: Administrator = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
):
    service = AdminSubscriptionService(session)
    subs = await service.list_all(status)
    return create_success_response(data=subs, message="Suscripciones")


@admin_sub_router.post("/{subscription_id}/suspend")
async def admin_suspend_sub(
    subscription_id: int,
    admin: Administrator = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
):
    service = AdminSubscriptionService(session)
    result = await service.suspend(subscription_id, admin.id, "Suspendido por administrador")
    return create_success_response(data=result, message="Suscripcion suspendida")


@admin_sub_router.post("/{subscription_id}/reactivate")
async def admin_reactivate_sub(
    subscription_id: int,
    admin: Administrator = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
):
    service = AdminSubscriptionService(session)
    result = await service.reactivate(subscription_id, admin.id)
    return create_success_response(data=result, message="Suscripcion reactivada")


# === CRUD Planes Admin ===

from pydantic import BaseModel as PydanticModel


class PlanCreateRequest(PydanticModel):
    code: str
    name: str
    description: str = ""
    price: float = 0
    billing_period: str = "monthly"
    max_technicians: int = 5
    max_services: int = 20
    enable_kpis: bool = False
    enable_reports: bool = False
    enable_realtime_tracking: bool = False
    enable_quotes: bool = False
    enable_voice_reports: bool = False
    enable_priority_support: bool = False
    sort_order: int = 0


class PlanUpdateRequest(PydanticModel):
    name: str | None = None
    description: str | None = None
    price: float | None = None
    billing_period: str | None = None
    max_technicians: int | None = None
    max_services: int | None = None
    enable_kpis: bool | None = None
    enable_reports: bool | None = None
    enable_realtime_tracking: bool | None = None
    enable_quotes: bool | None = None
    enable_voice_reports: bool | None = None
    enable_priority_support: bool | None = None
    sort_order: int | None = None


@plan_admin_router.get("")
async def list_all_plans(
    admin: Administrator = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(
        select(SubscriptionPlan).order_by(SubscriptionPlan.sort_order)
    )
    plans = result.scalars().all()
    return create_success_response(
        data=[{
            "id": p.id, "code": p.code, "name": p.name, "description": p.description,
            "price": float(p.price), "billing_period": p.billing_period,
            "max_technicians": p.max_technicians, "max_services": p.max_services,
            "enable_kpis": p.enable_kpis, "enable_reports": p.enable_reports,
            "enable_realtime_tracking": p.enable_realtime_tracking,
            "enable_quotes": p.enable_quotes, "enable_voice_reports": p.enable_voice_reports,
            "enable_priority_support": p.enable_priority_support,
            "enable_api_access": p.enable_api_access, "enable_white_label": p.enable_white_label,
            "sort_order": p.sort_order, "is_active": p.is_active,
        } for p in plans],
        message="Planes",
    )


@plan_admin_router.post("", status_code=201)
async def create_plan(
    body: PlanCreateRequest,
    admin: Administrator = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
):
    existing = await session.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == body.code))
    if existing:
        raise HTTPException(409, "Ya existe un plan con ese codigo")
    plan = SubscriptionPlan(
        code=body.code, name=body.name, description=body.description or None,
        price=body.price, billing_period=body.billing_period,
        max_technicians=body.max_technicians, max_services=body.max_services,
        enable_kpis=body.enable_kpis, enable_reports=body.enable_reports,
        enable_realtime_tracking=body.enable_realtime_tracking, enable_quotes=body.enable_quotes,
        enable_voice_reports=body.enable_voice_reports, enable_priority_support=body.enable_priority_support,
        sort_order=body.sort_order, is_active=True,
    )
    session.add(plan)
    await session.commit()
    return create_success_response(data={"id": plan.id, "code": plan.code}, message="Plan creado", status_code=201)


@plan_admin_router.put("/{plan_id}")
async def update_plan(
    plan_id: int,
    body: PlanUpdateRequest,
    admin: Administrator = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
):
    plan = await session.get(SubscriptionPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan no encontrado")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)
    await session.commit()
    await session.refresh(plan)
    return create_success_response(data={"id": plan.id, "name": plan.name}, message="Plan actualizado")


@plan_admin_router.post("/{plan_id}/toggle")
async def toggle_plan(
    plan_id: int,
    admin: Administrator = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
):
    plan = await session.get(SubscriptionPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan no encontrado")
    plan.is_active = not plan.is_active
    await session.commit()
    return create_success_response(
        data={"id": plan.id, "is_active": plan.is_active},
        message="Plan activado" if plan.is_active else "Plan desactivado",
    )
