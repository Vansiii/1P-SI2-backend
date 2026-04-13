"""
Schemas for audit operations.
"""
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from ...shared.schemas.base import BaseSchema


class AuditLogResponse(BaseSchema):
    """Audit log response schema."""
    id: int
    user_id: Optional[int] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[int] = None
    ip_address: str
    user_agent: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_at: datetime


class AuditLogListResponse(BaseSchema):
    """Response for audit log list operations."""
    logs: list[AuditLogResponse]
    total: int
    limit: int
    offset: int


class AuditLogFilters(BaseModel):
    """Filters for audit log queries."""
    user_id: Optional[int] = None
    action: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    limit: int = Field(default=100, le=1000)
    offset: int = Field(default=0, ge=0)


class UserActivityResponse(BaseSchema):
    """Response for user activity queries."""
    user_id: int
    logs: list[AuditLogResponse]
    total_actions: int


class ResourceActivityResponse(BaseSchema):
    """Response for resource activity queries."""
    resource_type: str
    resource_id: int
    logs: list[AuditLogResponse]
    total_actions: int


class AuditStatsResponse(BaseSchema):
    """Response for audit statistics."""
    total_logs: int
    unique_users: int
    most_common_actions: list[dict[str, Any]]
    activity_by_day: list[dict[str, Any]]