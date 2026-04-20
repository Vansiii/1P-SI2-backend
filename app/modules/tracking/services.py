"""
Tracking service for managing technician location tracking sessions.
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, func
from sqlalchemy.orm import selectinload

from ...core.logging import get_logger
from ...core.websocket_events import emit_to_incident_room, EventTypes
from ...models.tracking_session import TrackingSession
from ...models.technician_location_history import TechnicianLocationHistory
from ...models.technician import Technician
from ...models.incidente import Incidente
from ...core.exceptions import NotFoundError, ValidationError

logger = get_logger(__name__)


class TrackingService:
    """
    Service for managing tracking sessions and location history.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def start_tracking_session(
        self,
        technician_id: int,
        incident_id: Optional[int] = None
    ) -> TrackingSession:
        """
        Start a new tracking session for a technician.
        
        Args:
            technician_id: ID of the technician
            incident_id: Optional ID of the incident being tracked
            
        Returns:
            Created tracking session
            
        Raises:
            NotFoundError: If technician or incident not found
            ValidationError: If technician already has an active session
        """
        # Verify technician exists
        technician = await self.session.scalar(
            select(Technician).where(Technician.id == technician_id)
        )
        if not technician:
            raise NotFoundError(f"Technician {technician_id} not found")

        # Verify incident exists if provided
        if incident_id:
            incident = await self.session.scalar(
                select(Incidente).where(Incidente.id == incident_id)
            )
            if not incident:
                raise NotFoundError(f"Incident {incident_id} not found")

        # Check for existing active session
        existing_session = await self.session.scalar(
            select(TrackingSession).where(
                and_(
                    TrackingSession.technician_id == technician_id,
                    TrackingSession.is_active == True
                )
            )
        )
        
        if existing_session:
            raise ValidationError(
                f"Technician {technician_id} already has an active tracking session"
            )

        # Create new tracking session
        tracking_session = TrackingSession(
            technician_id=technician_id,
            incidente_id=incident_id,
            started_at=datetime.utcnow(),
            is_active=True,
            total_distance_km=0.0
        )
        
        self.session.add(tracking_session)
        await self.session.commit()
        await self.session.refresh(tracking_session)

        logger.info(
            f"Started tracking session {tracking_session.id} for technician {technician_id}"
        )
        
        # Emit tracking_started event to incident room if incident is associated
        if incident_id:
            await emit_to_incident_room(
                incident_id=incident_id,
                event_type=EventTypes.TRACKING_STARTED,
                data={
                    "tracking_session_id": tracking_session.id,
                    "technician_id": technician_id,
                    "incident_id": incident_id,
                    "started_at": tracking_session.started_at.isoformat(),
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
            logger.info(f"Emitted tracking_started event for session {tracking_session.id}")
        
        return tracking_session

    async def stop_tracking_session(
        self,
        session_id: int,
        calculate_distance: bool = True
    ) -> TrackingSession:
        """
        Stop an active tracking session.
        
        Args:
            session_id: ID of the tracking session
            calculate_distance: Whether to calculate total distance traveled
            
        Returns:
            Updated tracking session
            
        Raises:
            NotFoundError: If session not found
            ValidationError: If session is not active
        """
        # Get tracking session
        tracking_session = await self.session.scalar(
            select(TrackingSession).where(TrackingSession.id == session_id)
        )
        
        if not tracking_session:
            raise NotFoundError(f"Tracking session {session_id} not found")
        
        if not tracking_session.is_active:
            raise ValidationError(f"Tracking session {session_id} is not active")

        # Calculate total distance if requested
        if calculate_distance:
            total_distance = await self._calculate_session_distance(
                tracking_session.technician_id,
                tracking_session.started_at,
                datetime.utcnow()
            )
            tracking_session.total_distance_km = total_distance

        # Update session
        tracking_session.ended_at = datetime.utcnow()
        tracking_session.is_active = False

        await self.session.commit()
        await self.session.refresh(tracking_session)

        logger.info(
            f"Stopped tracking session {session_id}, "
            f"distance: {tracking_session.total_distance_km} km"
        )
        
        # Emit tracking_ended event to incident room if incident is associated
        if tracking_session.incidente_id:
            await emit_to_incident_room(
                incident_id=tracking_session.incidente_id,
                event_type=EventTypes.TRACKING_ENDED,
                data={
                    "tracking_session_id": tracking_session.id,
                    "technician_id": tracking_session.technician_id,
                    "incident_id": tracking_session.incidente_id,
                    "started_at": tracking_session.started_at.isoformat(),
                    "ended_at": tracking_session.ended_at.isoformat(),
                    "total_distance_km": float(tracking_session.total_distance_km or 0),
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
            logger.info(f"Emitted tracking_ended event for session {session_id}")
        
        return tracking_session

    async def get_active_session(
        self,
        technician_id: int
    ) -> Optional[TrackingSession]:
        """
        Get active tracking session for a technician.
        
        Args:
            technician_id: ID of the technician
            
        Returns:
            Active tracking session or None
        """
        return await self.session.scalar(
            select(TrackingSession).where(
                and_(
                    TrackingSession.technician_id == technician_id,
                    TrackingSession.is_active == True
                )
            )
        )

    async def get_session_history(
        self,
        session_id: int,
        limit: Optional[int] = None
    ) -> List[TechnicianLocationHistory]:
        """
        Get location history for a tracking session.
        
        Args:
            session_id: ID of the tracking session
            limit: Optional limit on number of records
            
        Returns:
            List of location history records
            
        Raises:
            NotFoundError: If session not found
        """
        # Get tracking session
        tracking_session = await self.session.scalar(
            select(TrackingSession).where(TrackingSession.id == session_id)
        )
        
        if not tracking_session:
            raise NotFoundError(f"Tracking session {session_id} not found")

        # Build query
        query = (
            select(TechnicianLocationHistory)
            .where(
                and_(
                    TechnicianLocationHistory.technician_id == tracking_session.technician_id,
                    TechnicianLocationHistory.recorded_at >= tracking_session.started_at
                )
            )
            .order_by(TechnicianLocationHistory.recorded_at.desc())
        )

        # Add end time filter if session is ended
        if tracking_session.ended_at:
            query = query.where(
                TechnicianLocationHistory.recorded_at <= tracking_session.ended_at
            )

        # Add limit if specified
        if limit:
            query = query.limit(limit)

        result = await self.session.scalars(query)
        return list(result.all())

    async def get_technician_location_history(
        self,
        technician_id: int,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[TechnicianLocationHistory]:
        """
        Get location history for a technician within a time range.
        
        Args:
            technician_id: ID of the technician
            start_time: Optional start time filter
            end_time: Optional end time filter
            limit: Maximum number of records to return
            
        Returns:
            List of location history records
        """
        query = (
            select(TechnicianLocationHistory)
            .where(TechnicianLocationHistory.technician_id == technician_id)
            .order_by(TechnicianLocationHistory.recorded_at.desc())
            .limit(limit)
        )

        if start_time:
            query = query.where(TechnicianLocationHistory.recorded_at >= start_time)
        
        if end_time:
            query = query.where(TechnicianLocationHistory.recorded_at <= end_time)

        result = await self.session.scalars(query)
        return list(result.all())

    async def get_incident_tracking_sessions(
        self,
        incident_id: int
    ) -> List[TrackingSession]:
        """
        Get all tracking sessions for an incident.
        
        Args:
            incident_id: ID of the incident
            
        Returns:
            List of tracking sessions
        """
        result = await self.session.scalars(
            select(TrackingSession)
            .where(TrackingSession.incidente_id == incident_id)
            .order_by(TrackingSession.started_at.desc())
        )
        return list(result.all())

    async def _calculate_session_distance(
        self,
        technician_id: int,
        start_time: datetime,
        end_time: datetime
    ) -> float:
        """
        Calculate total distance traveled during a session using Haversine formula.
        
        Args:
            technician_id: ID of the technician
            start_time: Session start time
            end_time: Session end time
            
        Returns:
            Total distance in kilometers
        """
        # Get all location points for the session
        locations = await self.session.scalars(
            select(TechnicianLocationHistory)
            .where(
                and_(
                    TechnicianLocationHistory.technician_id == technician_id,
                    TechnicianLocationHistory.recorded_at >= start_time,
                    TechnicianLocationHistory.recorded_at <= end_time
                )
            )
            .order_by(TechnicianLocationHistory.recorded_at.asc())
        )
        
        location_list = list(locations.all())
        
        if len(location_list) < 2:
            return 0.0

        # Calculate distance between consecutive points
        total_distance = 0.0
        for i in range(1, len(location_list)):
            prev = location_list[i - 1]
            curr = location_list[i]
            
            distance = self._haversine_distance(
                float(prev.latitude),
                float(prev.longitude),
                float(curr.latitude),
                float(curr.longitude)
            )
            total_distance += distance

        return round(total_distance, 2)

    @staticmethod
    def _haversine_distance(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float
    ) -> float:
        """
        Calculate distance between two GPS coordinates using Haversine formula.
        
        Args:
            lat1: Latitude of first point
            lon1: Longitude of first point
            lat2: Latitude of second point
            lon2: Longitude of second point
            
        Returns:
            Distance in kilometers
        """
        from math import radians, sin, cos, sqrt, atan2

        # Earth radius in kilometers
        R = 6371.0

        # Convert to radians
        lat1_rad = radians(lat1)
        lon1_rad = radians(lon1)
        lat2_rad = radians(lat2)
        lon2_rad = radians(lon2)

        # Differences
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        # Haversine formula
        a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        distance = R * c

        return distance

    async def get_tracking_statistics(
        self,
        technician_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> dict:
        """
        Get tracking statistics for technicians.
        
        Args:
            technician_id: Optional filter by technician
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            Dictionary with tracking statistics
        """
        query = select(TrackingSession)

        if technician_id:
            query = query.where(TrackingSession.technician_id == technician_id)
        
        if start_date:
            query = query.where(TrackingSession.started_at >= start_date)
        
        if end_date:
            query = query.where(TrackingSession.started_at <= end_date)

        sessions = await self.session.scalars(query)
        session_list = list(sessions.all())

        # Calculate statistics
        total_sessions = len(session_list)
        active_sessions = sum(1 for s in session_list if s.is_active)
        completed_sessions = total_sessions - active_sessions
        
        total_distance = sum(
            float(s.total_distance_km or 0) 
            for s in session_list 
            if s.total_distance_km
        )
        
        avg_distance = (
            total_distance / completed_sessions 
            if completed_sessions > 0 
            else 0
        )

        # Calculate average session duration
        completed_with_duration = [
            s for s in session_list 
            if s.ended_at and s.started_at
        ]
        
        if completed_with_duration:
            total_duration_seconds = sum(
                (s.ended_at - s.started_at).total_seconds()
                for s in completed_with_duration
            )
            avg_duration_minutes = (
                total_duration_seconds / len(completed_with_duration) / 60
            )
        else:
            avg_duration_minutes = 0

        return {
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "completed_sessions": completed_sessions,
            "total_distance_km": round(total_distance, 2),
            "average_distance_km": round(avg_distance, 2),
            "average_duration_minutes": round(avg_duration_minutes, 2)
        }
