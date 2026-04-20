"""
Router para cancelaciones mutuas de incidentes ambiguos.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db_session as get_db
from ...core.dependencies import get_current_user
from ...core.responses import success_response
from ...core.exceptions import NotFoundError, ValidationError, ForbiddenError
from ...models.user import User
from .service import CancellationService
from .schemas import (
    CancellationRequestCreate,
    CancellationResponseRequest,
    CancellationRequestResponse
)

router = APIRouter(prefix="/cancellation", tags=["cancellation"])


@router.post(
    "/incidents/{incident_id}/request",
    response_model=CancellationRequestResponse,
    status_code=status.HTTP_201_CREATED
)
async def request_cancellation(
    incident_id: int,
    request: CancellationRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Solicitar cancelación mutua de un incidente ambiguo.
    
    Esta solicitud requiere que la otra parte (cliente o taller) la acepte.
    Si ambas partes están de acuerdo, el incidente se anula y se busca un nuevo taller.
    
    **Validaciones:**
    - El incidente debe ser ambiguo (es_ambiguo = True)
    - El incidente debe estar asignado o en proceso
    - No debe existir otra solicitud pendiente
    - El motivo debe tener al menos 10 caracteres
    
    **Permisos:** Cliente del incidente o taller asignado
    """
    service = CancellationService(db)
    
    try:
        cancellation_request = await service.request_cancellation(
            incident_id=incident_id,
            user_id=current_user.id,
            user_type=current_user.user_type,
            reason=request.reason
        )
        
        return cancellation_request
        
    except (NotFoundError, ValidationError, ForbiddenError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST if isinstance(e, ValidationError) else
                       status.HTTP_404_NOT_FOUND if isinstance(e, NotFoundError) else
                       status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


@router.post(
    "/requests/{request_id}/respond",
    response_model=CancellationRequestResponse
)
async def respond_to_cancellation(
    request_id: int,
    response: CancellationResponseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Responder a una solicitud de cancelación mutua.
    
    Si se acepta, el incidente se anula automáticamente y el sistema busca un nuevo taller.
    Si se rechaza, la solicitud se marca como rechazada y el servicio continúa normalmente.
    
    **Validaciones:**
    - La solicitud debe estar pendiente
    - No debe haber expirado (24 horas)
    - Solo la otra parte puede responder (no quien solicitó)
    
    **Permisos:** Cliente del incidente o taller asignado (quien no solicitó)
    """
    service = CancellationService(db)
    
    try:
        cancellation_request = await service.respond_to_cancellation(
            request_id=request_id,
            user_id=current_user.id,
            user_type=current_user.user_type,
            accept=response.accept,
            response_message=response.response_message
        )
        
        return cancellation_request
        
    except (NotFoundError, ValidationError, ForbiddenError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST if isinstance(e, ValidationError) else
                       status.HTTP_404_NOT_FOUND if isinstance(e, NotFoundError) else
                       status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


@router.get(
    "/incidents/{incident_id}/pending",
    response_model=CancellationRequestResponse | None
)
async def get_pending_cancellation(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Obtener solicitud de cancelación pendiente para un incidente.
    
    Retorna la solicitud pendiente si existe, o None si no hay ninguna.
    
    **Permisos:** Cliente del incidente o taller asignado
    """
    service = CancellationService(db)
    
    cancellation_request = await service.get_pending_cancellation(incident_id)
    
    return cancellation_request
