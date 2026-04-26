"""
Communication metrics for monitoring real-time system performance.
"""
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from ...core.logging import get_logger
from ...models.event_log import EventLog
from ...models.outbox_event import OutboxEvent
from ...models.technician_location_history import TechnicianLocationHistory

logger = get_logger(__name__)


class CommunicationMetricsService:
    """
    Service for collecting and reporting communication metrics.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_event_metrics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get metrics about event processing and delivery.
        
        Args:
            start_time: Optional start time filter
            end_time: Optional end time filter
            
        Returns:
            Dictionary with event metrics
        """
        # Default to last 24 hours if not specified
        if not end_time:
            end_time = datetime.utcnow()
        if not start_time:
            start_time = end_time - timedelta(hours=24)

        # Total events published to outbox
        total_published_query = select(func.count()).select_from(OutboxEvent).where(
            and_(
                OutboxEvent.created_at >= start_time,
                OutboxEvent.created_at <= end_time
            )
        )
        total_published = await self.session.scalar(total_published_query) or 0

        # Events successfully processed
        processed_query = select(func.count()).select_from(OutboxEvent).where(
            and_(
                OutboxEvent.created_at >= start_time,
                OutboxEvent.created_at <= end_time,
                OutboxEvent.processed == True
            )
        )
        processed = await self.session.scalar(processed_query) or 0

        # Events pending processing
        pending_query = select(func.count()).select_from(OutboxEvent).where(
            and_(
                OutboxEvent.created_at >= start_time,
                OutboxEvent.created_at <= end_time,
                OutboxEvent.processed == False,
                OutboxEvent.retry_count < 3
            )
        )
        pending = await self.session.scalar(pending_query) or 0

        # Events failed (max retries exceeded)
        failed_query = select(func.count()).select_from(OutboxEvent).where(
            and_(
                OutboxEvent.created_at >= start_time,
                OutboxEvent.created_at <= end_time,
                OutboxEvent.processed == False,
                OutboxEvent.retry_count >= 3
            )
        )
        failed = await self.session.scalar(failed_query) or 0

        # Total events delivered
        delivered_query = select(func.count()).select_from(EventLog).where(
            and_(
                EventLog.delivered_at >= start_time,
                EventLog.delivered_at <= end_time
            )
        )
        delivered = await self.session.scalar(delivered_query) or 0

        # Events delivered via WebSocket
        ws_delivered_query = select(func.count()).select_from(EventLog).where(
            and_(
                EventLog.delivered_at >= start_time,
                EventLog.delivered_at <= end_time,
                EventLog.delivered_via == 'websocket'
            )
        )
        ws_delivered = await self.session.scalar(ws_delivered_query) or 0

        # Events delivered via FCM
        fcm_delivered_query = select(func.count()).select_from(EventLog).where(
            and_(
                EventLog.delivered_at >= start_time,
                EventLog.delivered_at <= end_time,
                EventLog.delivered_via == 'fcm'
            )
        )
        fcm_delivered = await self.session.scalar(fcm_delivered_query) or 0

        # Calculate success rate
        success_rate = (processed / total_published * 100) if total_published > 0 else 0

        # Calculate delivery rate
        delivery_rate = (delivered / processed * 100) if processed > 0 else 0

        return {
            "period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "duration_hours": (end_time - start_time).total_seconds() / 3600
            },
            "outbox": {
                "total_published": total_published,
                "processed": processed,
                "pending": pending,
                "failed": failed,
                "success_rate_percent": round(success_rate, 2)
            },
            "delivery": {
                "total_delivered": delivered,
                "websocket_delivered": ws_delivered,
                "fcm_delivered": fcm_delivered,
                "delivery_rate_percent": round(delivery_rate, 2)
            }
        }

    async def get_location_metrics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get metrics about GPS location tracking.
        
        Args:
            start_time: Optional start time filter
            end_time: Optional end time filter
            
        Returns:
            Dictionary with location metrics
        """
        # Default to last 24 hours if not specified
        if not end_time:
            end_time = datetime.utcnow()
        if not start_time:
            start_time = end_time - timedelta(hours=24)

        # Total location updates
        total_query = select(func.count()).select_from(TechnicianLocationHistory).where(
            and_(
                TechnicianLocationHistory.recorded_at >= start_time,
                TechnicianLocationHistory.recorded_at <= end_time
            )
        )
        total_updates = await self.session.scalar(total_query) or 0

        # Unique technicians tracked
        unique_techs_query = select(func.count(func.distinct(TechnicianLocationHistory.technician_id))).where(
            and_(
                TechnicianLocationHistory.recorded_at >= start_time,
                TechnicianLocationHistory.recorded_at <= end_time
            )
        )
        unique_technicians = await self.session.scalar(unique_techs_query) or 0

        # Average accuracy
        avg_accuracy_query = select(func.avg(TechnicianLocationHistory.accuracy)).where(
            and_(
                TechnicianLocationHistory.recorded_at >= start_time,
                TechnicianLocationHistory.recorded_at <= end_time,
                TechnicianLocationHistory.accuracy.isnot(None)
            )
        )
        avg_accuracy = await self.session.scalar(avg_accuracy_query) or 0

        # Calculate updates per hour
        duration_hours = (end_time - start_time).total_seconds() / 3600
        updates_per_hour = total_updates / duration_hours if duration_hours > 0 else 0

        # Calculate updates per technician
        updates_per_tech = total_updates / unique_technicians if unique_technicians > 0 else 0

        return {
            "period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "duration_hours": duration_hours
            },
            "tracking": {
                "total_updates": total_updates,
                "unique_technicians": unique_technicians,
                "updates_per_hour": round(updates_per_hour, 2),
                "updates_per_technician": round(updates_per_tech, 2),
                "average_accuracy_meters": round(float(avg_accuracy), 2) if avg_accuracy else None
            }
        }

    async def get_reconnection_metrics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get metrics about WebSocket reconnection attempts.
        
        Note: This requires logging reconnection attempts to database.
        For now, returns placeholder data.
        
        Args:
            start_time: Optional start time filter
            end_time: Optional end time filter
            
        Returns:
            Dictionary with reconnection metrics
        """
        # TODO: Implement reconnection tracking in database
        # For now, return placeholder data
        
        return {
            "period": {
                "start": start_time.isoformat() if start_time else None,
                "end": end_time.isoformat() if end_time else None
            },
            "reconnection": {
                "note": "Reconnection metrics not yet implemented",
                "total_attempts": 0,
                "successful_reconnections": 0,
                "failed_reconnections": 0,
                "average_backoff_seconds": 0
            }
        }

    async def get_comprehensive_metrics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get comprehensive communication metrics.
        
        Args:
            start_time: Optional start time filter
            end_time: Optional end time filter
            
        Returns:
            Dictionary with all communication metrics
        """
        event_metrics = await self.get_event_metrics(start_time, end_time)
        location_metrics = await self.get_location_metrics(start_time, end_time)
        reconnection_metrics = await self.get_reconnection_metrics(start_time, end_time)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "events": event_metrics,
            "locations": location_metrics,
            "reconnections": reconnection_metrics
        }
