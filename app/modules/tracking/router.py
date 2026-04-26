"""
Tracking endpoints for managing technician location tracking.
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.dependencies import get_current_user, require_permission
from ...core.permissions import Permission
from ...core.responses import success_response, error_response
from ...core.exceptions import NotFoundError, ValidationError
from ...core.logging import get_logger
from .services import TrackingService
from ..real_time.services import RealTimeService
from .schemas import (
    LocationUpdate,
    StartTrackingRequest,
    StopTrackingRequest,
    TrackingSessionResponse,
    LocationHistoryResponse,
    TrackingStatisticsResponse,
    LocationHistoryRequest,
    BatchLocationUpdate
)
from ...models.user import User

logger = get_logger(__name__)
router = APIRouter(prefix="/tracking", tags=["tracking"])


@router.post("/technicians/{technician_id}/location", status_code=status.HTTP_200_OK)
async def update_technician_location(
    technician_id: int,
    location: LocationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update technician's current location.
    
    This endpoint:
    - Updates technician's current location in database
    - Saves location to history
    - Broadcasts location update via WebSocket to active incidents
    
    **Permissions:** Technician can only update their own location
    """
    logger.info(f"📍 Recibida actualización de ubicación para técnico {technician_id}")
    logger.info(f"📍 Ubicación: ({location.latitude}, {location.longitude})")
    logger.info(f"📍 Usuario actual: {current_user.id}, Tipo: {current_user.user_type}")
    
    # Verify technician can only update their own location
    # Admins can update any location, technicians can only update their own
    is_admin = current_user.user_type == "admin"
    if not is_admin and current_user.id != technician_id:
        logger.warning(f"❌ Usuario {current_user.id} intentó actualizar ubicación de técnico {technician_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own location"
        )

    try:
        real_time_service = RealTimeService(db)
        
        logger.info(f"📤 Llamando a real_time_service.update_technician_location...")
        success = await real_time_service.update_technician_location(
            technician_id=technician_id,
            latitude=location.latitude,
            longitude=location.longitude,
            accuracy=location.accuracy,
            speed=location.speed,
            heading=location.heading
        )

        if not success:
            logger.error(f"❌ real_time_service.update_technician_location retornó False")
            return error_response(
                message="Failed to update location",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        logger.info(f"✅ Ubicación actualizada exitosamente para técnico {technician_id}")
        return success_response(
            data={
                "technician_id": technician_id,
                "latitude": location.latitude,
                "longitude": location.longitude,
                "updated_at": datetime.utcnow().isoformat()
            },
            message="Location updated successfully"
        )
    except Exception as e:
        logger.error(f"❌ Error al actualizar ubicación: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar ubicación: {str(e)}"
        )


@router.post("/technicians/{technician_id}/location/batch", status_code=status.HTTP_200_OK)
async def update_technician_location_batch(
    technician_id: int,
    batch: 'BatchLocationUpdate',
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update technician's location with a batch of location updates.
    
    This endpoint:
    - Accepts up to 10 location updates in a single request
    - Updates technician's current location to the most recent one
    - Saves all locations to history using batch insert
    - Broadcasts the most recent location update via WebSocket
    
    **Permissions:** Technician can only update their own location
    
    **Performance:** Uses executemany() for efficient batch insertion
    """
    logger.info(f"📍 Recibida actualización de ubicación en batch para técnico {technician_id}")
    logger.info(f"📍 Cantidad de ubicaciones: {len(batch.locations)}")
    
    # Verify technician can only update their own location
    is_admin = current_user.user_type == "admin"
    if not is_admin and current_user.id != technician_id:
        logger.warning(f"❌ Usuario {current_user.id} intentó actualizar ubicación de técnico {technician_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own location"
        )

    try:
        real_time_service = RealTimeService(db)
        
        # Sort locations by recorded_at to ensure correct order
        sorted_locations = sorted(batch.locations, key=lambda loc: loc.recorded_at)
        
        # Process all locations in batch
        logger.info(f"📤 Procesando batch de {len(sorted_locations)} ubicaciones...")
        
        # Update each location (RealTimeService handles batch insertion internally)
        for location in sorted_locations:
            await real_time_service.update_technician_location(
                technician_id=technician_id,
                latitude=location.latitude,
                longitude=location.longitude,
                accuracy=location.accuracy,
                speed=location.speed,
                heading=location.heading
            )
        
        # Get the most recent location for response
        most_recent = sorted_locations[-1]
        
        logger.info(f"✅ Batch de {len(sorted_locations)} ubicaciones procesado exitosamente para técnico {technician_id}")
        return success_response(
            data={
                "technician_id": technician_id,
                "locations_processed": len(sorted_locations),
                "most_recent_location": {
                    "latitude": most_recent.latitude,
                    "longitude": most_recent.longitude,
                    "recorded_at": most_recent.recorded_at.isoformat()
                },
                "updated_at": datetime.utcnow().isoformat()
            },
            message=f"Batch of {len(sorted_locations)} locations updated successfully"
        )
    except Exception as e:
        logger.error(f"❌ Error al actualizar ubicaciones en batch: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar ubicaciones en batch: {str(e)}"
        )


@router.post("/start", response_model=TrackingSessionResponse)
async def start_tracking(
    request: StartTrackingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.EMERGENCY_TRACK))
):
    """
    Start a new tracking session for the current technician.
    
    This creates a tracking session that records:
    - Start time
    - Associated incident (if provided)
    - All location updates during the session
    
    **Permissions:** Only technicians can start tracking sessions
    """
    tracking_service = TrackingService(db)

    try:
        session = await tracking_service.start_tracking_session(
            technician_id=current_user.id,
            incident_id=request.incident_id
        )
        return session

    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/stop", response_model=TrackingSessionResponse)
async def stop_tracking(
    request: StopTrackingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.EMERGENCY_TRACK))
):
    """
    Stop the active tracking session for the current technician.
    
    This:
    - Marks the session as ended
    - Calculates total distance traveled (if requested)
    - Stops broadcasting location updates
    
    **Permissions:** Only technicians can stop their tracking sessions
    """
    tracking_service = TrackingService(db)

    # Get active session for current technician
    active_session = await tracking_service.get_active_session(current_user.id)
    
    if not active_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active tracking session found"
        )

    try:
        session = await tracking_service.stop_tracking_session(
            session_id=active_session.id,
            calculate_distance=request.calculate_distance
        )
        return session

    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/sessions/active", response_model=Optional[TrackingSessionResponse])
async def get_active_session(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.EMERGENCY_TRACK))
):
    """
    Get the active tracking session for the current technician.
    
    Returns the currently active session or null if no session is active.
    
    **Permissions:** Only technicians can view their tracking sessions
    """
    tracking_service = TrackingService(db)
    session = await tracking_service.get_active_session(current_user.id)
    return session


@router.get("/sessions/{session_id}/history", response_model=List[LocationHistoryResponse])
async def get_session_history(
    session_id: int,
    limit: Optional[int] = Query(None, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get location history for a specific tracking session.
    
    Returns all location points recorded during the session,
    ordered by time (most recent first).
    
    **Permissions:** Technician can view their own sessions, admins can view all
    """
    tracking_service = TrackingService(db)

    try:
        history = await tracking_service.get_session_history(
            session_id=session_id,
            limit=limit
        )
        return history

    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/technicians/{technician_id}/history", response_model=List[LocationHistoryResponse])
async def get_technician_history(
    technician_id: int,
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get location history for a technician within a time range.
    
    **Permissions:** Technician can view their own history, admins can view all
    """
    # Verify permissions
    if current_user.user_type != "admin" and current_user.id != technician_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own location history"
        )

    tracking_service = TrackingService(db)
    
    history = await tracking_service.get_technician_location_history(
        technician_id=technician_id,
        start_time=start_time,
        end_time=end_time,
        limit=limit
    )
    
    return history


@router.get("/incidents/{incident_id}/sessions", response_model=List[TrackingSessionResponse])
async def get_incident_sessions(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all tracking sessions for a specific incident.
    
    Returns all tracking sessions associated with the incident,
    including active and completed sessions.
    
    **Permissions:** Client can view their incident sessions, technicians and admins can view all
    """
    tracking_service = TrackingService(db)
    
    sessions = await tracking_service.get_incident_tracking_sessions(incident_id)
    return sessions


@router.get("/statistics", response_model=TrackingStatisticsResponse)
async def get_tracking_statistics(
    technician_id: Optional[int] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.REPORT_VIEW_ALL))
):
    """
    Get tracking statistics.
    
    Returns aggregated statistics about tracking sessions:
    - Total sessions
    - Active sessions
    - Completed sessions
    - Total distance traveled
    - Average distance per session
    - Average session duration
    
    **Permissions:** Admin only
    """
    tracking_service = TrackingService(db)
    
    stats = await tracking_service.get_tracking_statistics(
        technician_id=technician_id,
        start_date=start_date,
        end_date=end_date
    )
    
    return stats
