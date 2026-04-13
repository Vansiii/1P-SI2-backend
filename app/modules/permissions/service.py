"""
Service for permissions management.
"""
from typing import List, Dict, Set
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.permissions import UserRole, Permission, ROLE_PERMISSIONS
from ...core import get_logger

logger = get_logger(__name__)


class PermissionsService:
    """Service for managing role permissions."""
    
    # Roles that cannot be modified
    PROTECTED_ROLES = {UserRole.ADMINISTRATOR, UserRole.SYSTEM}
    
    @staticmethod
    def get_all_permissions() -> List[Dict[str, str]]:
        """Get all available permissions."""
        permissions = []
        for perm in Permission:
            permissions.append({
                "name": perm.name,
                "value": perm.value,
                "description": perm.value.replace("_", " ").title()
            })
        return permissions
    
    @staticmethod
    def get_role_permissions(role: UserRole) -> List[str]:
        """Get permissions for a specific role."""
        return [perm.value for perm in ROLE_PERMISSIONS.get(role, set())]
    
    @staticmethod
    def get_all_roles_permissions() -> List[Dict[str, any]]:
        """Get all roles with their permissions."""
        roles_data = []
        for role in UserRole:
            permissions = PermissionsService.get_role_permissions(role)
            roles_data.append({
                "role": role.value,
                "permissions": permissions,
                "total_permissions": len(permissions)
            })
        return roles_data
    
    @staticmethod
    def get_all_roles_info() -> List[Dict[str, any]]:
        """Get information about all roles."""
        role_descriptions = {
            UserRole.CLIENT: "Cliente que reporta emergencias vehiculares",
            UserRole.WORKSHOP: "Taller mecánico que atiende emergencias",
            UserRole.TECHNICIAN: "Técnico de taller que realiza servicios",
            UserRole.ADMINISTRATOR: "Administrador del sistema con acceso completo",
            UserRole.SYSTEM: "Procesos automáticos e inteligencia artificial"
        }
        
        roles_data = []
        for role in UserRole:
            permissions = PermissionsService.get_role_permissions(role)
            roles_data.append({
                "name": role.name,
                "value": role.value,
                "description": role_descriptions.get(role, ""),
                "can_modify": role not in PermissionsService.PROTECTED_ROLES,
                "permission_count": len(permissions)
            })
        return roles_data
    
    @staticmethod
    def can_modify_role(role: UserRole) -> bool:
        """Check if a role can be modified."""
        return role not in PermissionsService.PROTECTED_ROLES
    
    @staticmethod
    def update_role_permissions(
        role: UserRole,
        new_permissions: List[str]
    ) -> Dict[str, any]:
        """
        Update permissions for a role.
        
        Note: This updates the in-memory ROLE_PERMISSIONS dict.
        For persistence, you'd need to store this in a database.
        """
        if not PermissionsService.can_modify_role(role):
            raise ValueError(f"Cannot modify permissions for role {role.value}")
        
        # Get current permissions
        current_perms = ROLE_PERMISSIONS.get(role, set())
        current_perm_values = {perm.value for perm in current_perms}
        
        # Convert new permissions to Permission enums
        new_perm_set = set()
        invalid_perms = []
        for perm_value in new_permissions:
            try:
                perm = Permission(perm_value)
                new_perm_set.add(perm)
            except ValueError:
                invalid_perms.append(perm_value)
        
        if invalid_perms:
            raise ValueError(f"Invalid permissions: {', '.join(invalid_perms)}")
        
        # Calculate changes
        added = new_perm_set - current_perms
        removed = current_perms - new_perm_set
        
        # Update the role permissions
        ROLE_PERMISSIONS[role] = new_perm_set
        
        logger.info(
            f"Updated permissions for role {role.value}: "
            f"added {len(added)}, removed {len(removed)}"
        )
        
        return {
            "role": role.value,
            "permissions": [perm.value for perm in new_perm_set],
            "added": [perm.value for perm in added],
            "removed": [perm.value for perm in removed]
        }
    
    @staticmethod
    def validate_permissions(permissions: List[str]) -> bool:
        """Validate that all permissions are valid."""
        valid_perms = {perm.value for perm in Permission}
        return all(perm in valid_perms for perm in permissions)
