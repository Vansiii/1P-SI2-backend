import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_logger, get_settings
from app.core.exceptions import AppException
from app.models.subscription_plan import SubscriptionPlan
from app.models.tenant_subscription import TenantSubscription
from app.models.subscription_invoice import SubscriptionInvoice
from app.models.tenant import Tenant
from app.models.workshop import Workshop
from app.models.audit_log import AuditLog

logger = get_logger(__name__)
settings = get_settings()

VALID_ACCESS_STATUSES = {'active', 'trialing', 'past_due', 'pending_downgrade', 'pending_cancellation'}
CURRENT_SUB_STATUSES = {'active', 'trialing', 'past_due', 'pending_downgrade', 'pending_cancellation'}


class SubscriptionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_my_subscription(self, tenant_id: int) -> dict | None:
        result = await self.session.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == tenant_id,
                TenantSubscription.status.in_(CURRENT_SUB_STATUSES),
            ).order_by(TenantSubscription.created_at.desc()).limit(1)
        )
        sub = result.scalar_one_or_none()
        if not sub:
            return None

        plan = await self.session.get(SubscriptionPlan, sub.plan_id)
        response = self._build_subscription_dict(sub, plan)

        if sub.pending_plan_id:
            pending_plan = await self.session.get(SubscriptionPlan, sub.pending_plan_id)
            if pending_plan:
                response['pending_plan'] = self._build_plan_dict(pending_plan)

        return response

    async def list_plans(self) -> list:
        result = await self.session.execute(
            select(SubscriptionPlan)
            .where(SubscriptionPlan.is_active == True)
            .order_by(SubscriptionPlan.sort_order)
        )
        plans = result.scalars().all()
        return [self._build_plan_dict(p) for p in plans]

    async def subscribe_free_plan(self, tenant_id: int, plan_id: int) -> TenantSubscription:
        plan = await self.session.get(SubscriptionPlan, plan_id)
        if not plan:
            raise AppException("Plan no encontrado", "PLAN_NOT_FOUND", 404)
        if plan.price > 0:
            raise AppException("Este plan requiere pago", "PLAN_REQUIRES_PAYMENT", 400)

        self._ensure_no_duplicate_active(tenant_id)
        return await self._activate_subscription(tenant_id, plan)

    async def _ensure_no_duplicate_active(self, tenant_id: int) -> None:
        result = await self.session.execute(
            select(func.count(TenantSubscription.id)).where(
                TenantSubscription.tenant_id == tenant_id,
                TenantSubscription.status.in_(CURRENT_SUB_STATUSES),
            )
        )
        count = result.scalar()
        if count and count > 1:
            raise AppException(
                "Inconsistencia: el tenant tiene multiples suscripciones activas. Contacta al administrador.",
                "DUPLICATE_ACTIVE_SUB",
                409,
            )

    async def _activate_subscription(
        self, tenant_id: int, plan: SubscriptionPlan
    ) -> TenantSubscription:
        result = await self.session.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == tenant_id
            ).order_by(TenantSubscription.created_at.desc()).limit(1)
        )
        current = result.scalar_one_or_none()

        previous_status = None
        previous_plan_id = None
        if current:
            previous_status = current.status
            previous_plan_id = current.plan_id
            current.status = "canceled"
            current.cancel_at_period_end = False

        now = datetime.now(UTC)
        sub = TenantSubscription(
            tenant_id=tenant_id,
            plan_id=plan.id,
            status="active",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            payment_provider="stripe" if plan.price > 0 else "free",
        )
        self.session.add(sub)
        await self.session.commit()
        await self.session.refresh(sub)

        self._audit(
            tenant_id=tenant_id,
            subscription_id=sub.id,
            action="SUBSCRIPTION_CREATED",
            new_plan_id=plan.id,
            new_status="active",
            user_id=None,
            details={"previous": {"status": previous_status, "plan_id": previous_plan_id}},
        )

        return sub

    async def change_plan(self, tenant_id: int, new_plan_id: int) -> dict:
        new_plan = await self.session.get(SubscriptionPlan, new_plan_id)
        if not new_plan:
            raise AppException("Plan no encontrado", "PLAN_NOT_FOUND", 404)

        result = await self.session.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == tenant_id,
                TenantSubscription.status.in_(CURRENT_SUB_STATUSES),
            ).order_by(TenantSubscription.created_at.desc()).limit(1)
        )
        sub = result.scalar_one_or_none()
        if not sub:
            raise AppException("No tienes suscripcion activa", "NO_ACTIVE_SUB", 400)

        if sub.status == "pending_cancellation":
            raise AppException(
                "No puedes cambiar de plan con una cancelacion pendiente. "
                "Reactiva tu suscripcion primero.",
                "PENDING_CANCELLATION",
                409,
            )

        current_plan = await self.session.get(SubscriptionPlan, sub.plan_id)
        current_price = current_plan.price if current_plan else 0
        new_price = new_plan.price

        if current_plan and current_plan.id == new_plan.id:
            raise AppException("Ya tienes este plan activo", "SAME_PLAN", 409)

        is_upgrade = new_price > current_price
        is_downgrade = new_price < current_price

        old_plan_id = sub.plan_id

        if is_upgrade:
            return await self._handle_upgrade(sub, new_plan, tenant_id, old_plan_id)

        elif is_downgrade:
            return await self._handle_downgrade(sub, new_plan, tenant_id, old_plan_id)

        else:
            return await self._handle_same_price(sub, new_plan, tenant_id, old_plan_id)

    async def _handle_upgrade(
        self, sub: TenantSubscription, new_plan: SubscriptionPlan,
        tenant_id: int, old_plan_id: int,
    ) -> dict:
        from .stripe_service import StripeSubscriptionService
        from app.models.user import User

        tenant = await self.session.get(Tenant, tenant_id)
        user = await self.session.get(User, tenant.owner_user_id) if tenant else None

        stripe_svc = StripeSubscriptionService(self.session)
        url = await stripe_svc.create_checkout_session(
            tenant, new_plan, user.email if user else "workshop@email.com"
        )

        self._audit(
            tenant_id=tenant_id,
            subscription_id=sub.id,
            action="PLAN_UPGRADED",
            old_plan_id=old_plan_id,
            new_plan_id=new_plan.id,
            new_status=sub.status,
            details={"redirected_to_stripe": True},
        )

        return {
            "url": url,
            "message": "Redirigiendo a Stripe para completar el cambio de plan",
        }

    async def _handle_downgrade(
        self, sub: TenantSubscription, new_plan: SubscriptionPlan,
        tenant_id: int, old_plan_id: int,
    ) -> dict:
        if sub.status == "pending_downgrade":
            sub.pending_plan_id = new_plan.id
            changed = "actualizado"
        else:
            sub.status = "pending_downgrade"
            sub.pending_plan_id = new_plan.id
            changed = "programado"

        await self.session.commit()

        self._audit(
            tenant_id=tenant_id,
            subscription_id=sub.id,
            action="PLAN_DOWNGRADE_SCHEDULED",
            old_plan_id=old_plan_id,
            new_plan_id=new_plan.id,
            new_status=sub.status,
        )

        return {
            "url": None,
            "message": f"Cambio a {new_plan.name} {changed}. Se aplicara al finalizar el periodo actual ({sub.current_period_end.isoformat()}).",
            "pending_plan_id": new_plan.id,
            "status": sub.status,
        }

    async def _handle_same_price(
        self, sub: TenantSubscription, new_plan: SubscriptionPlan,
        tenant_id: int, old_plan_id: int,
    ) -> dict:
        if sub.status == "pending_downgrade":
            sub.pending_plan_id = new_plan.id
            await self.session.commit()
            self._audit(tenant_id, sub.id, "PENDING_DOWNGRADE_UPDATED",
                        old_plan_id=old_plan_id, new_plan_id=new_plan.id,
                        new_status=sub.status)
            return {
                "url": None,
                "message": f"Cambio pendiente actualizado a {new_plan.name}. Se aplicara al finalizar el periodo.",
                "pending_plan_id": new_plan.id,
                "status": sub.status,
            }

        if sub.provider_subscription_id and sub.payment_provider == "stripe":
            from .stripe_service import StripeSubscriptionService
            stripe_svc = StripeSubscriptionService(self.session)
            await stripe_svc.change_stripe_subscription(sub, new_plan)

        sub.plan_id = new_plan.id
        sub.pending_plan_id = None

        if new_plan.price == 0:
            sub.payment_provider = "free"
            sub.provider_subscription_id = None
            sub.provider_customer_id = None

        await self.session.commit()

        self._audit(
            tenant_id=tenant_id,
            subscription_id=sub.id,
            action="PLAN_CHANGED",
            old_plan_id=old_plan_id,
            new_plan_id=new_plan.id,
            new_status=sub.status,
        )

        return {
            "url": None,
            "message": f"Plan cambiado a {new_plan.name}",
        }

    async def cancel_subscription(self, tenant_id: int) -> dict:
        result = await self.session.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == tenant_id,
                TenantSubscription.status.in_(CURRENT_SUB_STATUSES),
            ).order_by(TenantSubscription.created_at.desc()).limit(1)
        )
        sub = result.scalar_one_or_none()
        if not sub:
            raise AppException("No tienes suscripcion activa", "NO_ACTIVE_SUB", 400)

        if sub.status == "pending_cancellation":
            raise AppException(
                "Tu suscripcion ya esta pendiente de cancelacion.",
                "ALREADY_PENDING_CANCEL",
                409,
            )

        old_status = sub.status

        if sub.payment_provider == "stripe" and sub.provider_subscription_id:
            from .stripe_service import StripeSubscriptionService
            stripe_svc = StripeSubscriptionService(self.session)
            await stripe_svc.cancel_stripe_subscription(sub.provider_subscription_id)

        sub.status = "pending_cancellation"
        sub.cancel_at_period_end = True
        sub.pending_plan_id = None
        await self.session.commit()

        self._audit(
            tenant_id=tenant_id,
            subscription_id=sub.id,
            action="SUBSCRIPTION_CANCELLATION_SCHEDULED",
            old_status=old_status,
            new_status=sub.status,
            details={"period_end": sub.current_period_end.isoformat()},
        )

        return {
            "message": "Suscripcion cancelada. Seguira activa hasta el fin del periodo.",
            "period_end": sub.current_period_end.isoformat(),
            "status": sub.status,
        }

    async def reactivate_subscription(self, tenant_id: int) -> dict:
        result = await self.session.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == tenant_id,
                TenantSubscription.status == "pending_cancellation",
                TenantSubscription.current_period_end > datetime.now(UTC),
            ).order_by(TenantSubscription.created_at.desc()).limit(1)
        )
        sub = result.scalar_one_or_none()
        if not sub:
            raise AppException(
                "No hay suscripcion pendiente de cancelacion para reactivar.",
                "NO_CANCELED_SUB",
                400,
            )

        old_status = sub.status

        if sub.payment_provider == "stripe" and sub.provider_subscription_id:
            from .stripe_service import StripeSubscriptionService
            stripe_svc = StripeSubscriptionService(self.session)
            await stripe_svc.reactivate_stripe_subscription(sub.provider_subscription_id)

        sub.status = "active"
        sub.cancel_at_period_end = False
        sub.pending_plan_id = None
        await self.session.commit()

        self._audit(
            tenant_id=tenant_id,
            subscription_id=sub.id,
            action="SUBSCRIPTION_REACTIVATED",
            old_status=old_status,
            new_status=sub.status,
        )

        return {
            "message": "Suscripcion reactivada",
            "status": sub.status,
        }

    async def apply_pending_changes(self, tenant_id: int) -> dict:
        result = await self.session.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == tenant_id,
                TenantSubscription.status.in_(['pending_downgrade', 'pending_cancellation']),
                TenantSubscription.current_period_end <= datetime.now(UTC),
            ).order_by(TenantSubscription.created_at.desc()).limit(1)
        )
        sub = result.scalar_one_or_none()
        if not sub:
            return {"applied": False, "message": "No hay cambios pendientes por aplicar"}

        old_status = sub.status
        old_plan_id = sub.plan_id

        if sub.status == "pending_downgrade":
            if sub.pending_plan_id:
                sub.plan_id = sub.pending_plan_id
                sub.pending_plan_id = None

                if sub.payment_provider == "stripe" and sub.provider_subscription_id:
                    try:
                        from .stripe_service import StripeSubscriptionService
                        svc = StripeSubscriptionService(self.session)
                        svc.cancel_stripe_subscription(sub.provider_subscription_id)
                        sub.payment_provider = "free"
                        sub.provider_subscription_id = None
                        sub.provider_customer_id = None
                    except Exception:
                        logger.exception("Failed to cancel Stripe during downgrade apply")

            sub.status = "active"
            sub.current_period_start = datetime.now(UTC)
            sub.current_period_end = datetime.now(UTC) + timedelta(days=30)
            await self.session.commit()

            self._audit(
                tenant_id=tenant_id,
                subscription_id=sub.id,
                action="PLAN_DOWNGRADE_APPLIED",
                old_status=old_status,
                new_status=sub.status,
                old_plan_id=old_plan_id,
                new_plan_id=sub.plan_id,
            )

            plan_name = (await self.session.get(SubscriptionPlan, sub.plan_id)).name
            return {
                "applied": True,
                "change": "downgrade",
                "message": f"Downgrade aplicado. Ahora tienes el plan {plan_name}.",
                "plan_id": sub.plan_id,
                "status": sub.status,
            }

        elif sub.status == "pending_cancellation":
            sub.status = "canceled"
            await self.session.commit()

            self._audit(
                tenant_id=tenant_id,
                subscription_id=sub.id,
                action="SUBSCRIPTION_CANCELLED",
                old_status=old_status,
                new_status=sub.status,
            )

            return {
                "applied": True,
                "change": "cancellation",
                "message": "Cancelacion aplicada. Tu suscripcion ahora esta cancelada.",
                "status": sub.status,
            }

    async def get_invoices(self, tenant_id: int) -> list:
        result = await self.session.execute(
            select(SubscriptionInvoice)
            .where(SubscriptionInvoice.tenant_id == tenant_id)
            .order_by(SubscriptionInvoice.created_at.desc())
        )
        invoices = result.scalars().all()
        return [
            {
                "id": inv.id,
                "amount": float(inv.amount),
                "currency": inv.currency,
                "status": inv.status,
                "paid_at": inv.paid_at.isoformat() if inv.paid_at else None,
                "invoice_url": inv.invoice_url,
                "created_at": inv.created_at.isoformat(),
            }
            for inv in invoices
        ]

    def _audit(
        self,
        tenant_id: int,
        subscription_id: int,
        action: str,
        old_plan_id: int | None = None,
        new_plan_id: int | None = None,
        old_status: str | None = None,
        new_status: str | None = None,
        user_id: int | None = None,
        details: dict | None = None,
    ) -> None:
        try:
            audit = AuditLog(
                user_id=user_id,
                tenant_id=tenant_id,
                action=action,
                resource_type="subscription",
                resource_id=subscription_id,
                ip_address="system",
                details=json.dumps({
                    "old_plan_id": old_plan_id,
                    "new_plan_id": new_plan_id,
                    "old_status": old_status,
                    "new_status": new_status,
                    **(details or {}),
                }),
            )
            self.session.add(audit)
        except Exception:
            logger.exception("Failed to write audit log")

    def _build_subscription_dict(self, sub, plan) -> dict:
        result = {
            "id": sub.id,
            "tenant_id": sub.tenant_id,
            "plan_id": sub.plan_id,
            "pending_plan_id": sub.pending_plan_id,
            "status": sub.status,
            "current_period_start": sub.current_period_start.isoformat(),
            "current_period_end": sub.current_period_end.isoformat(),
            "cancel_at_period_end": sub.cancel_at_period_end,
            "payment_provider": sub.payment_provider,
            "grace_until": sub.grace_until.isoformat() if sub.grace_until else None,
            "plan": self._build_plan_dict(plan),
        }
        return result

    def _build_plan_dict(self, p) -> dict:
        return {
            "id": p.id,
            "code": p.code,
            "name": p.name,
            "description": p.description,
            "price": float(p.price),
            "billing_period": p.billing_period,
            "max_technicians": p.max_technicians,
            "max_services": p.max_services,
            "enable_kpis": p.enable_kpis,
            "enable_reports": p.enable_reports,
            "enable_realtime_tracking": p.enable_realtime_tracking,
            "enable_quotes": p.enable_quotes,
            "enable_voice_reports": p.enable_voice_reports,
            "enable_priority_support": p.enable_priority_support,
        }


class AdminSubscriptionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(self, status: str | None = None) -> list:
        stmt = select(TenantSubscription)
        if status:
            stmt = stmt.where(TenantSubscription.status == status)
        stmt = stmt.order_by(TenantSubscription.created_at.desc()).limit(100)
        result = await self.session.execute(stmt)
        subs = result.scalars().all()
        return [
            {
                "id": s.id,
                "tenant_id": s.tenant_id,
                "plan_id": s.plan_id,
                "pending_plan_id": s.pending_plan_id,
                "status": s.status,
                "current_period_end": s.current_period_end.isoformat(),
                "cancel_at_period_end": s.cancel_at_period_end,
                "provider_subscription_id": s.provider_subscription_id,
            }
            for s in subs
        ]

    async def suspend(self, subscription_id: int, admin_id: int, reason: str) -> dict:
        sub = await self.session.get(TenantSubscription, subscription_id)
        if not sub:
            raise AppException("Suscripcion no encontrada", "SUB_NOT_FOUND", 404)

        old_status = sub.status
        sub.status = "suspended"
        sub.suspended_reason = reason
        sub.suspended_by = admin_id

        tenant = await self.session.get(Tenant, sub.tenant_id)
        if tenant:
            tenant.status = "suspended"

        if sub.provider_subscription_id:
            try:
                from .stripe_service import StripeSubscriptionService
                svc = StripeSubscriptionService(self.session)
                svc.cancel_stripe_subscription(sub.provider_subscription_id)
            except Exception:
                logger.exception("Failed to cancel Stripe subscription")

        self.session.add(AuditLog(
            user_id=admin_id,
            tenant_id=sub.tenant_id,
            action="SUBSCRIPTION_SUSPENDED",
            resource_type="subscription",
            resource_id=subscription_id,
            ip_address="system",
            details=json.dumps({"reason": reason, "old_status": old_status}),
        ))

        await self.session.commit()
        return {"message": "Suscripcion suspendida"}

    async def reactivate(self, subscription_id: int, admin_id: int) -> dict:
        sub = await self.session.get(TenantSubscription, subscription_id)
        if not sub:
            raise AppException("Suscripcion no encontrada", "SUB_NOT_FOUND", 404)

        old_status = sub.status
        sub.status = "active"
        sub.suspended_reason = None

        tenant = await self.session.get(Tenant, sub.tenant_id)
        if tenant:
            tenant.status = "active"

        self.session.add(AuditLog(
            user_id=admin_id,
            tenant_id=sub.tenant_id,
            action="SUBSCRIPTION_REACTIVATED",
            resource_type="subscription",
            resource_id=subscription_id,
            ip_address="system",
            details=json.dumps({"old_status": old_status}),
        ))

        await self.session.commit()
        return {"message": "Suscripcion reactivada"}
