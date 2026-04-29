"""
Service for calculating system metrics and statistics.
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

from ...core.logging import get_logger
from ...core.event_publisher import EventPublisher
from ...shared.schemas.events.dashboard import DashboardMetricsUpdatedEvent
from ...models.incidente import Incidente
from ...models.technician import Technician
from ...models.workshop import Workshop
from ...models.tracking_session import TrackingSession
from ...models.assignment_attempt import AssignmentAttempt

logger = get_logger(__name__)


class MetricsService:
    """
    Service for calculating system metrics and generating reports.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_naive_utc(self, dt: Optional[datetime]) -> Optional[datetime]:
        """Normalize datetime to naive UTC."""
        if dt is None:
            return None
        from datetime import timezone
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    async def get_workshop_metrics(
        self,
        workshop_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """
        Get metrics for a specific workshop.
        
        Args:
            workshop_id: ID of the workshop
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            Dictionary with workshop metrics
        """
        # Default to last 30 days if no dates provided
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        start_date = self._to_naive_utc(start_date)
        end_date = self._to_naive_utc(end_date)

        # Total incidents assigned to workshop
        total_incidents = await self.session.scalar(
            select(func.count(Incidente.id))
            .where(
                and_(
                    Incidente.taller_id == workshop_id,
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date
                )
            )
        )

        # Resolved incidents
        resolved_incidents = await self.session.scalar(
            select(func.count(Incidente.id))
            .where(
                and_(
                    Incidente.taller_id == workshop_id,
                    Incidente.estado_actual == "resuelto",
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date
                )
            )
        )

        # Cancelled incidents
        cancelled_incidents = await self.session.scalar(
            select(func.count(Incidente.id))
            .where(
                and_(
                    Incidente.taller_id == workshop_id,
                    Incidente.estado_actual == "cancelado",
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date
                )
            )
        )

        # Active incidents
        active_incidents = await self.session.scalar(
            select(func.count(Incidente.id))
            .where(
                and_(
                    Incidente.taller_id == workshop_id,
                    Incidente.estado_actual.in_(["asignado", "en_camino", "en_sitio"])
                )
            )
        )

        # Calculate average response time (time from created to assigned)
        avg_response_time = await self.session.scalar(
            select(func.avg(
                func.extract('epoch', Incidente.assigned_at - Incidente.created_at) / 60
            ))
            .where(
                and_(
                    Incidente.taller_id == workshop_id,
                    Incidente.assigned_at.isnot(None),
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date
                )
            )
        )

        # Calculate average resolution time (time from assigned to resolved)
        avg_resolution_time = await self.session.scalar(
            select(func.avg(
                func.extract('epoch', Incidente.resolved_at - Incidente.assigned_at) / 60
            ))
            .where(
                and_(
                    Incidente.taller_id == workshop_id,
                    Incidente.resolved_at.isnot(None),
                    Incidente.assigned_at.isnot(None),
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date
                )
            )
        )

        # Calculate resolution rate
        resolution_rate = (
            (resolved_incidents / total_incidents * 100)
            if total_incidents > 0
            else 0
        )

        # Get number of active technicians
        active_technicians = await self.session.scalar(
            select(func.count(Technician.id))
            .where(
                and_(
                    Technician.workshop_id == workshop_id,
                    Technician.is_available == True,
                    Technician.is_online == True
                )
            )
        )

        return {
            "workshop_id": workshop_id,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "incidents": {
                "total": total_incidents or 0,
                "resolved": resolved_incidents or 0,
                "cancelled": cancelled_incidents or 0,
                "active": active_incidents or 0,
                "resolution_rate": round(resolution_rate, 2)
            },
            "performance": {
                "avg_response_time_minutes": round(avg_response_time or 0, 2),
                "avg_resolution_time_minutes": round(avg_resolution_time or 0, 2)
            },
            "technicians": {
                "active": active_technicians or 0
            }
        }

    async def get_technician_metrics(
        self,
        technician_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """
        Get metrics for a specific technician.
        
        Args:
            technician_id: ID of the technician
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            Dictionary with technician metrics
        """
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)
            
        start_date = self._to_naive_utc(start_date)
        end_date = self._to_naive_utc(end_date)

        # Total incidents
        total_incidents = await self.session.scalar(
            select(func.count(Incidente.id))
            .where(
                and_(
                    Incidente.tecnico_id == technician_id,
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date
                )
            )
        )

        # Resolved incidents
        resolved_incidents = await self.session.scalar(
            select(func.count(Incidente.id))
            .where(
                and_(
                    Incidente.tecnico_id == technician_id,
                    Incidente.estado_actual == "resuelto",
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date
                )
            )
        )

        # Total distance traveled
        total_distance = await self.session.scalar(
            select(func.sum(TrackingSession.total_distance_km))
            .where(
                and_(
                    TrackingSession.technician_id == technician_id,
                    TrackingSession.started_at >= start_date,
                    TrackingSession.started_at <= end_date
                )
            )
        )

        # Average resolution time
        avg_resolution_time = await self.session.scalar(
            select(func.avg(
                func.extract('epoch', Incidente.resolved_at - Incidente.assigned_at) / 60
            ))
            .where(
                and_(
                    Incidente.tecnico_id == technician_id,
                    Incidente.resolved_at.isnot(None),
                    Incidente.assigned_at.isnot(None),
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date
                )
            )
        )

        resolution_rate = (
            (resolved_incidents / total_incidents * 100)
            if total_incidents > 0
            else 0
        )

        return {
            "technician_id": technician_id,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "incidents": {
                "total": total_incidents or 0,
                "resolved": resolved_incidents or 0,
                "resolution_rate": round(resolution_rate, 2)
            },
            "performance": {
                "avg_resolution_time_minutes": round(avg_resolution_time or 0, 2),
                "total_distance_km": round(total_distance or 0, 2)
            }
        }

    async def get_system_metrics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """
        Get global system metrics.
        
        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            Dictionary with system-wide metrics
        """
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        start_date = self._to_naive_utc(start_date)
        end_date = self._to_naive_utc(end_date)

        # Total incidents
        total_incidents = await self.session.scalar(
            select(func.count(Incidente.id))
            .where(
                and_(
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date
                )
            )
        )

        # Incidents by state
        incidents_by_state = {}
        states = ["pendiente", "asignado", "en_camino", "en_sitio", "resuelto", "cancelado"]
        
        for state in states:
            count = await self.session.scalar(
                select(func.count(Incidente.id))
                .where(
                    and_(
                        Incidente.estado_actual == state,
                        Incidente.created_at >= start_date,
                        Incidente.created_at <= end_date
                    )
                )
            )
            incidents_by_state[state] = count or 0

        # Active workshops
        active_workshops = await self.session.scalar(
            select(func.count(Workshop.id))
            .where(Workshop.is_active == True)
        )

        # Active technicians
        active_technicians = await self.session.scalar(
            select(func.count(Technician.id))
            .where(
                and_(
                    Technician.is_available == True,
                    Technician.is_online == True
                )
            )
        )

        # Assignment success rate
        total_assignments = await self.session.scalar(
            select(func.count(AssignmentAttempt.id))
            .where(
                and_(
                    AssignmentAttempt.created_at >= start_date,
                    AssignmentAttempt.created_at <= end_date
                )
            )
        )

        successful_assignments = await self.session.scalar(
            select(func.count(AssignmentAttempt.id))
            .where(
                and_(
                    AssignmentAttempt.status == "accepted",
                    AssignmentAttempt.created_at >= start_date,
                    AssignmentAttempt.created_at <= end_date
                )
            )
        )

        assignment_success_rate = (
            (successful_assignments / total_assignments * 100)
            if total_assignments > 0
            else 0
        )

        # Average response time
        avg_response_time = await self.session.scalar(
            select(func.avg(
                func.extract('epoch', Incidente.assigned_at - Incidente.created_at) / 60
            ))
            .where(
                and_(
                    Incidente.assigned_at.isnot(None),
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date
                )
            )
        )

        return {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "incidents": {
                "total": total_incidents or 0,
                "by_state": incidents_by_state
            },
            "resources": {
                "active_workshops": active_workshops or 0,
                "active_technicians": active_technicians or 0
            },
            "performance": {
                "avg_response_time_minutes": round(avg_response_time or 0, 2),
                "assignment_success_rate": round(assignment_success_rate, 2)
            }
        }

    async def get_incidents_by_category(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Get incident count grouped by category.
        
        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            List of category statistics
        """
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        start_date = self._to_naive_utc(start_date)
        end_date = self._to_naive_utc(end_date)

        from ...models.categoria import Categoria

        result = await self.session.execute(
            select(
                Incidente.categoria_ia,
                func.count(Incidente.id).label('count')
            )
            .where(
                and_(
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date,
                    Incidente.categoria_ia.isnot(None)
                )
            )
            .group_by(Incidente.categoria_ia)
            .order_by(func.count(Incidente.id).desc())
        )

        return [
            {"category_name": row[0] or "General", "count": row[1]}
            for row in result.all()
        ]

    async def calculate_metrics(self) -> Dict:
        """
        Calculate current dashboard metrics for real-time updates.
        
        Returns:
            Dictionary with current system metrics
        """
        now = datetime.utcnow()
        today_start = datetime(now.year, now.month, now.day)
        
        # Total incidents (all time)
        total_incidents = await self.session.scalar(
            select(func.count(Incidente.id))
        ) or 0
        
        # Active incidents (not resolved or cancelled)
        active_incidents = await self.session.scalar(
            select(func.count(Incidente.id))
            .where(
                Incidente.estado_actual.in_([
                    "pendiente", "asignado", "en_camino", "en_sitio"
                ])
            )
        ) or 0
        
        # Completed today
        completed_today = await self.session.scalar(
            select(func.count(Incidente.id))
            .where(
                and_(
                    Incidente.estado_actual == "resuelto",
                    Incidente.resolved_at >= today_start
                )
            )
        ) or 0
        
        # Average response time (last 24 hours)
        avg_response_time = await self.session.scalar(
            select(func.avg(
                func.extract('epoch', Incidente.assigned_at - Incidente.created_at) / 60
            ))
            .where(
                and_(
                    Incidente.assigned_at.isnot(None),
                    Incidente.created_at >= now - timedelta(hours=24)
                )
            )
        )
        
        # Active technicians (online and available)
        active_technicians = await self.session.scalar(
            select(func.count(Technician.id))
            .where(
                and_(
                    Technician.is_available == True,
                    Technician.is_online == True
                )
            )
        ) or 0
        
        return {
            "total_incidents": total_incidents,
            "active_incidents": active_incidents,
            "completed_today": completed_today,
            "avg_response_time": round(avg_response_time, 2) if avg_response_time else None,
            "active_technicians": active_technicians
        }
    
    async def publish_metrics_update(self) -> None:
        """
        Calculate and publish dashboard metrics update event.
        
        This method should be called periodically (e.g., every 1 minute)
        to update dashboard metrics in real-time.
        """
        try:
            metrics = await self.calculate_metrics()
            
            # Create and publish event
            event = DashboardMetricsUpdatedEvent(
                total_incidents=metrics["total_incidents"],
                active_incidents=metrics["active_incidents"],
                completed_today=metrics["completed_today"],
                avg_response_time=metrics["avg_response_time"],
                active_technicians=metrics["active_technicians"]
            )
            
            await EventPublisher.publish(self.session, event)
            await self.session.commit()
            
            logger.debug(
                f"✅ Dashboard metrics updated: "
                f"total={metrics['total_incidents']}, "
                f"active={metrics['active_incidents']}, "
                f"completed_today={metrics['completed_today']}"
            )
            
        except Exception as e:
            logger.error(
                f"❌ Error publishing dashboard metrics: {str(e)}",
                exc_info=True
            )
