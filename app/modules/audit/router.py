"""
Audit endpoints.
"""
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_db_session, get_logger
from ...core.responses import create_success_response, create_paginated_response
from .schemas import (
    AuditLogResponse,
    AuditLogListResponse,
    AuditLogFilters,
    UserActivityResponse,
    ResourceActivityResponse,
)
from .service import AuditService
from ...shared.dependencies.auth import get_current_user
from ...shared.schemas.pagination import PaginationParams
from ...models.user import User

logger = get_logger(__name__)

router = APIRouter()


@router.get(
    "/logs",
    response_model=AuditLogListResponse,
    summary="Get audit logs",
    description="Get audit logs with optional filtering and pagination",
)
async def get_audit_logs(
    user_id: int = Query(None, description="Filter by user ID"),
    action: str = Query(None, description="Filter by action"),
    resource_type: str = Query(None, description="Filter by resource type"),
    resource_id: int = Query(None, description="Filter by resource ID"),
    pagination: PaginationParams = Depends(),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Get audit logs with filtering and pagination."""
    # TODO: Add admin authorization check
    audit_service = AuditService(session)
    
    logs = await audit_service.get_audit_logs(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    
    # For total count, we'd need a separate count query
    total = len(logs)  # Simplified for now
    
    return create_paginated_response(
        data=logs,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get(
    "/users/{user_id}/activity",
    response_model=UserActivityResponse,
    summary="Get user activity",
    description="Get activity logs for a specific user",
)
async def get_user_activity(
    user_id: int,
    limit: int = Query(50, le=200, description="Maximum number of logs to return"),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Get activity logs for a specific user."""
    # TODO: Add authorization check (admin or own user)
    audit_service = AuditService(session)
    
    logs = await audit_service.get_user_activity(user_id, limit)
    
    return create_success_response(
        data={
            "user_id": user_id,
            "logs": logs,
            "total_actions": len(logs),
        },
        message=f"Actividad del usuario {user_id} obtenida exitosamente",
    )


@router.get(
    "/resources/{resource_type}/{resource_id}/activity",
    response_model=ResourceActivityResponse,
    summary="Get resource activity",
    description="Get activity logs for a specific resource",
)
async def get_resource_activity(
    resource_type: str,
    resource_id: int,
    limit: int = Query(50, le=200, description="Maximum number of logs to return"),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Get activity logs for a specific resource."""
    # TODO: Add admin authorization check
    audit_service = AuditService(session)
    
    logs = await audit_service.get_resource_activity(resource_type, resource_id, limit)
    
    return create_success_response(
        data={
            "resource_type": resource_type,
            "resource_id": resource_id,
            "logs": logs,
            "total_actions": len(logs),
        },
        message=f"Actividad del recurso {resource_type}:{resource_id} obtenida exitosamente",
    )


@router.post(
    "/cleanup",
    summary="Cleanup old audit logs",
    description="Clean up old audit logs (admin only)",
)
async def cleanup_audit_logs(
    days_to_keep: int = Query(90, ge=30, le=365, description="Number of days to keep logs"),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Clean up old audit logs."""
    # TODO: Add admin authorization check
    audit_service = AuditService(session)
    count = await audit_service.cleanup_old_logs(days_to_keep)
    
    return create_success_response(
        data={"deleted_count": count},
        message=f"Se eliminaron {count} logs de auditoría antiguos",
    )
