import json
import re
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import (
    EmailAlreadyExistsException,
    create_access_token,
    hash_password,
    validate_password_strength,
    get_logger,
    get_settings,
)
from app.core.constants import UserType
from app.core.exceptions import AppException
from app.models.tenant import Tenant
from app.models.subscription_plan import SubscriptionPlan
from app.models.tenant_subscription import TenantSubscription
from app.models.user import User
from app.models.workshop import Workshop
from app.models.audit_log import AuditLog
from app.models.administrator import Administrator
from app.modules.auth.services import _resolve_tenant_claims

from .schemas import WorkshopTenantRegistrationRequest

logger = get_logger(__name__)
settings = get_settings()


def generate_slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]", "-", name.lower().strip())[:60]
    suffix = secrets.token_hex(3)[:6]
    return f"{base}-{suffix}"


class TenantRegistrationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def email_exists(self, email: str) -> bool:
        result = await self.session.execute(
            select(User.id).where(User.email == email.strip().lower())
        )
        return result.scalar_one_or_none() is not None

    async def nit_exists(self, nit: str) -> bool:
        result = await self.session.execute(
            select(Tenant.id).where(Tenant.nit == nit.strip())
        )
        return result.scalar_one_or_none() is not None

    async def register_workshop(
        self, request: WorkshopTenantRegistrationRequest
    ) -> dict:
        await self.session.rollback()

        email = request.email.strip().lower()
        nit = request.nit.strip()

        if await self.email_exists(email):
            raise EmailAlreadyExistsException(email)
        if await self.nit_exists(nit):
            raise AppException(
                message="El NIT ya esta registrado",
                code="NIT_EXISTS",
                status_code=409,
            )

        is_valid, error = validate_password_strength(request.password)
        if not is_valid:
            raise AppException(message=error, code="WEAK_PASSWORD", status_code=400)

        password_hash = hash_password(request.password)
        plan_id = request.plan_id or settings.default_plan_id
        slug = generate_slug(request.workshop_name)
        now = datetime.now(UTC)

        user = Workshop(
            first_name=request.first_name,
            last_name=request.last_name,
            email=email,
            phone=request.phone,
            password_hash=password_hash,
            user_type="workshop",
            is_active=True,
            email_verified=False,
            workshop_name=request.workshop_name,
            owner_name=f"{request.first_name} {request.last_name}",
            description=request.description,
            latitude=request.latitude,
            longitude=request.longitude,
            address=request.address,
            coverage_radius_km=request.coverage_radius_km,
            nit=nit,
            is_available=True,
            is_verified=False,
        )
        self.session.add(user)
        await self.session.flush()

        tenant = Tenant(
            workshop_id=user.id,
            owner_user_id=user.id,
            legal_name=request.legal_name,
            nit=nit,
            slug=slug,
            business_type=request.business_type,
            status="pending",
        )
        self.session.add(tenant)
        await self.session.flush()

        user.tenant_id = tenant.id

        subscription = TenantSubscription(
            tenant_id=tenant.id,
            plan_id=plan_id,
            status="active",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        self.session.add(subscription)

        self.session.add(AuditLog(
            user_id=user.id,
            tenant_id=tenant.id,
            action="tenant_registered",
            resource_type="tenant",
            resource_id=tenant.id,
            ip_address="system",
        ))

        await self.session.commit()

        additional_claims = await _resolve_tenant_claims(self.session, user)
        access_token, expires_at, jti = create_access_token(
            subject=str(user.id),
            email=user.email,
            user_type=user.user_type,
            additional_claims=additional_claims,
        )

        tenant_status = additional_claims.get("tenant_status", "pending")
        checkout_url = None

        plan = await self.session.get(SubscriptionPlan, plan_id)
        if plan and plan.price > 0:
            from .stripe_service import StripeSubscriptionService
            stripe_svc = StripeSubscriptionService(self.session)
            checkout_url = await stripe_svc.create_checkout_session(tenant, plan, email)

        try:
            from app.modules.notifications.service import NotificationService
            await NotificationService.notify_admins_new_tenant(
                self.session, tenant, request.workshop_name, email
            )
        except Exception:
            logger.exception("Failed to notify admins of new tenant registration")

        return {
            "tenant_id": tenant.id,
            "status": tenant_status,
            "workshop_id": user.id,
            "legal_name": tenant.legal_name,
            "nit": tenant.nit,
            "access_token": access_token,
            "token_type": "bearer",
            "checkout_url": checkout_url,
        }


class TenantApprovalService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_pending(self) -> list[dict]:
        from sqlalchemy.orm import aliased
        Owner = aliased(User)

        stmt = (
            select(
                Tenant.id.label("tenant_id"),
                Tenant.legal_name,
                Tenant.nit,
                Tenant.business_type,
                Tenant.status,
                Tenant.created_at,
                Workshop.workshop_name,
                Workshop.owner_name,
                Owner.email.label("owner_email"),
                Workshop.address,
                SubscriptionPlan.name.label("plan_name"),
            )
            .join(Workshop, Tenant.workshop_id == Workshop.id)
            .join(Owner, Tenant.owner_user_id == Owner.id)
            .outerjoin(
                TenantSubscription,
                TenantSubscription.tenant_id == Tenant.id,
            )
            .outerjoin(
                SubscriptionPlan,
                TenantSubscription.plan_id == SubscriptionPlan.id,
            )
            .where(Tenant.status == "pending")
            .order_by(Tenant.created_at.desc())
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        return [dict(r._mapping) for r in rows]

    async def approve(
        self, tenant_id: int, admin_user: Administrator, plan_id: int | None = None
    ) -> Tenant:
        tenant = await self.session.get(Tenant, tenant_id)
        if not tenant or tenant.status != "pending":
            raise AppException(
                message="Solicitud no encontrada o ya procesada",
                code="TENANT_NOT_PENDING",
                status_code=404,
            )

        tenant.status = "active"
        tenant.reviewed_by = admin_user.id
        tenant.reviewed_at = datetime.now(UTC)

        if plan_id:
            sub = await self.session.scalar(
                select(TenantSubscription).where(
                    TenantSubscription.tenant_id == tenant.id
                )
            )
            if sub:
                sub.plan_id = plan_id

        self.session.add(AuditLog(
            user_id=admin_user.id,
            tenant_id=tenant.id,
            action="tenant_approved",
            resource_type="tenant",
            resource_id=tenant.id,
            ip_address="system",
            details=json.dumps({"plan_id": plan_id} if plan_id else {}),
        ))

        await self.session.commit()

        try:
            user = await self.session.get(User, tenant.owner_user_id)
            if user:
                from app.modules.notifications.service import NotificationService
                await NotificationService.notify_tenant_approved(
                    self.session, tenant, user.email
                )
        except Exception:
            logger.exception("Failed to send approval notification")

        return tenant

    async def reject(
        self, tenant_id: int, admin_user: Administrator, reason: str
    ) -> Tenant:
        tenant = await self.session.get(Tenant, tenant_id)
        if not tenant or tenant.status != "pending":
            raise AppException(
                message="Solicitud no encontrada o ya procesada",
                code="TENANT_NOT_PENDING",
                status_code=404,
            )

        tenant.status = "rejected"
        tenant.rejection_reason = reason
        tenant.reviewed_by = admin_user.id
        tenant.reviewed_at = datetime.now(UTC)

        user = await self.session.get(User, tenant.owner_user_id)
        if user:
            user.is_active = False

        self.session.add(AuditLog(
            user_id=admin_user.id,
            tenant_id=tenant.id,
            action="tenant_rejected",
            resource_type="tenant",
            resource_id=tenant.id,
            ip_address="system",
            details=json.dumps({"reason": reason}),
        ))

        await self.session.commit()

        try:
            if user:
                from app.modules.notifications.service import NotificationService
                await NotificationService.notify_tenant_rejected(
                    self.session, tenant, user.email, reason
                )
        except Exception:
            logger.exception("Failed to send rejection notification")

        return tenant

    async def get_tenant_by_id(self, tenant_id: int) -> Tenant | None:
        return await self.session.get(Tenant, tenant_id)

    async def list_tenants(self, status: str | None = None) -> list[Tenant]:
        stmt = select(Tenant)
        if status:
            stmt = stmt.where(Tenant.status == status)
        stmt = stmt.order_by(Tenant.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def suspend_tenant(self, tenant_id: int, admin_user: int, reason: str) -> Tenant:
        tenant = await self.session.get(Tenant, tenant_id)
        if not tenant:
            raise AppException(message="Tenant no encontrado", code="TENANT_NOT_FOUND", status_code=404)
        tenant.status = "suspended"
        tenant.reviewed_by = admin_user
        tenant.reviewed_at = datetime.now(UTC)
        await self.session.commit()
        return tenant

    async def reactivate_tenant(self, tenant_id: int, admin_user: int) -> Tenant:
        tenant = await self.session.get(Tenant, tenant_id)
        if not tenant:
            raise AppException(message="Tenant no encontrado", code="TENANT_NOT_FOUND", status_code=404)
        tenant.status = "active"
        tenant.rejection_reason = None
        tenant.reviewed_by = admin_user
        tenant.reviewed_at = datetime.now(UTC)

        user = await self.session.get(User, tenant.owner_user_id)
        if user:
            user.is_active = True

        await self.session.commit()
        return tenant
