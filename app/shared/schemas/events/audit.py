"""Audit event schemas for security and compliance monitoring."""

from datetime import datetime
from typing import Any, Dict, Optional, Literal

from pydantic import Field

from .base import BaseEvent, EventPriority


class AuditCriticalActionEvent(BaseEvent):
    """Event emitted when a critical action is performed."""
    
    event_type: Literal["audit.critical_action"] = "audit.critical_action"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    action: str = Field(..., description="Action performed")
    user_id: int = Field(..., description="User who performed the action")
    user_role: str = Field(..., description="Role of the user")
    resource: str = Field(..., description="Resource affected")
    resource_id: Optional[int] = Field(None, description="ID of the resource")
    ip_address: Optional[str] = Field(None, description="IP address of the user")
    user_agent: Optional[str] = Field(None, description="User agent string")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")


class AuditSuspiciousActivityEvent(BaseEvent):
    """Event emitted when suspicious activity is detected."""
    
    event_type: Literal["audit.suspicious_activity"] = "audit.suspicious_activity"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    activity_type: str = Field(..., description="Type of suspicious activity")
    user_id: Optional[int] = Field(None, description="User ID if known")
    ip_address: Optional[str] = Field(None, description="IP address")
    details: Dict[str, Any] = Field(..., description="Activity details")
    severity: str = Field(..., description="Severity level (low, medium, high, critical)")
    detected_at: datetime = Field(default_factory=datetime.utcnow)


class AuditSecurityBreachEvent(BaseEvent):
    """Event emitted when a security breach is detected."""
    
    event_type: Literal["audit.security_breach"] = "audit.security_breach"
    priority: EventPriority = Field(default=EventPriority.CRITICAL)
    
    breach_type: str = Field(..., description="Type of security breach")
    severity: str = Field(..., description="Severity level")
    affected_resource: str = Field(..., description="Affected resource")
    affected_users: Optional[list] = Field(None, description="List of affected user IDs")
    details: Dict[str, Any] = Field(..., description="Breach details")
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    mitigation_status: Optional[str] = Field(None, description="Current mitigation status")
