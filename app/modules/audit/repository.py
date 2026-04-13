"""
Audit log repository.
"""
from datetime import datetime, UTC, timedelta
from typing import Any, Sequence

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logging import get_logger
from ...models.audit_log import AuditLog
from ...shared.repositories.base import BaseRepository

logger = get_logger(__name__)


class AuditRepository(BaseRepository[AuditLog]):
    """Repository for AuditLog operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, AuditLog)
    
    async def find_by_user(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
        action: str | None = None,
        resource_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> Sequence[AuditLog]:
        """
        Find audit logs by user with optional filters.
        
        Args:
            user_id: User ID
            skip: Number of records to skip
            limit: Maximum number of records
            action: Filter by action
            resource_type: Filter by resource type
            start_date: Filter by start date
            end_date: Filter by end date
            
        Returns:
            List of audit logs
        """
        try:
            query = select(AuditLog).where(AuditLog.user_id == user_id)
            
            if action:
                query = query.where(AuditLog.action == action)
            
            if resource_type:
                query = query.where(AuditLog.resource_type == resource_type)
            
            if start_date:
                query = query.where(AuditLog.created_at >= start_date)
            
            if end_date:
                query = query.where(AuditLog.created_at <= end_date)
            
            query = query.order_by(AuditLog.created_at.desc())
            query = query.offset(skip).limit(limit)
            
            result = await self.session.execute(query)
            logs = result.scalars().all()
            
            logger.debug(
                "Found audit logs by user",
                user_id=user_id,
                count=len(logs),
                action=action,
                resource_type=resource_type,
            )
            
            return logs
            
        except Exception as exc:
            logger.error(
                "Error finding audit logs by user",
                user_id=user_id,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def find_by_action(
        self,
        action: str,
        skip: int = 0,
        limit: int = 100,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> Sequence[AuditLog]:
        """
        Find audit logs by action.
        
        Args:
            action: Action to filter by
            skip: Number of records to skip
            limit: Maximum number of records
            start_date: Filter by start date
            end_date: Filter by end date
            
        Returns:
            List of audit logs
        """
        try:
            query = select(AuditLog).where(AuditLog.action == action)
            
            if start_date:
                query = query.where(AuditLog.created_at >= start_date)
            
            if end_date:
                query = query.where(AuditLog.created_at <= end_date)
            
            query = query.order_by(AuditLog.created_at.desc())
            query = query.offset(skip).limit(limit)
            
            result = await self.session.execute(query)
            logs = result.scalars().all()
            
            logger.debug(
                "Found audit logs by action",
                action=action,
                count=len(logs),
            )
            
            return logs
            
        except Exception as exc:
            logger.error(
                "Error finding audit logs by action",
                action=action,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def find_by_ip_address(
        self,
        ip_address: str,
        skip: int = 0,
        limit: int = 100,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> Sequence[AuditLog]:
        """
        Find audit logs by IP address.
        
        Args:
            ip_address: IP address to filter by
            skip: Number of records to skip
            limit: Maximum number of records
            start_date: Filter by start date
            end_date: Filter by end date
            
        Returns:
            List of audit logs
        """
        try:
            query = select(AuditLog).where(AuditLog.ip_address == ip_address)
            
            if start_date:
                query = query.where(AuditLog.created_at >= start_date)
            
            if end_date:
                query = query.where(AuditLog.created_at <= end_date)
            
            query = query.order_by(AuditLog.created_at.desc())
            query = query.offset(skip).limit(limit)
            
            result = await self.session.execute(query)
            logs = result.scalars().all()
            
            logger.debug(
                "Found audit logs by IP",
                ip_address=ip_address,
                count=len(logs),
            )
            
            return logs
            
        except Exception as exc:
            logger.error(
                "Error finding audit logs by IP",
                ip_address=ip_address,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def get_action_stats(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get statistics of actions performed.
        
        Args:
            start_date: Filter by start date
            end_date: Filter by end date
            
        Returns:
            List of action statistics
        """
        try:
            query = select(
                AuditLog.action,
                func.count(AuditLog.id).label('count')
            )
            
            if start_date:
                query = query.where(AuditLog.created_at >= start_date)
            
            if end_date:
                query = query.where(AuditLog.created_at <= end_date)
            
            query = query.group_by(AuditLog.action)
            query = query.order_by(func.count(AuditLog.id).desc())
            
            result = await self.session.execute(query)
            stats = [
                {"action": row.action, "count": row.count}
                for row in result
            ]
            
            logger.debug("Generated action statistics", stats_count=len(stats))
            
            return stats
            
        except Exception as exc:
            logger.error(
                "Error generating action statistics",
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def cleanup_old_logs(self, days_to_keep: int = 90) -> int:
        """
        Delete old audit logs to manage storage.
        
        Args:
            days_to_keep: Number of days to keep logs
            
        Returns:
            Number of deleted logs
        """
        try:
            cutoff_date = datetime.now(UTC) - timedelta(days=days_to_keep)
            
            query = delete(AuditLog).where(
                AuditLog.created_at < cutoff_date
            )
            
            result = await self.session.execute(query)
            await self.session.commit()
            
            deleted_count = result.rowcount or 0
            
            logger.info(
                "Cleaned up old audit logs",
                count=deleted_count,
                days_to_keep=days_to_keep,
            )
            
            return deleted_count
            
        except Exception as exc:
            await self.session.rollback()
            logger.error(
                "Error cleaning up old audit logs",
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def get_user_activity_summary(
        self,
        user_id: int,
        days: int = 30,
    ) -> dict[str, Any]:
        """
        Get user activity summary for the last N days.
        
        Args:
            user_id: User ID
            days: Number of days to analyze
            
        Returns:
            Activity summary
        """
        try:
            start_date = datetime.now(UTC) - timedelta(days=days)
            
            # Get total actions
            total_query = select(func.count(AuditLog.id)).where(
                AuditLog.user_id == user_id,
                AuditLog.created_at >= start_date,
            )
            total_result = await self.session.execute(total_query)
            total_actions = total_result.scalar() or 0
            
            # Get actions by type
            actions_query = select(
                AuditLog.action,
                func.count(AuditLog.id).label('count')
            ).where(
                AuditLog.user_id == user_id,
                AuditLog.created_at >= start_date,
            ).group_by(AuditLog.action)
            
            actions_result = await self.session.execute(actions_query)
            actions_by_type = {
                row.action: row.count
                for row in actions_result
            }
            
            # Get last activity
            last_activity_query = select(AuditLog.created_at).where(
                AuditLog.user_id == user_id
            ).order_by(AuditLog.created_at.desc()).limit(1)
            
            last_activity_result = await self.session.execute(last_activity_query)
            last_activity = last_activity_result.scalar_one_or_none()
            
            summary = {
                "user_id": user_id,
                "period_days": days,
                "total_actions": total_actions,
                "actions_by_type": actions_by_type,
                "last_activity": last_activity,
            }
            
            logger.debug(
                "Generated user activity summary",
                user_id=user_id,
                total_actions=total_actions,
            )
            
            return summary
            
        except Exception as exc:
            logger.error(
                "Error generating user activity summary",
                user_id=user_id,
                error=str(exc),
                exc_info=True,
            )
            raise