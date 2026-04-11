"""
Permissions management endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from ...core import get_logger
from ...core.permissions import UserRole, Permission
from ...core.dependencies import AdminUser, require_permission
from ...core.responses import create_success_response
from .schemas import (
    AvailablePermissionsResponse,
    RolePermissionsResponse,
    AllRolesPermissionsResponse,
    UpdateRolePermissionsRequest,
    UpdateRolePermissionsResponse,
    AllRolesResponse,
)
from .service import PermissionsService

logger = get_logger(__name__)

router = APIRouter()


@router.get(
    "/permissions",
    response_model=AvailablePermissionsResponse,
    summary="Get all available permissions",
    description="Get list of all available permissions in the system (Admin only)",
    dependencies=[Depends(require_permission(Permission.ADMIN_MANAGE_PERMISSIONS))],
)
async def get_all_permissions(current_user: AdminUser):
    """Get all available permissions."""
    permissions = PermissionsService.get_all_permissions()
    
    return create_success_response(
        data={
            "permissions": permissions,
            "total": len(permissions)
        },
        message="Permisos obtenidos exitosamente"
    )


@router.get(
    "/roles",
    response_model=AllRolesResponse,
    summary="Get all roles",
    description="Get information about all roles in the system (Admin only)",
    dependencies=[Depends(require_permission(Permission.ADMIN_MANAGE_PERMISSIONS))],
)
async def get_all_roles(current_user: AdminUser):
    """Get all roles information."""
    roles = PermissionsService.get_all_roles_info()
    
    return create_success_response(
        data={
            "roles": roles,
            "total": len(roles)
        },
        message="Roles obtenidos exitosamente"
    )


@router.get(
    "/roles/permissions",
    response_model=AllRolesPermissionsResponse,
    summary="Get all roles with their permissions",
    description="Get all roles and their assigned permissions (Admin only)",
    dependencies=[Depends(require_permission(Permission.ADMIN_MANAGE_PERMISSIONS))],
)
async def get_all_roles_permissions(current_user: AdminUser):
    """Get all roles with their permissions."""
    roles_permissions = PermissionsService.get_all_roles_permissions()
    
    return create_success_response(
        data={"roles": roles_permissions},
        message="Permisos de roles obtenidos exitosamente"
    )


@router.get(
    "/roles/{role}/permissions",
    response_model=RolePermissionsResponse,
    summary="Get permissions for a specific role",
    description="Get all permissions assigned to a specific role (Admin only)",
    dependencies=[Depends(require_permission(Permission.ADMIN_MANAGE_PERMISSIONS))],
)
async def get_role_permissions(
    role: str,
    current_user: AdminUser
):
    """Get permissions for a specific role."""
    try:
        user_role = UserRole(role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rol inválido: {role}"
        )
    
    permissions = PermissionsService.get_role_permissions(user_role)
    
    return create_success_response(
        data={
            "role": user_role.value,
            "permissions": permissions,
            "total_permissions": len(permissions)
        },
        message=f"Permisos del rol {user_role.value} obtenidos exitosamente"
    )


@router.put(
    "/roles/{role}/permissions",
    response_model=UpdateRolePermissionsResponse,
    summary="Update permissions for a role",
    description="Update the permissions assigned to a role (Admin only, cannot modify ADMINISTRATOR or SYSTEM roles)",
    dependencies=[Depends(require_permission(Permission.ADMIN_MANAGE_PERMISSIONS))],
)
async def update_role_permissions(
    role: str,
    request: UpdateRolePermissionsRequest,
    current_user: AdminUser
):
    """Update permissions for a specific role."""
    try:
        user_role = UserRole(role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rol inválido: {role}"
        )
    
    # Check if role can be modified
    if not PermissionsService.can_modify_role(user_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No se pueden modificar los permisos del rol {user_role.value}"
        )
    
    # Validate permissions
    if not PermissionsService.validate_permissions(request.permissions):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uno o más permisos son inválidos"
        )
    
    try:
        result = PermissionsService.update_role_permissions(
            user_role,
            request.permissions
        )
        
        return create_success_response(
            data={
                **result,
                "message": f"Permisos del rol {user_role.value} actualizados exitosamente"
            },
            message=f"Se actualizaron los permisos del rol {user_role.value}"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post(
    "/roles/{role}/permissions/add",
    response_model=UpdateRolePermissionsResponse,
    summary="Add permissions to a role",
    description="Add specific permissions to a role without removing existing ones (Admin only)",
    dependencies=[Depends(require_permission(Permission.ADMIN_MANAGE_PERMISSIONS))],
)
async def add_permissions_to_role(
    role: str,
    request: UpdateRolePermissionsRequest,
    current_user: AdminUser
):
    """Add permissions to a role."""
    try:
        user_role = UserRole(role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rol inválido: {role}"
        )
    
    if not PermissionsService.can_modify_role(user_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No se pueden modificar los permisos del rol {user_role.value}"
        )
    
    # Get current permissions and add new ones
    current_perms = PermissionsService.get_role_permissions(user_role)
    new_perms = list(set(current_perms + request.permissions))
    
    try:
        result = PermissionsService.update_role_permissions(user_role, new_perms)
        
        return create_success_response(
            data={
                **result,
                "message": f"Permisos agregados al rol {user_role.value} exitosamente"
            },
            message=f"Se agregaron {len(result['added'])} permisos al rol {user_role.value}"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post(
    "/roles/{role}/permissions/remove",
    response_model=UpdateRolePermissionsResponse,
    summary="Remove permissions from a role",
    description="Remove specific permissions from a role (Admin only)",
    dependencies=[Depends(require_permission(Permission.ADMIN_MANAGE_PERMISSIONS))],
)
async def remove_permissions_from_role(
    role: str,
    request: UpdateRolePermissionsRequest,
    current_user: AdminUser
):
    """Remove permissions from a role."""
    try:
        user_role = UserRole(role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rol inválido: {role}"
        )
    
    if not PermissionsService.can_modify_role(user_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No se pueden modificar los permisos del rol {user_role.value}"
        )
    
    # Get current permissions and remove specified ones
    current_perms = PermissionsService.get_role_permissions(user_role)
    new_perms = [p for p in current_perms if p not in request.permissions]
    
    try:
        result = PermissionsService.update_role_permissions(user_role, new_perms)
        
        return create_success_response(
            data={
                **result,
                "message": f"Permisos removidos del rol {user_role.value} exitosamente"
            },
            message=f"Se removieron {len(result['removed'])} permisos del rol {user_role.value}"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
