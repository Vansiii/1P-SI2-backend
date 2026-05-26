"""
Service for managing service ratings.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import joinedload

from ...core.logging import get_logger
from ...core.exceptions import NotFoundError, ValidationError, ForbiddenError
from ...models.service_rating import ServiceRating
from ...models.incidente import Incidente
from ...models.client import Client
from ...models.workshop import Workshop
from ...models.technician import Technician
from ...models.audit_log import AuditLog
from ...core.websocket_events import emit_to_user, emit_to_incident_room
from .schemas import (
    RatingCreate,
    RatingResponse,
    RatingWithDetails,
    WorkshopRatingStats,
    TechnicianRatingStats
)

logger = get_logger(__name__)


class RatingService:
    """Service for managing service ratings."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_rating(
        self,
        incident_id: int,
        client_id: int,
        rating_data: RatingCreate,
        ip_address: str,
        user_agent: Optional[str] = None
    ) -> RatingResponse:
        """
        Create a service rating for an incident.
        
        Args:
            incident_id: ID of the incident to rate
            client_id: ID of the client creating the rating
            rating_data: Rating data (rating and optional comment)
            ip_address: IP address of the client
            user_agent: User agent string
            
        Returns:
            Created rating
            
        Raises:
            NotFoundError: If incident not found
            ValidationError: If incident is not in 'resuelto' state or already rated
            ForbiddenError: If client is not the owner of the incident
        """
        # Get incident with relationships
        incident = await self.session.scalar(
            select(Incidente)
            .options(joinedload(Incidente.workshop), joinedload(Incidente.technician))
            .where(Incidente.id == incident_id)
        )

        if not incident:
            raise NotFoundError(f"Incident {incident_id} not found")

        # Validate client ownership
        if incident.client_id != client_id:
            raise ForbiddenError("You can only rate your own incidents")

        # Validate incident state
        if incident.estado_actual != "resuelto":
            raise ValidationError(
                f"Cannot rate incident in state '{incident.estado_actual}'. "
                "Only resolved incidents can be rated."
            )

        # Check if already rated
        existing_rating = await self.session.scalar(
            select(ServiceRating).where(ServiceRating.incident_id == incident_id)
        )

        if existing_rating:
            raise ValidationError("This incident has already been rated")

        # Validate workshop and technician exist
        if not incident.taller_id:
            raise ValidationError("Incident has no assigned workshop")

        # Create rating
        rating = ServiceRating(
            incident_id=incident_id,
            client_id=client_id,
            workshop_id=incident.taller_id,
            technician_id=incident.tecnico_id,
            rating=rating_data.rating,
            comment=rating_data.comment
        )

        self.session.add(rating)
        await self.session.flush()

        # Create audit log
        audit_log = AuditLog(
            user_id=client_id,
            action="rating_created",
            resource_type="service_rating",
            resource_id=rating.id,
            ip_address=ip_address,
            user_agent=user_agent,
            details=f"Client rated incident {incident_id} with {rating_data.rating} stars"
        )
        self.session.add(audit_log)

        await self.session.commit()
        await self.session.refresh(rating)

        logger.info(
            f"Rating created: incident_id={incident_id}, client_id={client_id}, "
            f"rating={rating_data.rating}, workshop_id={incident.taller_id}"
        )

        # Emit WebSocket events
        await self._emit_rating_events(rating, incident)

        return RatingResponse.model_validate(rating)

    async def get_incident_rating(self, incident_id: int) -> Optional[RatingResponse]:
        """
        Get rating for a specific incident.
        
        Args:
            incident_id: ID of the incident
            
        Returns:
            Rating if exists, None otherwise
        """
        rating = await self.session.scalar(
            select(ServiceRating).where(ServiceRating.incident_id == incident_id)
        )

        if not rating:
            return None

        return RatingResponse.model_validate(rating)

    async def get_workshop_ratings(
        self,
        workshop_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> list[RatingWithDetails]:
        """
        Get all ratings for a workshop with details.
        
        Args:
            workshop_id: ID of the workshop
            limit: Maximum number of ratings to return
            offset: Number of ratings to skip
            
        Returns:
            List of ratings with details
        """
        result = await self.session.execute(
            select(ServiceRating)
            .options(
                joinedload(ServiceRating.client),
                joinedload(ServiceRating.technician),
                joinedload(ServiceRating.incident)
            )
            .where(ServiceRating.workshop_id == workshop_id)
            .order_by(ServiceRating.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        ratings = result.scalars().all()
        return [self._build_rating_with_details(rating) for rating in ratings]

    async def get_workshop_rating_stats(self, workshop_id: int) -> WorkshopRatingStats:
        """
        Get rating statistics for a workshop.
        
        Args:
            workshop_id: ID of the workshop
            
        Returns:
            Workshop rating statistics
        """
        # Get workshop
        workshop = await self.session.scalar(
            select(Workshop).where(Workshop.id == workshop_id)
        )

        if not workshop:
            raise NotFoundError(f"Workshop {workshop_id} not found")

        # Get total ratings and average
        stats = await self.session.execute(
            select(
                func.count(ServiceRating.id).label('total'),
                func.avg(ServiceRating.rating).label('average')
            )
            .where(ServiceRating.workshop_id == workshop_id)
        )
        row = stats.first()
        total_ratings = row.total or 0
        average_rating = float(row.average) if row.average else 0.0

        # Get rating distribution
        distribution_result = await self.session.execute(
            select(
                ServiceRating.rating,
                func.count(ServiceRating.id).label('count')
            )
            .where(ServiceRating.workshop_id == workshop_id)
            .group_by(ServiceRating.rating)
        )
        
        rating_distribution = {i: 0 for i in range(1, 6)}
        for row in distribution_result:
            rating_distribution[row.rating] = row.count

        # Get recent ratings
        recent_ratings = await self.get_workshop_ratings(workshop_id, limit=10)

        return WorkshopRatingStats(
            workshop_id=workshop_id,
            workshop_name=workshop.workshop_name,
            total_ratings=total_ratings,
            average_rating=round(average_rating, 2),
            rating_distribution=rating_distribution,
            recent_ratings=recent_ratings
        )

    async def get_technician_rating_stats(
        self,
        technician_id: int
    ) -> TechnicianRatingStats:
        """
        Get rating statistics for a technician.
        
        Args:
            technician_id: ID of the technician
            
        Returns:
            Technician rating statistics
        """
        # Get technician
        technician = await self.session.scalar(
            select(Technician).where(Technician.id == technician_id)
        )

        if not technician:
            raise NotFoundError(f"Technician {technician_id} not found")

        # Get total ratings and average
        stats = await self.session.execute(
            select(
                func.count(ServiceRating.id).label('total'),
                func.avg(ServiceRating.rating).label('average')
            )
            .where(ServiceRating.technician_id == technician_id)
        )
        row = stats.first()
        total_ratings = row.total or 0
        average_rating = float(row.average) if row.average else 0.0

        # Get rating distribution
        distribution_result = await self.session.execute(
            select(
                ServiceRating.rating,
                func.count(ServiceRating.id).label('count')
            )
            .where(ServiceRating.technician_id == technician_id)
            .group_by(ServiceRating.rating)
        )
        
        rating_distribution = {i: 0 for i in range(1, 6)}
        for row in distribution_result:
            rating_distribution[row.rating] = row.count

        # Get recent ratings
        result = await self.session.execute(
            select(ServiceRating)
            .options(
                joinedload(ServiceRating.client),
                joinedload(ServiceRating.workshop),
                joinedload(ServiceRating.incident)
            )
            .where(ServiceRating.technician_id == technician_id)
            .order_by(ServiceRating.created_at.desc())
            .limit(10)
        )
        
        ratings = result.scalars().all()
        recent_ratings = [self._build_rating_with_details(rating) for rating in ratings]

        technician_name = f"{technician.first_name} {technician.last_name}"

        return TechnicianRatingStats(
            technician_id=technician_id,
            technician_name=technician_name,
            total_ratings=total_ratings,
            average_rating=round(average_rating, 2),
            rating_distribution=rating_distribution,
            recent_ratings=recent_ratings
        )

    def _build_rating_with_details(self, rating: ServiceRating) -> RatingWithDetails:
        """Build RatingWithDetails from ServiceRating with loaded relationships."""
        client_name = None
        if rating.client:
            client_name = f"{rating.client.first_name} {rating.client.last_name}"

        workshop_name = None
        if rating.workshop:
            workshop_name = rating.workshop.workshop_name

        technician_name = None
        if rating.technician:
            technician_name = f"{rating.technician.first_name} {rating.technician.last_name}"

        incident_description = None
        if rating.incident:
            incident_description = rating.incident.descripcion[:100]

        return RatingWithDetails(
            id=rating.id,
            incident_id=rating.incident_id,
            client_id=rating.client_id,
            workshop_id=rating.workshop_id,
            technician_id=rating.technician_id,
            rating=rating.rating,
            comment=rating.comment,
            created_at=rating.created_at,
            updated_at=rating.updated_at,
            client_name=client_name,
            workshop_name=workshop_name,
            technician_name=technician_name,
            incident_description=incident_description
        )

    async def _emit_rating_events(self, rating: ServiceRating, incident: Incidente):
        """Emit WebSocket events for new rating."""
        try:
            # Notify workshop
            await emit_to_user(
                user_id=rating.workshop_id,
                event_type="rating_received",
                data={
                    "rating_id": rating.id,
                    "incident_id": rating.incident_id,
                    "rating": rating.rating,
                    "comment": rating.comment,
                    "created_at": rating.created_at.isoformat()
                }
            )

            # Notify technician if assigned
            if rating.technician_id:
                await emit_to_user(
                    user_id=rating.technician_id,
                    event_type="rating_received",
                    data={
                        "rating_id": rating.id,
                        "incident_id": rating.incident_id,
                        "rating": rating.rating,
                        "comment": rating.comment,
                        "created_at": rating.created_at.isoformat()
                    }
                )

            # Notify incident room
            await emit_to_incident_room(
                incident_id=rating.incident_id,
                event_type="incident_rated",
                data={
                    "rating_id": rating.id,
                    "incident_id": rating.incident_id,
                    "rating": rating.rating,
                    "has_comment": rating.comment is not None
                }
            )

        except Exception as e:
            logger.error(f"Failed to emit rating events: {str(e)}", exc_info=True)
