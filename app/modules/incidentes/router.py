"""
Router para gestión de incidentes/emergencias vehiculares.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import NotFoundException, get_db_session, get_logger
from ...core.responses import create_success_response
from ...core.permissions import Permission
from ...core.dependencies import require_any_permission, require_permission
from ...shared.dependencies.auth import get_current_user
from ...models.user import User
from .schemas import (
    IncidenteCreateRequest,
    IncidenteResponse,
    IncidenteDetailResponse,
    IncidenteUpdateStatusRequest,
    EvidenciaResponse,
    EvidenciaImagenResponse,
    EvidenciaAudioResponse,
)
from .service import IncidenteService
from .ai_service import IncidentAIService
from pydantic import BaseModel, Field

class AcceptIncidenteRequest(BaseModel):
    """Request para aceptar un incidente."""
    pass  # Por ahora no necesita parámetros adicionales

class RejectIncidenteRequest(BaseModel):
    """Request para rechazar un incidente."""
    motivo: str = Field(..., min_length=10, max_length=500, description="Motivo del rechazo")

logger = get_logger(__name__)

router = APIRouter(prefix="/incidentes", tags=["Incidentes"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=IncidenteResponse,
    summary="Reportar emergencia vehicular",
    description="Crear un nuevo reporte de emergencia vehicular con evidencias",
    dependencies=[Depends(require_permission(Permission.EMERGENCY_CREATE))],
)
async def create_incidente(
    request: IncidenteCreateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Reportar una emergencia vehicular."""
    # Verificar que el usuario es un cliente
    if current_user.user_type != "client":
        from ...core import ForbiddenException
        raise ForbiddenException("Solo los clientes pueden reportar emergencias")
    
    service = IncidenteService(session)
    incidente = await service.create_incidente(current_user.id, request)
    
    return create_success_response(
        data=IncidenteResponse.model_validate(incidente).model_dump(mode='json'),
        message="Emergencia reportada exitosamente. Un taller será asignado pronto.",
        status_code=status.HTTP_201_CREATED,
    )


@router.get(
    "",
    response_model=List[IncidenteResponse],
    summary="Listar incidentes",
    description="Obtener lista de incidentes según el tipo de usuario",
    dependencies=[Depends(require_permission(Permission.EMERGENCY_VIEW_OWN))],
)
async def list_incidentes(
    estado: Optional[str] = Query(None, description="Filtrar por estado"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Listar incidentes según el tipo de usuario."""
    service = IncidenteService(session)
    
    if current_user.user_type == "client":
        incidentes = await service.get_client_incidentes(current_user.id, estado)
    elif current_user.user_type == "workshop":
        incidentes = await service.get_taller_incidentes(current_user.id, estado)
    elif current_user.user_type == "admin":
        # Admin puede ver todos los incidentes
        if estado:
            incidentes = await service.get_all_incidentes_by_estado(estado)
        else:
            incidentes = await service.get_all_incidentes()
    else:
        from ...core import ForbiddenException
        raise ForbiddenException("Tipo de usuario no autorizado")
    
    return create_success_response(
        data=[IncidenteResponse.model_validate(i).model_dump(mode='json') for i in incidentes],
        message=f"Se encontraron {len(incidentes)} incidentes",
    )


@router.get(
    "/{incidente_id}",
    response_model=IncidenteDetailResponse,
    summary="Obtener detalle de incidente",
    description="Obtener información detallada de un incidente con evidencias",
    dependencies=[Depends(require_permission(Permission.EMERGENCY_VIEW_OWN))],
)
async def get_incidente(
    incidente_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Obtener detalle de un incidente."""
    service = IncidenteService(session)
    
    incidente, evidencias, imagenes, audios = await service.get_incidente_with_evidencias(
        incidente_id,
        current_user.id,
        current_user.user_type
    )
    
    # Construir respuesta detallada
    response_data = IncidenteDetailResponse.model_validate(incidente)
    response_data.evidencias = [EvidenciaResponse.model_validate(e) for e in evidencias]
    response_data.imagenes = [EvidenciaImagenResponse.model_validate(i) for i in imagenes]
    response_data.audios = [EvidenciaAudioResponse.model_validate(a) for a in audios]
    
    return create_success_response(
        data=response_data.model_dump(mode='json'),
        message="Incidente obtenido exitosamente",
    )


@router.patch(
    "/{incidente_id}/estado",
    response_model=IncidenteResponse,
    summary="Actualizar estado de incidente",
    description="Cambiar el estado de un incidente",
    dependencies=[Depends(require_permission(Permission.SERVICE_UPDATE_STATUS))],
)
async def update_incidente_estado(
    incidente_id: int,
    request: IncidenteUpdateStatusRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Actualizar el estado de un incidente."""
    service = IncidenteService(session)
    
    incidente = await service.update_estado(
        incidente_id,
        request.estado,
        current_user.id,
        current_user.user_type
    )
    
    return create_success_response(
        data=IncidenteResponse.model_validate(incidente).model_dump(mode='json'),
        message=f"Estado actualizado a '{request.estado}' exitosamente",
    )


@router.get(
    "/pendientes/asignacion",
    response_model=List[IncidenteResponse],
    summary="Obtener incidentes pendientes",
    description="Obtener lista de incidentes pendientes de asignación",
    dependencies=[Depends(require_permission(Permission.REQUEST_VIEW_INCOMING))],
)
async def get_pending_incidentes(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Obtener incidentes pendientes de asignación."""
    service = IncidenteService(session)
    
    # Si es un taller, excluir los que ha rechazado
    taller_id = current_user.id if current_user.user_type == "workshop" else None
    incidentes = await service.get_pending_incidentes(taller_id)
    
    return create_success_response(
        data=[IncidenteResponse.model_validate(i).model_dump(mode='json') for i in incidentes],
        message=f"Se encontraron {len(incidentes)} incidentes pendientes",
    )


@router.post(
    "/{incidente_id}/aceptar",
    response_model=IncidenteResponse,
    summary="Aceptar solicitud de incidente",
    description="El taller acepta la solicitud y se asigna el incidente",
    dependencies=[Depends(require_permission(Permission.REQUEST_ACCEPT))],
)
async def accept_incidente(
    incidente_id: int,
    request: AcceptIncidenteRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Aceptar una solicitud de incidente."""
    if current_user.user_type != "workshop":
        from ...core import ForbiddenException
        raise ForbiddenException("Solo los talleres pueden aceptar solicitudes")
    
    service = IncidenteService(session)
    incidente = await service.accept_incidente(incidente_id, current_user.id)
    
    return create_success_response(
        data=IncidenteResponse.model_validate(incidente).model_dump(mode='json'),
        message="Solicitud aceptada exitosamente. El incidente ha sido asignado a tu taller.",
    )


@router.post(
    "/{incidente_id}/rechazar",
    response_model=IncidenteResponse,
    summary="Rechazar solicitud de incidente",
    description="El taller rechaza la solicitud y el sistema busca otro taller",
    dependencies=[Depends(require_permission(Permission.REQUEST_REJECT))],
)
async def reject_incidente(
    incidente_id: int,
    request: RejectIncidenteRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Rechazar una solicitud de incidente."""
    if current_user.user_type != "workshop":
        from ...core import ForbiddenException
        raise ForbiddenException("Solo los talleres pueden rechazar solicitudes")
    
    service = IncidenteService(session)
    incidente = await service.reject_incidente(incidente_id, current_user.id, request.motivo)
    
    return create_success_response(
        data=IncidenteResponse.model_validate(incidente).model_dump(mode='json'),
        message="Solicitud rechazada. El sistema buscará otro taller disponible.",
    )


@router.post(
    "/{incidente_id}/procesar-ia",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Process incident with AI",
    description="Queue an incident for multimodal Gemini classification",
    dependencies=[Depends(require_permission(Permission.ADMIN_MANUAL_INTERVENTION))],
)
async def process_incidente_with_ai(
    incidente_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Queue incident AI processing with current evidence payload."""
    logger.info(
        "Manual request to process incident with AI",
        incidente_id=incidente_id,
        requested_by=current_user.id,
        user_type=current_user.user_type,
    )

    service = IncidentAIService(session)
    analysis = await service.queue_incident_processing(
        incident_id=incidente_id,
        force_reprocess=False,
    )

    if analysis.status == "completed":
        return create_success_response(
            data=service.serialize_analysis(analysis),
            message="Incident already has an up-to-date AI analysis",
            status_code=status.HTTP_200_OK,
        )

    IncidentAIService.dispatch_processing_by_analysis_id(analysis.id)
    return create_success_response(
        data=service.serialize_analysis(analysis),
        message="AI processing queued successfully",
        status_code=status.HTTP_202_ACCEPTED,
    )


@router.post(
    "/{incidente_id}/reprocesar-ia",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Reprocess incident with AI",
    description="Force a new multimodal Gemini classification run",
    dependencies=[Depends(require_permission(Permission.ADMIN_MANUAL_INTERVENTION))],
)
async def reprocess_incidente_with_ai(
    incidente_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Force a new AI processing attempt for an incident."""
    logger.info(
        "Manual request to reprocess incident with AI",
        incidente_id=incidente_id,
        requested_by=current_user.id,
        user_type=current_user.user_type,
    )

    service = IncidentAIService(session)
    analysis = await service.queue_incident_processing(
        incident_id=incidente_id,
        force_reprocess=True,
    )

    IncidentAIService.dispatch_processing_by_analysis_id(analysis.id)
    return create_success_response(
        data=service.serialize_analysis(analysis),
        message="AI reprocessing queued successfully",
        status_code=status.HTTP_202_ACCEPTED,
    )


@router.get(
    "/{incidente_id}/analisis-ia",
    summary="Get latest AI analysis",
    description="Return the most recent technical AI analysis for an incident",
    dependencies=[
        Depends(
            require_any_permission(
                Permission.EMERGENCY_VIEW_OWN,
                Permission.ADMIN_MANUAL_INTERVENTION,
            )
        )
    ],
)
async def get_latest_incidente_ai_analysis(
    incidente_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Get the latest AI analysis entry for one incident."""
    incidente_service = IncidenteService(session)
    await incidente_service.get_incidente(
        incidente_id=incidente_id,
        user_id=current_user.id,
        user_type=current_user.user_type,
    )

    service = IncidentAIService(session)
    latest_analysis = await service.get_latest_analysis_for_incident(incidente_id)
    if not latest_analysis:
        raise NotFoundException(resource_type="AI analysis", resource_id=incidente_id)

    return create_success_response(
        data=service.serialize_analysis(latest_analysis),
        message="AI analysis retrieved successfully",
    )


@router.get(
    "/{incidente_id}/analisis-ia/historial",
    summary="List AI analysis history",
    description="Return AI analysis history for an incident",
    dependencies=[
        Depends(
            require_any_permission(
                Permission.EMERGENCY_VIEW_OWN,
                Permission.ADMIN_MANUAL_INTERVENTION,
            )
        )
    ],
)
async def get_incidente_ai_analysis_history(
    incidente_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Get AI analysis history for one incident."""
    incidente_service = IncidenteService(session)
    await incidente_service.get_incidente(
        incidente_id=incidente_id,
        user_id=current_user.id,
        user_type=current_user.user_type,
    )

    service = IncidentAIService(session)
    history = await service.list_analysis_history(incidente_id)

    return create_success_response(
        data=[service.serialize_analysis(analysis) for analysis in history],
        message=f"Found {len(history)} AI analyses",
    )


@router.get(
    "/{incidente_id}/rechazos",
    summary="Obtener rechazos de un incidente",
    description="Obtener lista de talleres que rechazaron este incidente",
    dependencies=[Depends(require_permission(Permission.EMERGENCY_VIEW_OWN))],
)
async def get_incidente_rechazos(
    incidente_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Obtener rechazos de un incidente."""
    from sqlalchemy import select
    from ...models.rechazo_taller import RechazoTaller
    from ...models.workshop import Workshop
    
    # Verificar que el incidente existe
    service = IncidenteService(session)
    incidente = await service.repository.find_by_id(incidente_id)
    
    if not incidente:
        from ...core import NotFoundException
        raise NotFoundException(f"Incidente con ID {incidente_id} no encontrado")
    
    # Obtener rechazos con información del taller
    result = await session.execute(
        select(RechazoTaller, Workshop)
        .join(Workshop, RechazoTaller.taller_id == Workshop.id)
        .where(RechazoTaller.incidente_id == incidente_id)
        .order_by(RechazoTaller.created_at.desc())
    )
    
    rechazos_data = []
    for rechazo, workshop in result:
        rechazos_data.append({
            "id": rechazo.id,
            "taller_id": rechazo.taller_id,
            "taller_nombre": workshop.workshop_name,
            "motivo": rechazo.motivo,
            "created_at": rechazo.created_at.isoformat()
        })
    
    return create_success_response(
        data=rechazos_data,
        message=f"Se encontraron {len(rechazos_data)} rechazos para este incidente",
    )
