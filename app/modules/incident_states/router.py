"""
Incident state management endpoints.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.dependencies import get_current_user, require_permission
from ...core.permissions import Permission
from ...core.responses import success_response
from ...core.exceptions import NotFoundError, ValidationError
from .services import IncidentStateService
from .schemas import (
    StateTransitionRequest,
    CancelIncidentRequest,
    ResolveIncidentRequest,
    StateHistoryResponse,
    StateInfoResponse,
    AllowedTransitionsResponse
)
from ...models.user import User

router = APIRouter(prefix="/incidents", tags=["incident-states"])


@router.post("/{incident_id}/transition", status_code=status.HTTP_200_OK)
async def transition_incident_state(
    incident_id: int,
    request: StateTransitionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Transition incident to a new state.
    
    This endpoint:
    - Validates the state transition
    - Updates incident state
    - Creates history record
    - Broadcasts change via WebSocket
    - Sends push notification
    
    **Valid transitions:**
    - pendiente → asignado, cancelado
    - asignado → en_camino, cancelado
    - en_camino → en_sitio, cancelado
    - en_sitio → resuelto, cancelado
    - resuelto → (terminal state)
    - cancelado → (terminal state)
    
    **Permissions:** Workshop staff or admin
    """
    state_service = IncidentStateService(db)

    try:
        incident = await state_service.transition_state(
            incident_id=incident_id,
            new_state=request.new_state,
            changed_by=current_user.id,
            notes=request.notes,
            force=request.force and current_user.user_type == "admin"
        )

        return success_response(
            data={
                "incident_id": incident.id,
                "previous_state": incident.estado_actual,
                "new_state": request.new_state
            },
            message=f"Incident transitioned to {request.new_state}"
        )

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


@router.post("/{incident_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_incident(
    incident_id: int,
    request: CancelIncidentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Cancel an incident.
    
    This is a convenience endpoint that transitions to 'cancelado' state.
    Can be called from any non-terminal state.
    
    **Permissions:** Client (own incidents), workshop staff, or admin
    """
    state_service = IncidentStateService(db)

    try:
        incident = await state_service.cancel_incident(
            incident_id=incident_id,
            cancelled_by=current_user.id,
            reason=request.reason
        )

        return success_response(
            data={
                "incident_id": incident.id,
                "state": incident.estado_actual,
                "cancelled_at": incident.cancelled_at.isoformat() if incident.cancelled_at else None
            },
            message="Incident cancelled successfully"
        )

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


@router.post("/{incident_id}/resolve", status_code=status.HTTP_200_OK)
async def resolve_incident(
    incident_id: int,
    request: ResolveIncidentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.SERVICE_UPDATE_STATUS))
):
    """
    Mark incident as resolved.
    
    This transitions the incident to 'resuelto' state.
    Can only be called from 'en_sitio' state.
    
    **Permissions:** Assigned technician or admin
    """
    state_service = IncidentStateService(db)

    try:
        incident = await state_service.resolve_incident(
            incident_id=incident_id,
            resolved_by=current_user.id,
            resolution_notes=request.resolution_notes
        )

        return success_response(
            data={
                "incident_id": incident.id,
                "state": incident.estado_actual,
                "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None
            },
            message="Incident resolved successfully"
        )

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


@router.get("/{incident_id}/history", response_model=List[StateHistoryResponse])
async def get_state_history(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get state transition history for an incident.
    
    Returns all state changes ordered by date (newest first).
    
    **Permissions:** Client (own incidents), workshop staff, or admin
    """
    state_service = IncidentStateService(db)

    history = await state_service.get_state_history(incident_id)
    return history


@router.get("/{incident_id}/allowed-transitions", response_model=AllowedTransitionsResponse)
async def get_allowed_transitions(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get allowed state transitions for an incident.
    
    Returns the current state and list of valid target states.
    
    **Permissions:** Authenticated user
    """
    state_service = IncidentStateService(db)

    try:
        from sqlalchemy import select
        from ...models.incidente import Incidente

        incident = await db.scalar(
            select(Incidente).where(Incidente.id == incident_id)
        )

        if not incident:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Incident {incident_id} not found"
            )

        allowed = await state_service.get_allowed_transitions(incident_id)
        state_info = state_service.get_state_info(incident.estado_actual)

        return {
            "current_state": incident.estado_actual,
            "allowed_transitions": allowed,
            "state_info": state_info
        }

    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/states", response_model=List[StateInfoResponse])
async def get_all_states(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get information about all incident states.
    
    Returns list of all states with descriptions and allowed transitions.
    
    **Permissions:** Authenticated user
    """
    state_service = IncidentStateService(db)
    return state_service.get_all_states()


@router.get("/{incident_id}/can-transition/{target_state}", status_code=status.HTTP_200_OK)
async def can_transition_to_state(
    incident_id: int,
    target_state: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Check if incident can transition to a specific state.
    
    **Permissions:** Authenticated user
    """
    state_service = IncidentStateService(db)

    can_transition = await state_service.can_transition(incident_id, target_state)

    return success_response(
        data={
            "incident_id": incident_id,
            "target_state": target_state,
            "can_transition": can_transition
        },
        message=f"Transition to {target_state} is {'allowed' if can_transition else 'not allowed'}"
    )
