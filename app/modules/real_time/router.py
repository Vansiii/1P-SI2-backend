"""
Real-time API endpoints for testing WebSocket integration.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional

from ...core.database import get_db_session
from ...shared.dependencies.auth import get_current_user, get_current_technician
from .services import RealTimeService
from ...models.user import User
from ...models.technician import Technician

router = APIRouter()


class LocationUpdateRequest(BaseModel):
    """Request for technician location update."""
    latitude: float = Field(..., ge=-90, le=90, description="GPS latitude")
    longitude: float = Field(..., ge=-180, le=180, description="GPS longitude")
    accuracy: Optional[float] = Field(None, ge=0, description="GPS accuracy in meters")
    speed: Optional[float] = Field(None, ge=0, description="Speed in km/h")
    heading: Optional[float] = Field(None, ge=0, lt=360, description="Direction in degrees")


class IncidentStatusUpdateRequest(BaseModel):
    """Request for incident status update."""
    new_status: str = Field(..., description="New status: pendiente, asignado, en_proceso, resuelto, cancelado")
    notes: Optional[str] = Field(None, max_length=500, description="Optional notes about the change")


class TechnicianAssignmentRequest(BaseModel):
    """Request for technician assignment."""
    technician_id: int = Field(..., description="ID of the technician to assign")


class ChatMessageRequest(BaseModel):
    """Request for chat message."""
    message: str = Field(..., min_length=1, max_length=1000, description="Message text")


@router.post("/technicians/location")
async def update_technician_location(
    request: LocationUpdateRequest,
    current_technician: Technician = Depends(get_current_technician),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Update technician's current location and broadcast to active incidents.
    
    This endpoint allows technicians to update their GPS location,
    which will be automatically broadcast to clients tracking their incidents.
    """
    real_time_service = RealTimeService(session)
    
    success = await real_time_service.update_technician_location(
        technician_id=current_technician.id,
        latitude=request.latitude,
        longitude=request.longitude,
        accuracy=request.accuracy,
        speed=request.speed,
        heading=request.heading
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating location"
        )
    
    return {
        "message": "Location updated successfully",
        "technician_id": current_technician.id,
        "location": {
            "latitude": request.latitude,
            "longitude": request.longitude,
            "accuracy": request.accuracy,
            "speed": request.speed,
            "heading": request.heading
        }
    }


@router.put("/incidents/{incident_id}/status")
async def update_incident_status(
    incident_id: int,
    request: IncidentStatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Update incident status and notify all participants via WebSocket.
    
    This endpoint allows authorized users to change incident status,
    which will be broadcast to all connected users in the incident room.
    """
    real_time_service = RealTimeService(session)
    
    success = await real_time_service.update_incident_status(
        incident_id=incident_id,
        new_status=request.new_status,
        changed_by=current_user.id,
        notes=request.notes
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating incident status"
        )
    
    return {
        "message": "Incident status updated successfully",
        "incident_id": incident_id,
        "new_status": request.new_status,
        "changed_by": current_user.id
    }


@router.post("/incidents/{incident_id}/assign")
async def assign_technician(
    incident_id: int,
    request: TechnicianAssignmentRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Assign technician to incident and notify all parties.
    
    This endpoint assigns a technician to an incident and broadcasts
    the assignment to all relevant users via WebSocket.
    """
    real_time_service = RealTimeService(session)
    
    success = await real_time_service.assign_technician_to_incident(
        incident_id=incident_id,
        technician_id=request.technician_id,
        assigned_by=current_user.id
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error assigning technician"
        )
    
    return {
        "message": "Technician assigned successfully",
        "incident_id": incident_id,
        "technician_id": request.technician_id,
        "assigned_by": current_user.id
    }


@router.post("/incidents/{incident_id}/arrived")
async def notify_technician_arrived(
    incident_id: int,
    current_technician: Technician = Depends(get_current_technician),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Notify that technician has arrived at incident location.
    
    This endpoint allows technicians to notify when they arrive
    at the incident location, updating status and notifying the client.
    """
    real_time_service = RealTimeService(session)
    
    success = await real_time_service.notify_technician_arrived(
        incident_id=incident_id,
        technician_id=current_technician.id
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error notifying arrival"
        )
    
    return {
        "message": "Arrival notification sent successfully",
        "incident_id": incident_id,
        "technician_id": current_technician.id
    }


@router.post("/incidents/{incident_id}/chat")
async def send_chat_message(
    incident_id: int,
    request: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Send chat message to incident participants.
    
    This endpoint allows users to send messages in incident chat,
    which will be broadcast to all connected users in the incident room.
    """
    real_time_service = RealTimeService(session)
    
    success = await real_time_service.send_chat_message(
        incident_id=incident_id,
        sender_id=current_user.id,
        message=request.message
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error sending message"
        )
    
    return {
        "message": "Chat message sent successfully",
        "incident_id": incident_id,
        "sender_id": current_user.id,
        "text": request.message
    }


@router.get("/stats")
async def get_real_time_stats(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Get real-time connection statistics.
    
    This endpoint provides information about active WebSocket connections
    and incident rooms for monitoring purposes.
    """
    real_time_service = RealTimeService(session)
    stats = await real_time_service.get_connection_stats()
    
    return {
        "message": "Real-time statistics retrieved successfully",
        "stats": stats
    }