"""
Audit endpoints.
"""
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_db_session, get_logger
from ...core.responses import create_success_response, create_paginated_response
from ...core.permissions import Permission
from ...core.dependencies import require_permission, AdminUser
from .schemas import (
    AuditLogResponse,
    AuditLogListResponse,
    AuditLogFilters,
    UserActivityResponse,
    ResourceActivityResponse,
)
from .service import AuditService
from ...shared.schemas.pagination import PaginationParams

logger = get_logger(__name__)

router = APIRouter()


@router.get(
    "/logs",
    response_model=AuditLogListResponse,
    summary="Get audit logs",
    description="Get audit logs with optional filtering and pagination (Admin only)",
    dependencies=[Depends(require_permission(Permission.ADMIN_VIEW_AUDIT_LOG))],
)
async def get_audit_logs(
    current_user: AdminUser,
    user_id: int = Query(None, description="Filter by user ID"),
    action: str = Query(None, description="Filter by action"),
    resource_type: str = Query(None, description="Filter by resource type"),
    resource_id: int = Query(None, description="Filter by resource ID"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Number of records to return"),
    session: AsyncSession = Depends(get_db_session),
):
    """Get audit logs with filtering and pagination."""
    audit_service = AuditService(session)
    
    logs, total = await audit_service.get_audit_logs(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        limit=limit,
        offset=skip,
    )
    
    # Convert SQLAlchemy models to dicts for JSON serialization
    logs_data = []
    for log in logs:
        log_dict = {
            "id": log.id,
            "user_id": log.user_id,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "ip_address": log.ip_address,
            "user_agent": log.user_agent,
            "details": log.details,
            "timestamp": log.created_at.isoformat() if log.created_at else None,
        }
        logs_data.append(log_dict)
    
    # Calculate pagination metadata
    total_pages = (total + limit - 1) // limit  # Ceiling division
    current_page = (skip // limit) + 1
    
    # Return paginated response in consistent format
    return create_success_response(
        data={
            "logs": logs_data,
            "total": total,
            "page": current_page,
            "page_size": limit,
            "total_pages": total_pages,
        },
        status_code=200,
    )


@router.get(
    "/users/{user_id}/activity",
    response_model=UserActivityResponse,
    summary="Get user activity",
    description="Get activity logs for a specific user (Admin only)",
    dependencies=[Depends(require_permission(Permission.ADMIN_VIEW_AUDIT_LOG))],
)
async def get_user_activity(
    user_id: int,
    current_user: AdminUser,
    limit: int = Query(50, le=200, description="Maximum number of logs to return"),
    session: AsyncSession = Depends(get_db_session),
):
    """Get activity logs for a specific user."""
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
    description="Get activity logs for a specific resource (Admin only)",
    dependencies=[Depends(require_permission(Permission.ADMIN_VIEW_AUDIT_LOG))],
)
async def get_resource_activity(
    resource_type: str,
    resource_id: int,
    current_user: AdminUser,
    limit: int = Query(50, le=200, description="Maximum number of logs to return"),
    session: AsyncSession = Depends(get_db_session),
):
    """Get activity logs for a specific resource."""
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
    description="Clean up old audit logs (Admin only)",
    dependencies=[Depends(require_permission(Permission.ADMIN_VIEW_AUDIT_LOG))],
)
async def cleanup_audit_logs(
    current_user: AdminUser,
    days_to_keep: int = Query(90, ge=30, le=365, description="Number of days to keep logs"),
    session: AsyncSession = Depends(get_db_session),
):
    """Clean up old audit logs."""
    audit_service = AuditService(session)
    count = await audit_service.cleanup_old_logs(days_to_keep)
    
    return create_success_response(
        data={"deleted_count": count},
        message=f"Se eliminaron {count} logs de auditoría antiguos",
    )
