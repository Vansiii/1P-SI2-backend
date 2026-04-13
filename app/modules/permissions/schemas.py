"""
Schemas for permissions management.
"""
from typing import List
from pydantic import BaseModel, Field

from ...core.permissions import UserRole, Permission


class PermissionInfo(BaseModel):
    """Information about a permission."""
    name: str = Field(..., description="Permission name")
    value: str = Field(..., description="Permission value")
    description: str = Field(..., description="Permission description")


class RolePermissionsResponse(BaseModel):
    """Response with role permissions."""
    role: str = Field(..., description="Role name")
    permissions: List[str] = Field(..., description="List of permission values")
    total_permissions: int = Field(..., description="Total number of permissions")


class AllRolesPermissionsResponse(BaseModel):
    """Response with all roles and their permissions."""
    roles: List[RolePermissionsResponse] = Field(..., description="List of roles with permissions")


class AvailablePermissionsResponse(BaseModel):
    """Response with all available permissions."""
    permissions: List[PermissionInfo] = Field(..., description="List of available permissions")
    total: int = Field(..., description="Total number of permissions")


class UpdateRolePermissionsRequest(BaseModel):
    """Request to update role permissions."""
    permissions: List[str] = Field(
        ...,
        description="List of permission values to assign to the role",
        min_items=0
    )


class UpdateRolePermissionsResponse(BaseModel):
    """Response after updating role permissions."""
    role: str = Field(..., description="Role name")
    permissions: List[str] = Field(..., description="Updated list of permissions")
    added: List[str] = Field(..., description="Permissions that were added")
    removed: List[str] = Field(..., description="Permissions that were removed")
    message: str = Field(..., description="Success message")


class RoleInfo(BaseModel):
    """Information about a role."""
    name: str = Field(..., description="Role name")
    value: str = Field(..., description="Role value")
    description: str = Field(..., description="Role description")
    can_modify: bool = Field(..., description="Whether this role can be modified")
    permission_count: int = Field(..., description="Number of permissions")


class AllRolesResponse(BaseModel):
    """Response with all roles information."""
    roles: List[RoleInfo] = Field(..., description="List of roles")
    total: int = Field(..., description="Total number of roles")
