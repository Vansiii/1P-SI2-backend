"""
Service for audit logging and tracking operations.
"""
import json
from datetime import datetime
from typing import Any, List, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_logger
from ...models.audit_log import AuditLog
from .repository import AuditRepository

logger = get_logger(__name__)


class AuditService:
    """Service for audit logging operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.audit_repo = AuditRepository(session)
    
    async def log_action(
        self,
        action: str,
        user_id: Optional[int] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[int] = None,
        ip_address: str = "unknown",
        user_agent: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> AuditLog:
        """
        Log an action in the audit trail.
        
        Args:
            action: Action performed (e.g., 'login', 'logout', 'password_change')
            user_id: ID of user who performed the action (optional)
            resource_type: Type of affected resource (e.g., 'user', 'workshop')
            resource_id: ID of affected resource
            ip_address: Client IP address
            user_agent: Client user agent
            details: Additional details in dict format (converted to JSON)
            
        Returns:
            Created AuditLog
        """
        # Convert details to JSON if exists
        details_json = None
        if details:
            try:
                details_json = json.dumps(details, ensure_ascii=False)
            except Exception as e:
                logger.error("Error serializing audit details", error=str(e), details=details)
                details_json = json.dumps({"error": "Failed to serialize details"})
        
        # Create audit log record
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent[:500] if user_agent else None,  # Limit to 500 chars
            details=details_json,
        )
        
        self.session.add(audit_log)
        await self.session.commit()
        await self.session.refresh(audit_log)
        
        logger.info(
            "Audit action logged",
            action=action,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        
        return audit_log
    
    async def log_action_from_request(
        self,
        request: Request,
        action: str,
        user_id: Optional[int] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[int] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> AuditLog:
        """
        Log an action extracting IP and user agent from Request.
        
        Convenient wrapper for log_action() that automatically extracts
        information from FastAPI Request.
        
        Args:
            request: FastAPI Request object
            action: Action performed
            user_id: ID of user who performed the action
            resource_type: Type of affected resource
            resource_id: ID of affected resource
            details: Additional details
            
        Returns:
            Created AuditLog
        """
        ip_address = "unknown"
        if request.client:
            ip_address = request.client.host
        
        user_agent = request.headers.get("user-agent")
        
        return await self.log_action(
            action=action,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details,
        )
    
    async def get_audit_logs(
        self,
        user_id: Optional[int] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[List[AuditLog], int]:
        """
        Get audit logs with optional filters.
        
        Args:
            user_id: Filter by user
            action: Filter by action
            resource_type: Filter by resource type
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            Tuple of (List of AuditLog, total count)
        """
        return await self.audit_repo.find_with_filters(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            limit=limit,
            offset=offset,
        )
    
    async def get_user_activity(
        self,
        user_id: int,
        limit: int = 50,
    ) -> List[AuditLog]:
        """
        Get recent activity for a user.
        
        Args:
            user_id: User ID
            limit: Maximum number of results
            
        Returns:
            List of AuditLog for the user
        """
        return await self.get_audit_logs(
            user_id=user_id,
            limit=limit,
        )
    
    async def get_resource_activity(
        self,
        resource_type: str,
        resource_id: int,
        limit: int = 50,
    ) -> List[AuditLog]:
        """
        Get recent activity for a specific resource.
        
        Args:
            resource_type: Type of resource
            resource_id: Resource ID
            limit: Maximum number of results
            
        Returns:
            List of AuditLog for the resource
        """
        return await self.audit_repo.find_by_resource(
            resource_type=resource_type,
            resource_id=resource_id,
            limit=limit,
        )
    
    async def cleanup_old_logs(self, days_to_keep: int = 90) -> int:
        """
        Clean up old audit logs.
        
        Args:
            days_to_keep: Number of days to keep logs
            
        Returns:
            Number of logs deleted
        """
        count = await self.audit_repo.delete_old_logs(days_to_keep)
        logger.info("Old audit logs cleaned up", count=count, days_to_keep=days_to_keep)
        return count


# Constants for common actions
class AuditAction:
    """Constants for audit actions."""
    
    # Authentication
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    REGISTER = "register"
    
    # Passwords
    PASSWORD_CHANGE = "password_change"
    PASSWORD_RESET_REQUEST = "password_reset_request"
    PASSWORD_RESET = "password_reset"
    
    # 2FA
    TWO_FA_ENABLED = "2fa_enabled"
    TWO_FA_DISABLED = "2fa_disabled"
    TWO_FA_VERIFIED = "2fa_verified"
    
    # Tokens
    TOKEN_REFRESH = "token_refresh"
    TOKEN_REVOKE_ALL = "token_revoke_all"
    
    # Account
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_UNLOCKED = "account_unlocked"
    ACCOUNT_DELETED = "account_deleted"
    
    # Profile
    PROFILE_UPDATE = "profile_update"
    
    # Administration
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"


# Constants for resource types
class ResourceType:
    """Constants for resource types."""
    
    USER = "user"
    CLIENT = "client"
    WORKSHOP = "workshop"
    TECHNICIAN = "technician"
    ADMINISTRATOR = "administrator"
    INCIDENT = "incident"
    VEHICLE = "vehicle"
    SERVICE = "service"