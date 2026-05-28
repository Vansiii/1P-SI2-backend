from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import get_current_user_payload
from app.core.responses import create_success_response
from .service import WorkshopSelectionService
from .schemas import SelectWorkshopRequest

router = APIRouter(prefix="/incidentes", tags=["Workshop Selection"])


@router.get("/{incident_id}/compatible-workshops")
async def get_compatible_workshops(
    incident_id: int,
    radius_km: float | None = Query(default=None, ge=1, le=200, description="Radio de busqueda en km"),
    user_payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_db_session),
):
    client_id = int(user_payload["sub"])
    service = WorkshopSelectionService(session)
    try:
        workshops = await service.get_compatible_workshops(
            incident_id, client_id, radius_km
        )
        return create_success_response(
            data=workshops,
            message=f"{len(workshops)} talleres compatibles encontrados",
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{incident_id}/compatible-workshops/{workshop_id}")
async def get_workshop_detail(
    incident_id: int,
    workshop_id: int,
    user_payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_db_session),
):
    client_id = int(user_payload["sub"])
    service = WorkshopSelectionService(session)
    try:
        workshops = await service.get_compatible_workshops(incident_id, client_id)
        match = next((w for w in workshops if w["workshop_id"] == workshop_id), None)
        if not match:
            raise HTTPException(status_code=404, detail="Taller no encontrado en la lista de compatibles")
        profile = await service.get_workshop_profile(workshop_id)
        match["schedules"] = profile.get("schedules", []) if profile else []
        match["active_services"] = profile.get("active_services", []) if profile else []
        return create_success_response(data=match, message="Detalle del taller")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{incident_id}/select-workshop")
async def select_workshop(
    incident_id: int,
    body: SelectWorkshopRequest,
    user_payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_db_session),
):
    client_id = int(user_payload["sub"])
    service = WorkshopSelectionService(session)
    try:
        result = await service.select_workshop(
            incident_id, body.workshop_id, client_id
        )
        return create_success_response(data=result, message=result["message"])
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/{incident_id}/assignment-history/{workshop_id}")
async def get_assignment_history(
    incident_id: int,
    workshop_id: int,
    user_payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_db_session),
):
    client_id = int(user_payload["sub"])
    service = WorkshopSelectionService(session)
    history = await service.get_assignment_history(incident_id, workshop_id, client_id)
    return create_success_response(data=history, message=f"{len(history)} intentos de asignación")


# === Perfil publico del taller ===

public_workshop_router = APIRouter(prefix="/workshops", tags=["Workshop - Public"])


@public_workshop_router.get("/{workshop_id}/public-profile")
async def get_workshop_public_profile(
    workshop_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    service = WorkshopSelectionService(session)
    profile = await service.get_workshop_profile(workshop_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Taller no encontrado o no disponible")
    return create_success_response(data=profile, message="Perfil del taller")
