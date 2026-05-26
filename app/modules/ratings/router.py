"""
Router for service ratings endpoints.
"""
from typing import Annotated
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.dependencies import get_current_user, require_role
from ...core.permissions import UserRole
from ...models.user import User
from ...core.responses import success_response
from .services import RatingService
from .schemas import RatingCreate, RatingResponse, WorkshopRatingStats, TechnicianRatingStats

router = APIRouter(prefix="/ratings", tags=["ratings"])


@router.post(
    "/incidents/{incident_id}",
    response_model=RatingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create rating for incident",
    description="Client rates the service received for a resolved incident"
)
async def create_incident_rating(
    incident_id: int,
    rating_data: RatingCreate,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Create a service rating for an incident.
    
    Requirements:
    - User must be a client
    - Client must be the owner of the incident
    - Incident must be in 'resuelto' state
    - Incident must not have been rated before
    - Rating must be between 1 and 5
    """
    # Verify user is a client
    if current_user.user_type != 'client':
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only clients can rate services"
        )
    
    service = RatingService(db)
    
    # Get client IP and user agent
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent")
    
    rating = await service.create_rating(
        incident_id=incident_id,
        client_id=current_user.id,
        rating_data=rating_data,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    return success_response(
        data=rating,
        message="Rating created successfully"
    )


@router.get(
    "/incidents/{incident_id}",
    response_model=RatingResponse | None,
    summary="Get rating for incident",
    description="Get the rating for a specific incident if it exists"
)
async def get_incident_rating(
    incident_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Get the rating for a specific incident.
    
    Returns None if the incident has not been rated yet.
    """
    service = RatingService(db)
    rating = await service.get_incident_rating(incident_id)
    
    return success_response(
        data=rating,
        message="Rating retrieved successfully" if rating else "No rating found"
    )


@router.get(
    "/workshops/{workshop_id}/stats",
    response_model=WorkshopRatingStats,
    summary="Get workshop rating statistics",
    description="Get rating statistics and recent ratings for a workshop"
)
async def get_workshop_rating_stats(
    workshop_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Get rating statistics for a workshop.
    
    Includes:
    - Total number of ratings
    - Average rating
    - Rating distribution (1-5 stars)
    - Recent ratings with details
    """
    service = RatingService(db)
    stats = await service.get_workshop_rating_stats(workshop_id)
    
    return success_response(
        data=stats,
        message="Workshop rating statistics retrieved successfully"
    )


@router.get(
    "/technicians/{technician_id}/stats",
    response_model=TechnicianRatingStats,
    summary="Get technician rating statistics",
    description="Get rating statistics and recent ratings for a technician"
)
async def get_technician_rating_stats(
    technician_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Get rating statistics for a technician.
    
    Includes:
    - Total number of ratings
    - Average rating
    - Rating distribution (1-5 stars)
    - Recent ratings with details
    """
    service = RatingService(db)
    stats = await service.get_technician_rating_stats(technician_id)
    
    return success_response(
        data=stats,
        message="Technician rating statistics retrieved successfully"
    )


@router.get(
    "/admin/all",
    summary="Get all ratings (Admin only)",
    description="Get all ratings with pagination for admin dashboard",
    dependencies=[Depends(require_role(UserRole.ADMINISTRATOR))]
)
async def get_all_ratings_admin(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
    offset: int = 0
):
    """
    Get all ratings with pagination (admin only).
    
    Useful for admin dashboard and reporting.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import joinedload
    from ...models.service_rating import ServiceRating
    
    result = await db.execute(
        select(ServiceRating)
        .options(
            joinedload(ServiceRating.client),
            joinedload(ServiceRating.workshop),
            joinedload(ServiceRating.technician),
            joinedload(ServiceRating.incident)
        )
        .order_by(ServiceRating.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    
    ratings = result.scalars().all()
    service = RatingService(db)
    ratings_with_details = [service._build_rating_with_details(rating) for rating in ratings]
    
    return success_response(
        data=ratings_with_details,
        message=f"Retrieved {len(ratings_with_details)} ratings"
    )
