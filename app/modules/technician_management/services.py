"""
Service for managing technician availability and operations.
"""
from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_

from ...core.logging import get_logger
from ...core.exceptions import NotFoundError, ValidationError
from ...models.technician import Technician
from ...models.incidente import Incidente
from ...models.tracking_session import TrackingSession

logger = get_logger(__name__)


class TechnicianManagementService:
    """
    Service for managing technician availability and status.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def update_availability(
        self,
        technician_id: int,
        is_available: bool
    ) -> Technician:
        """
        Update technician availability status.
        
        Args:
            technician_id: ID of the technician
            is_available: New availability status
            
        Returns:
            Updated technician
            
        Raises:
            NotFoundError: If technician not found
            ValidationError: If technician has active service
        """
        technician = await self.session.scalar(
            select(Technician).where(Technician.id == technician_id)
        )

        if not technician:
            raise NotFoundError(f"Technician {technician_id} not found")

        # If setting to unavailable, check for active services
        if not is_available:
            has_active_service = await self._has_active_service(technician_id)
            if has_active_service:
                raise ValidationError(
                    "Cannot set technician as unavailable while they have an active service"
                )

        technician.is_available = is_available
        technician.updated_at = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(technician)

        logger.info(
            f"Technician {technician_id} availability updated to {is_available}"
        )

        # 🔔 Emit WebSocket event to workshop owner
        try:
            from ...core.websocket_events import emit_to_user, EventTypes
            await emit_to_user(
                user_id=technician.workshop_id,
                event_type=EventTypes.TECHNICIAN_AVAILABILITY_CHANGED,
                data={
                    "technician_id": technician.id,
                    "workshop_id": technician.workshop_id,
                    "first_name": technician.first_name,
                    "last_name": technician.last_name,
                    "is_available": technician.is_available,
                    "is_on_duty": technician.is_on_duty,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
        except Exception as e:
            logger.error(f"Error emitting WebSocket event: {str(e)}")

        return technician

    async def update_online_status(
        self,
        technician_id: int,
        is_online: bool
    ) -> Technician:
        """
        Update technician online status.
        
        Args:
            technician_id: ID of the technician
            is_online: New online status
            
        Returns:
            Updated technician
        """
        technician = await self.session.scalar(
            select(Technician).where(Technician.id == technician_id)
        )

        if not technician:
            raise NotFoundError(f"Technician {technician_id} not found")

        technician.is_online = is_online
        technician.last_seen_at = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(technician)

        return technician

    async def get_available_technicians(
        self,
        workshop_id: int,
        specialty_id: Optional[int] = None
    ) -> List[Technician]:
        """
        Get available technicians for a workshop.
        
        Args:
            workshop_id: ID of the workshop
            specialty_id: Optional filter by specialty
            
        Returns:
            List of available technicians
        """
        query = (
            select(Technician)
            .where(
                and_(
                    Technician.workshop_id == workshop_id,
                    Technician.is_available == True,
                    Technician.is_online == True
                )
            )
        )

        if specialty_id:
            # Filter by specialty (requires join with technician_especialidad)
            from ...models.technician_especialidad import TechnicianEspecialidad
            query = query.join(
                TechnicianEspecialidad,
                TechnicianEspecialidad.technician_id == Technician.id
            ).where(TechnicianEspecialidad.especialidad_id == specialty_id)

        result = await self.session.scalars(query)
        return list(result.all())

    async def get_technician_workload(
        self,
        technician_id: int
    ) -> dict:
        """
        Get current workload for a technician.
        
        Args:
            technician_id: ID of the technician
            
        Returns:
            Dictionary with workload information
        """
        # Count active incidents
        active_incidents = await self.session.scalar(
            select(Incidente)
            .where(
                and_(
                    Incidente.tecnico_id == technician_id,
                    Incidente.estado_actual.in_(["asignado", "en_camino", "en_sitio"])
                )
            )
        )

        # Count active tracking sessions
        active_sessions = await self.session.scalar(
            select(TrackingSession)
            .where(
                and_(
                    TrackingSession.technician_id == technician_id,
                    TrackingSession.is_active == True
                )
            )
        )

        # Get technician info
        technician = await self.session.scalar(
            select(Technician).where(Technician.id == technician_id)
        )

        return {
            "technician_id": technician_id,
            "is_available": technician.is_available if technician else False,
            "is_online": technician.is_online if technician else False,
            "active_incidents": 1 if active_incidents else 0,
            "active_tracking_sessions": 1 if active_sessions else 0,
            "has_active_work": bool(active_incidents or active_sessions)
        }

    async def _has_active_service(self, technician_id: int) -> bool:
        """
        Check if technician has any active service.
        
        Args:
            technician_id: ID of the technician
            
        Returns:
            True if technician has active service
        """
        active_incident = await self.session.scalar(
            select(Incidente)
            .where(
                and_(
                    Incidente.tecnico_id == technician_id,
                    Incidente.estado_actual.in_(["asignado", "en_camino", "en_sitio"])
                )
            )
        )

        return active_incident is not None

    async def get_technician_statistics(
        self,
        technician_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> dict:
        """
        Get statistics for a technician.
        
        Args:
            technician_id: ID of the technician
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            Dictionary with technician statistics
        """
        from sqlalchemy import func

        # Base query for incidents
        query = select(Incidente).where(Incidente.tecnico_id == technician_id)

        if start_date:
            query = query.where(Incidente.created_at >= start_date)
        if end_date:
            query = query.where(Incidente.created_at <= end_date)

        # Total incidents
        total_incidents = await self.session.scalar(
            select(func.count(Incidente.id))
            .where(Incidente.tecnico_id == technician_id)
        )

        # Resolved incidents
        resolved_incidents = await self.session.scalar(
            select(func.count(Incidente.id))
            .where(
                and_(
                    Incidente.tecnico_id == technician_id,
                    Incidente.estado_actual == "resuelto"
                )
            )
        )

        # Cancelled incidents
        cancelled_incidents = await self.session.scalar(
            select(func.count(Incidente.id))
            .where(
                and_(
                    Incidente.tecnico_id == technician_id,
                    Incidente.estado_actual == "cancelado"
                )
            )
        )

        # Active incidents
        active_incidents = await self.session.scalar(
            select(func.count(Incidente.id))
            .where(
                and_(
                    Incidente.tecnico_id == technician_id,
                    Incidente.estado_actual.in_(["asignado", "en_camino", "en_sitio"])
                )
            )
        )

        # Calculate resolution rate
        resolution_rate = (
            (resolved_incidents / total_incidents * 100)
            if total_incidents > 0
            else 0
        )

        return {
            "technician_id": technician_id,
            "total_incidents": total_incidents or 0,
            "resolved_incidents": resolved_incidents or 0,
            "cancelled_incidents": cancelled_incidents or 0,
            "active_incidents": active_incidents or 0,
            "resolution_rate": round(resolution_rate, 2)
        }

    async def get_workshop_technicians(
        self,
        workshop_id: int,
        include_unavailable: bool = True
    ) -> List[Technician]:
        """
        Get all technicians for a workshop.
        
        Args:
            workshop_id: ID of the workshop
            include_unavailable: Whether to include unavailable technicians
            
        Returns:
            List of technicians
        """
        query = select(Technician).where(Technician.workshop_id == workshop_id)

        if not include_unavailable:
            query = query.where(Technician.is_available == True)

        result = await self.session.scalars(query)
        return list(result.all())

    async def assign_specialty(
        self,
        technician_id: int,
        specialty_id: int
    ) -> bool:
        """
        Assign a specialty to a technician.
        
        Args:
            technician_id: ID of the technician
            specialty_id: ID of the specialty
            
        Returns:
            True if assigned successfully
        """
        from ...models.technician_especialidad import TechnicianEspecialidad

        # Check if already assigned
        existing = await self.session.scalar(
            select(TechnicianEspecialidad)
            .where(
                and_(
                    TechnicianEspecialidad.technician_id == technician_id,
                    TechnicianEspecialidad.especialidad_id == specialty_id
                )
            )
        )

        if existing:
            return True  # Already assigned

        # Create new assignment
        assignment = TechnicianEspecialidad(
            technician_id=technician_id,
            especialidad_id=specialty_id
        )

        self.session.add(assignment)
        await self.session.commit()

        logger.info(f"Assigned specialty {specialty_id} to technician {technician_id}")
        return True

    async def remove_specialty(
        self,
        technician_id: int,
        specialty_id: int
    ) -> bool:
        """
        Remove a specialty from a technician.
        
        Args:
            technician_id: ID of the technician
            specialty_id: ID of the specialty
            
        Returns:
            True if removed successfully
        """
        from ...models.technician_especialidad import TechnicianEspecialidad
        from sqlalchemy import delete

        result = await self.session.execute(
            delete(TechnicianEspecialidad)
            .where(
                and_(
                    TechnicianEspecialidad.technician_id == technician_id,
                    TechnicianEspecialidad.especialidad_id == specialty_id
                )
            )
        )

        await self.session.commit()

        removed = result.rowcount > 0
        if removed:
            logger.info(f"Removed specialty {specialty_id} from technician {technician_id}")

        return removed
