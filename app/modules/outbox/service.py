"""
Outbox Service for managing outbox events.

This service provides utility functions for managing the outbox,
such as cleanup of old events and statistics.
"""

from datetime import datetime, timedelta
from typing import Dict, Any
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.outbox_event import OutboxEvent, EventPriority
from ...models.event_log import EventLog
from ...core.logging import get_logger

logger = get_logger(__name__)


class OutboxService:
    """
    Service for managing outbox events.
    
    Provides utility functions for:
    - Cleanup of old processed events
    - Statistics and monitoring
    - Manual reprocessing of failed events
    """
    
    @staticmethod
    async def cleanup_old_events(
        session: AsyncSession,
        days_old: int = 7
    ) -> int:
        """
        Delete processed events older than specified days.
        
        Args:
            session: Database session
            days_old: Delete events older than this many days (default: 7)
        
        Returns:
            int: Number of events deleted
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        # Delete old processed events
        result = await session.execute(
            select(OutboxEvent).where(
                and_(
                    OutboxEvent.processed == True,
                    OutboxEvent.processed_at < cutoff_date
                )
            )
        )
        old_events = result.scalars().all()
        
        for event in old_events:
            await session.delete(event)
        
        await session.commit()
        
        logger.info(f"Cleaned up {len(old_events)} old outbox events")
        return len(old_events)
    
    @staticmethod
    async def cleanup_old_event_logs(
        session: AsyncSession,
        days_old: int = 30
    ) -> int:
        """
        Delete event logs older than specified days.
        
        Args:
            session: Database session
            days_old: Delete logs older than this many days (default: 30)
        
        Returns:
            int: Number of logs deleted
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        # Delete old event logs
        result = await session.execute(
            select(EventLog).where(
                EventLog.delivered_at < cutoff_date
            )
        )
        old_logs = result.scalars().all()
        
        for log in old_logs:
            await session.delete(log)
        
        await session.commit()
        
        logger.info(f"Cleaned up {len(old_logs)} old event logs")
        return len(old_logs)
    
    @staticmethod
    async def get_statistics(
        session: AsyncSession
    ) -> Dict[str, Any]:
        """
        Get outbox statistics for monitoring.
        
        Args:
            session: Database session
        
        Returns:
            Dict with statistics
        """
        # Count pending events
        pending_result = await session.execute(
            select(func.count(OutboxEvent.id)).where(
                OutboxEvent.processed == False
            )
        )
        pending_count = pending_result.scalar_one()
        
        # Count failed events (max retries reached)
        failed_result = await session.execute(
            select(func.count(OutboxEvent.id)).where(
                and_(
                    OutboxEvent.processed == True,
                    OutboxEvent.retry_count >= 3
                )
            )
        )
        failed_count = failed_result.scalar_one()
        
        # Count events by priority
        priority_result = await session.execute(
            select(
                OutboxEvent.priority,
                func.count(OutboxEvent.id)
            ).where(
                OutboxEvent.processed == False
            ).group_by(OutboxEvent.priority)
        )
        priority_counts = {
            row[0]: row[1] for row in priority_result.all()
        }
        
        # Count processed in last hour
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        processed_hour_result = await session.execute(
            select(func.count(OutboxEvent.id)).where(
                and_(
                    OutboxEvent.processed == True,
                    OutboxEvent.processed_at >= one_hour_ago
                )
            )
        )
        processed_last_hour = processed_hour_result.scalar_one()
        
        # Count event logs in last hour
        logs_hour_result = await session.execute(
            select(func.count(EventLog.id)).where(
                EventLog.delivered_at >= one_hour_ago
            )
        )
        logs_last_hour = logs_hour_result.scalar_one()
        
        return {
            "pending_events": pending_count,
            "failed_events": failed_count,
            "priority_breakdown": priority_counts,
            "processed_last_hour": processed_last_hour,
            "deliveries_last_hour": logs_last_hour,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    async def retry_failed_events(
        session: AsyncSession,
        max_age_hours: int = 24
    ) -> int:
        """
        Reset retry count for failed events to allow reprocessing.
        
        Args:
            session: Database session
            max_age_hours: Only retry events younger than this (default: 24)
        
        Returns:
            int: Number of events reset for retry
        """
        cutoff_date = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        # Find failed events
        result = await session.execute(
            select(OutboxEvent).where(
                and_(
                    OutboxEvent.processed == False,
                    OutboxEvent.retry_count >= 3,
                    OutboxEvent.created_at >= cutoff_date
                )
            )
        )
        failed_events = result.scalars().all()
        
        # Reset retry count
        for event in failed_events:
            event.retry_count = 0
            event.last_error = None
        
        await session.commit()
        
        logger.info(f"Reset {len(failed_events)} failed events for retry")
        return len(failed_events)
