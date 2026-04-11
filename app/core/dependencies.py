"""
Dependencies para autorización y control de acceso basado en permisos.
"""

from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission, UserRole, check_permission
from app.core.database import get_db_session
from app.shared.dependencies.auth import get_current_token_payload as _get_current_token_payload
from app.modules.auth.schemas import TokenPayload


async def get_current_user_payload(
    token_payload: TokenPayload = Depends(_get_current_token_payload)
) -> dict[str, Any]:
    """
    Dependency que obtiene el payload del usuario actual desde el token JWT.
    
    Integrado con el sistema de autenticación existente.
    
    El payload contiene:
    - sub: ID del usuario
    - email: Email del usuario
    - user_type: Tipo de usuario (client, workshop, technician, administrator)
    - jti: ID único del token
    - exp: Fecha de expiración
    """
    return {
        "sub": token_payload.sub,
        "email": token_payload.email,
        "user_type": token_payload.user_type,
        "jti": token_payload.jti,
        "exp": token_payload.exp,
    }


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
