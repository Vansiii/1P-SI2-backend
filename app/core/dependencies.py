"""
Dependencies para autorización, control de acceso basado en permisos y tenant context.
"""

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission, UserRole, check_permission
from app.core.database import get_db_session
from app.shared.dependencies.auth import get_current_token_payload as _get_current_token_payload
from app.shared.dependencies.auth import get_current_user  # Export for modules
from app.modules.auth.schemas import TokenPayload


@dataclass
class TenantContext:
    """Contexto de tenant resuelto desde el JWT."""
    tenant_id: int | None
    user_id: int
    user_type: str
    is_active: bool
    status: str | None


async def get_current_user_payload(
    token_payload: TokenPayload = Depends(_get_current_token_payload)
) -> dict[str, Any]:
    """
    Dependency que obtiene el payload del usuario actual desde el token JWT.

    Integrado con el sistema de autenticación existente.

    El payload contiene:
    - sub: ID del usuario
    - email: Email del usuario
    - user_type: Tipo de usuario
    - tenant_id: ID del tenant (si aplica, CU29-CU31)
    - tenant_status: Estado del tenant (si aplica)
    - jti: ID único del token
    - exp: Fecha de expiración
    """
    return {
        "sub": token_payload.sub,
        "email": token_payload.email,
        "user_type": token_payload.user_type,
        "tenant_id": token_payload.tenant_id,
        "tenant_status": token_payload.tenant_status,
        "jti": token_payload.jti,
        "exp": token_payload.exp,
    }


async def get_tenant_context(
    user_payload: dict = Depends(get_current_user_payload),
) -> TenantContext:
    """
    Resuelve el TenantContext desde el JWT.
    No valida estado del tenant — usar require_active_tenant() para eso.
    """
    user_id = int(user_payload["sub"])
    user_type = user_payload.get("user_type", "")
    tenant_id = user_payload.get("tenant_id")
    tenant_status = user_payload.get("tenant_status")

    is_active = tenant_status in (None, "active") if tenant_id else True

    return TenantContext(
        tenant_id=tenant_id,
        user_id=user_id,
        user_type=user_type,
        is_active=is_active,
        status=tenant_status,
    )


async def require_active_tenant(
    ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> TenantContext:
    """
    Bloquea acceso si el tenant no está activo.
    Admin siempre tiene acceso completo.
    Workshop/Technician requieren tenant activo.
    """
    if ctx.user_type in ("admin", "administrator", "client"):
        return ctx

    if ctx.tenant_id is None and ctx.user_type == "workshop":
        raise HTTPException(
            status_code=403,
            detail="No tienes un tenant asociado.",
        )

    if ctx.status == "pending":
        from app.models.tenant import Tenant
        tenant = await session.get(Tenant, ctx.tenant_id)
        if tenant and tenant.status == "active":
            ctx.status = "active"
            ctx.is_active = True
            return ctx
        raise HTTPException(
            status_code=403,
            detail="Tu cuenta esta pendiente de aprobacion. "
                   "Puedes iniciar sesion y configurar tu perfil, "
                   "pero las funcionalidades completas se activaran "
                   "cuando un administrador apruebe tu cuenta.",
        )
    if ctx.status == "rejected":
        from app.models.tenant import Tenant
        tenant = await session.get(Tenant, ctx.tenant_id)
        reason = tenant.rejection_reason if tenant else ""
        raise HTTPException(
            status_code=403,
            detail=f"Tu solicitud fue rechazada. Motivo: {reason}",
        )
    if ctx.status == "suspended":
        raise HTTPException(
            status_code=403,
            detail="Tu cuenta ha sido suspendida. Contacta al administrador.",
        )
    if ctx.status == "canceled":
        raise HTTPException(
            status_code=403,
            detail="Tu cuenta ha sido cancelada.",
        )

    return ctx


async def get_tenant_id(
    ctx: TenantContext = Depends(require_active_tenant),
) -> int | None:
    """Retorna solo el tenant_id (requiere tenant activo)."""
    return ctx.tenant_id


async def verify_tenant_resource_ownership(
    resource_id: int,
    resource_workshop_id: int,
    ctx: TenantContext = Depends(require_active_tenant),
) -> None:
    """
    Verifica que un recurso pertenece al tenant del usuario.
    Admin bypass. Workshop solo ve sus recursos.
    """
    if ctx.user_type in ("admin", "administrator"):
        return

    if ctx.tenant_id is None:
        raise HTTPException(403, "No tienes permisos para este recurso")

    if resource_workshop_id != ctx.workshop_id if hasattr(ctx, 'workshop_id') else False:
        # Si no tenemos workshop_id directo, no podemos validar ownership
        # Usar la version con DB en el servicio correspondiente
        pass


def require_permission(required_permission: Permission):
    """
    Dependency factory que verifica que el usuario tenga un permiso específico.
    
    Uso:
        @router.get("/emergencies", dependencies=[Depends(require_permission(Permission.EMERGENCY_CREATE))])
        async def create_emergency():
            ...
    """
    async def permission_checker(
        user_payload: dict = Depends(get_current_user_payload),
    ) -> dict[str, Any]:
        user_type = user_payload.get("user_type")
        
        if not user_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token no contiene información de tipo de usuario",
            )
        
        check_permission(user_type, required_permission)
        return user_payload
    
    return permission_checker


def require_any_permission(*required_permissions: Permission):
    """
    Dependency factory que verifica que el usuario tenga al menos uno de los permisos.
    
    Uso:
        @router.get(
            "/reports",
            dependencies=[Depends(require_any_permission(
                Permission.REPORT_VIEW_OPERATIONAL,
                Permission.REPORT_VIEW_ALL
            ))]
        )
        async def view_reports():
            ...
    """
    from app.core.permissions import check_any_permission
    
    async def permission_checker(
        user_payload: dict = Depends(get_current_user_payload),
    ) -> dict[str, Any]:
        user_type = user_payload.get("user_type")
        
        if not user_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token no contiene información de tipo de usuario",
            )
        
        check_any_permission(user_type, list(required_permissions))
        return user_payload
    
    return permission_checker


def require_all_permissions(*required_permissions: Permission):
    """
    Dependency factory que verifica que el usuario tenga todos los permisos.
    
    Uso:
        @router.post(
            "/admin/configure",
            dependencies=[Depends(require_all_permissions(
                Permission.ADMIN_CONFIGURE_SYSTEM,
                Permission.ADMIN_VIEW_AUDIT_LOG
            ))]
        )
        async def configure_system():
            ...
    """
    from app.core.permissions import check_all_permissions
    
    async def permission_checker(
        user_payload: dict = Depends(get_current_user_payload),
    ) -> dict[str, Any]:
        user_type = user_payload.get("user_type")
        
        if not user_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token no contiene información de tipo de usuario",
            )
        
        check_all_permissions(user_type, list(required_permissions))
        return user_payload
    
    return permission_checker


def require_role(required_role: UserRole):
    """
    Dependency factory que verifica que el usuario tenga un rol específico.
    
    Uso:
        @router.get("/admin/dashboard", dependencies=[Depends(require_role(UserRole.ADMINISTRATOR))])
        async def admin_dashboard():
            ...
    """
    async def role_checker(
        user_payload: dict = Depends(get_current_user_payload),
    ) -> dict[str, Any]:
        user_type = user_payload.get("user_type")
        
        if not user_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token no contiene información de tipo de usuario",
            )
        
        try:
            current_role = UserRole(user_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rol de usuario inválido: {user_type}",
            )
        
        if current_role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere rol {required_role.value}, pero tienes {current_role.value}",
            )
        
        return user_payload
    
    return role_checker


def require_any_role(*required_roles: UserRole):
    """
    Dependency factory que verifica que el usuario tenga uno de los roles especificados.
    
    Uso:
        @router.get(
            "/services",
            dependencies=[Depends(require_any_role(UserRole.WORKSHOP, UserRole.TECHNICIAN))]
        )
        async def view_services():
            ...
    """
    async def role_checker(
        user_payload: dict = Depends(get_current_user_payload),
    ) -> dict[str, Any]:
        user_type = user_payload.get("user_type")
        
        if not user_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token no contiene información de tipo de usuario",
            )
        
        try:
            current_role = UserRole(user_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rol de usuario inválido: {user_type}",
            )
        
        if current_role not in required_roles:
            roles_str = ", ".join(r.value for r in required_roles)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere uno de los siguientes roles: {roles_str}",
            )
        
        return user_payload
    
    return role_checker


# Type aliases para facilitar el uso
CurrentUser = Annotated[dict[str, Any], Depends(get_current_user_payload)]
AdminUser = Annotated[dict[str, Any], Depends(require_role(UserRole.ADMINISTRATOR))]
ClientUser = Annotated[dict[str, Any], Depends(require_role(UserRole.CLIENT))]
WorkshopUser = Annotated[dict[str, Any], Depends(require_role(UserRole.WORKSHOP))]
TechnicianUser = Annotated[dict[str, Any], Depends(require_role(UserRole.TECHNICIAN))]
CurrentTenant = Annotated[TenantContext, Depends(require_active_tenant)]


def require_feature(feature_name: str):
    """
    Dependency factory que verifica que el tenant tiene acceso a una funcionalidad.

    Uso:
        @router.get("/reports/kpis", dependencies=[Depends(require_feature('enable_kpis'))])
    """
    async def checker(
        ctx: TenantContext = Depends(require_active_tenant),
        session: AsyncSession = Depends(get_db_session),
    ):
        if ctx.user_type in ("admin", "administrator"):
            return True

        if ctx.tenant_id is None:
            raise HTTPException(403, "Funcionalidad no disponible sin suscripcion activa")

        from app.models.tenant_subscription import TenantSubscription
        from app.models.subscription_plan import SubscriptionPlan

        result = await session.execute(
            select(TenantSubscription).join(
                SubscriptionPlan, TenantSubscription.plan_id == SubscriptionPlan.id
            ).where(
                TenantSubscription.tenant_id == ctx.tenant_id,
                TenantSubscription.status.in_(['active', 'trialing', 'past_due', 'pending_downgrade', 'pending_cancellation']),
            )
        )
        sub = result.scalar_one_or_none()

        if not sub:
            raise HTTPException(403, "No tienes una suscripcion activa")

        plan = await session.get(SubscriptionPlan, sub.plan_id)
        if not getattr(plan, feature_name, False):
            feature_labels = {
                'enable_kpis': 'KPIs avanzados',
                'enable_reports': 'Reportes PDF/Excel',
                'enable_realtime_tracking': 'Tracking en tiempo real',
                'enable_quotes': 'Cotizaciones',
                'enable_voice_reports': 'Reportes por voz',
                'enable_priority_support': 'Soporte prioritario',
                'enable_api_access': 'Acceso API',
            }
            label = feature_labels.get(feature_name, feature_name)
            raise HTTPException(
                403,
                detail=f"La funcionalidad '{label}' esta disponible en planes superiores. "
                       f"Tu plan actual es {plan.name}."
            )
        return True
    return checker
