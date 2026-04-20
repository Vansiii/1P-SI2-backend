"""
Router para gestión de incidentes/emergencias vehiculares.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status, HTTPException
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
    accept_suggested_technician: bool = Field(
        default=False,
        description="Si es True, acepta el técnico sugerido por la IA y cambia el estado a 'en_proceso'. Si es False, solo asigna el taller y deja el estado en 'asignado' para asignación manual."
    )

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
    tecnico_id: Optional[str] = Query(None, description="Filtrar por técnico (usar 'me' para el técnico actual)"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Listar incidentes según el tipo de usuario."""
    service = IncidenteService(session)
    
    if current_user.user_type == "client":
        incidentes = await service.get_client_incidentes(current_user.id, estado)
    elif current_user.user_type == "technician":
        # Técnico puede ver sus incidentes asignados
        if tecnico_id == "me" or tecnico_id is None:
            # Obtener incidentes asignados al técnico actual
            incidentes = await service.get_technician_incidentes(current_user.id, estado)
        else:
            from ...core import ForbiddenException
            raise ForbiddenException("No puedes ver incidentes de otros técnicos")
    elif current_user.user_type == "workshop":
        # Si el taller pide estado "pendiente", mostrar solicitudes entrantes
        if estado == "pendiente":
            incidentes = await service.get_pending_incidentes(current_user.id)
        elif estado is None:
            # "Todos": combinar solicitudes pendientes + incidencias asignadas
            pendientes = await service.get_pending_incidentes(current_user.id)
            asignadas = await service.get_taller_incidentes(current_user.id, None)
            # Combinar y eliminar duplicados por ID
            incidentes_dict = {inc.id: inc for inc in asignadas}
            for inc in pendientes:
                if inc.id not in incidentes_dict:
                    incidentes_dict[inc.id] = inc
            # Ordenar por fecha de creación descendente
            incidentes = sorted(incidentes_dict.values(), key=lambda x: x.created_at, reverse=True)
        else:
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
    
    # Construir respuestas con información del técnico sugerido
    response_data = []
    
    # Si es un taller, obtener todos los técnicos sugeridos en una sola consulta
    suggested_technicians_map = {}
    if taller_id and incidentes:
        from ...models.assignment_attempt import AssignmentAttempt
        from ...models.technician import Technician
        from sqlalchemy import select, and_
        
        incident_ids = [inc.id for inc in incidentes]
        
        result = await session.execute(
            select(AssignmentAttempt, Technician)
            .join(Technician, AssignmentAttempt.technician_id == Technician.id, isouter=True)
            .where(
                and_(
                    AssignmentAttempt.incident_id.in_(incident_ids),
                    AssignmentAttempt.workshop_id == taller_id,
                    AssignmentAttempt.status.in_(['pending', 'timeout'])
                )
            )
        )
        
        for assignment_attempt, technician in result:
            if technician:
                suggested_technicians_map[assignment_attempt.incident_id] = {
                    "technician_id": technician.id,
                    "first_name": technician.first_name,
                    "last_name": technician.last_name,
                    "phone": technician.phone,
                    "final_score": float(assignment_attempt.final_score),
                    "distance_km": float(assignment_attempt.distance_km),
                    "ai_reasoning": assignment_attempt.ai_reasoning,
                    "assignment_strategy": assignment_attempt.assignment_strategy,
                    "status": assignment_attempt.status,  # pending, timeout, rejected, accepted
                    "timeout_at": assignment_attempt.timeout_at.isoformat() if assignment_attempt.timeout_at else None  # ✅ Timestamp cuando expira
                }
    
    for incidente in incidentes:
        incidente_dict = IncidenteResponse.model_validate(incidente).model_dump(mode='json')
        
        # Agregar información del técnico sugerido si existe
        if incidente.id in suggested_technicians_map:
            incidente_dict["suggested_technician"] = suggested_technicians_map[incidente.id]
        
        response_data.append(incidente_dict)
    
    return create_success_response(
        data=response_data,
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
    incidente = await service.accept_incidente(
        incidente_id, 
        current_user.id,
        accept_suggested_technician=request.accept_suggested_technician
    )
    
    return create_success_response(
        data=IncidenteResponse.model_validate(incidente).model_dump(mode='json'),
        message="Solicitud aceptada exitosamente. El incidente ha sido asignado a tu taller.",
    )


@router.post(
    "/{incidente_id}/rechazar",
    response_model=IncidenteResponse,
    summary="Rechazar solicitud de incidente",
    description="El taller rechaza la solicitud y el sistema busca otro taller automáticamente",
    dependencies=[Depends(require_permission(Permission.REQUEST_REJECT))],
)
async def reject_incidente(
    incidente_id: int,
    request: RejectIncidenteRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Rechazar una solicitud de incidente y activar reasignación automática.
    
    Flow:
    1. Registrar rechazo del taller
    2. Marcar assignment_attempt como 'rejected'
    3. Activar reasignación automática con recálculo dinámico
    4. Retornar resultado (nuevo taller o requiere intervención manual)
    """
    if current_user.user_type != "workshop":
        from ...core import ForbiddenException
        raise ForbiddenException("Solo los talleres pueden rechazar solicitudes")
    
    # 1. Registrar rechazo
    service = IncidenteService(session)
    incidente = await service.reject_incidente(incidente_id, current_user.id, request.motivo)
    
    # 2. Activar reasignación automática
    from ...services.reassignment_service import ReassignmentService
    
    reassignment_service = ReassignmentService(session)
    result = await reassignment_service.handle_rejection(
        incident_id=incidente_id,
        workshop_id=current_user.id,
        rejection_reason=request.motivo
    )
    
    # 3. Preparar respuesta según resultado
    if result.success:
        message = (
            f"Solicitud rechazada y reasignada automáticamente a "
            f"{result.assigned_workshop.workshop_name if result.assigned_workshop else 'otro taller'}."
        )
    else:
        if "Max attempts" in result.error_message or "No workshops available" in result.error_message:
            message = (
                "Solicitud rechazada. No hay más talleres disponibles. "
                "Se ha notificado al administrador para intervención manual."
            )
        else:
            message = f"Solicitud rechazada. Error en reasignación: {result.error_message}"
    
    return create_success_response(
        data=IncidenteResponse.model_validate(incidente).model_dump(mode='json'),
        message=message,
    )


@router.post(
    "/{incidente_id}/anular-asignacion",
    response_model=IncidenteResponse,
    summary="Anular asignación de caso ambiguo",
    description="El taller anula la asignación de un caso ambiguo después de chatear con el cliente (CU11)",
    dependencies=[Depends(require_permission(Permission.REQUEST_REJECT))],
)
async def anular_asignacion_ambigua(
    incidente_id: int,
    request: RejectIncidenteRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Anular asignación de un caso ambiguo después de chatear con el cliente.
    
    Este endpoint es específico para el CU11 Gestionar Caso Ambiguo:
    - Solo funciona si el incidente es ambiguo (es_ambiguo = True)
    - Solo funciona si el taller ya está asignado
    - Solo funciona si ya hay mensajes de chat entre taller y cliente
    - Después de anular, el sistema busca otro taller automáticamente
    
    Flow:
    1. Validar que el incidente sea ambiguo
    2. Validar que el taller esté asignado
    3. Validar que haya al menos un mensaje de chat
    4. Anular la asignación (volver a pendiente)
    5. Activar reasignación automática
    """
    if current_user.user_type != "workshop":
        from ...core import ForbiddenException
        raise ForbiddenException("Solo los talleres pueden anular asignaciones")
    
    # 1. Anular asignación con validaciones
    service = IncidenteService(session)
    incidente = await service.anular_asignacion_ambigua(
        incidente_id=incidente_id,
        taller_id=current_user.id,
        motivo=request.motivo
    )
    
    # 2. Activar reasignación automática
    from ...services.reassignment_service import ReassignmentService
    
    reassignment_service = ReassignmentService(session)
    result = await reassignment_service.handle_rejection(
        incident_id=incidente_id,
        workshop_id=current_user.id,
        rejection_reason=f"Caso ambiguo anulado: {request.motivo}"
    )
    
    # 3. Preparar respuesta según resultado
    if result.success:
        message = (
            f"Asignación anulada. El incidente ha sido reasignado automáticamente a "
            f"{result.assigned_workshop.workshop_name if result.assigned_workshop else 'otro taller'}."
        )
    else:
        if "Max attempts" in result.error_message or "No workshops available" in result.error_message:
            message = (
                "Asignación anulada. No hay más talleres disponibles. "
                "Se ha notificado al administrador para intervención manual."
            )
        else:
            message = f"Asignación anulada. Error en reasignación: {result.error_message}"
    
    return create_success_response(
        data=IncidenteResponse.model_validate(incidente).model_dump(mode='json'),
        message=message,
    )


@router.post(
    "/{incidente_id}/cancelar",
    response_model=IncidenteResponse,
    summary="Cancelar incidente",
    description="Cancelar un incidente (cliente puede cancelar sus propios incidentes, admin puede cancelar cualquiera)",
    dependencies=[Depends(require_any_permission(
        Permission.EMERGENCY_CANCEL_OWN,
        Permission.ADMIN_MANUAL_INTERVENTION
    ))],
)
async def cancel_incidente(
    incidente_id: int,
    motivo: Optional[str] = Query(None, description="Motivo de la cancelación"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Cancelar un incidente.
    
    Casos de uso:
    - Cliente cancela porque solucionó el problema por su cuenta
    - Cliente cancela porque ya no necesita el servicio
    - Admin cancela por razones administrativas
    
    El incidente debe estar en estado pendiente, asignado o en_proceso.
    No se pueden cancelar incidentes ya resueltos o cancelados.
    """
    service = IncidenteService(session)
    
    incidente = await service.cancel_incidente(
        incidente_id=incidente_id,
        user_id=current_user.id,
        user_type=current_user.user_type,
        motivo=motivo
    )
    
    return create_success_response(
        data=IncidenteResponse.model_validate(incidente).model_dump(mode='json'),
        message="Incidente cancelado exitosamente",
    )


@router.post(
    "/{incidente_id}/completar",
    response_model=IncidenteResponse,
    summary="Completar incidente",
    description="Marcar un incidente como completado (cliente puede completar sus propios incidentes cuando el servicio ha sido satisfactorio)",
    dependencies=[Depends(require_any_permission(
        Permission.EMERGENCY_CANCEL_OWN,  # Reutilizamos el mismo permiso que para cancelar
        Permission.ADMIN_MANUAL_INTERVENTION
    ))],
)
async def complete_incidente(
    incidente_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Marcar un incidente como completado.
    
    Casos de uso:
    - Cliente confirma que el problema fue resuelto satisfactoriamente
    - Cliente marca como completado después de que el técnico terminó el trabajo
    
    El incidente debe estar en estado 'en_proceso' o 'en_sitio'.
    Solo el cliente propietario del incidente puede marcarlo como completado.
    """
    service = IncidenteService(session)
    
    # Verificar que el incidente existe y pertenece al cliente
    incidente = await service.repository.find_by_id(incidente_id)
    if not incidente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incidente no encontrado"
        )
    
    # Verificar permisos: solo el cliente propietario puede completar
    if current_user.user_type == "client" and incidente.client_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para completar este incidente"
        )
    
    # Verificar que el incidente esté en un estado que permita completarlo
    if incidente.estado_actual not in ["en_proceso", "en_sitio"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se puede completar un incidente en estado '{incidente.estado_actual}'. Debe estar 'en_proceso' o 'en_sitio'."
        )
    
    # Usar el servicio de estados para transicionar a 'resuelto'
    from ..incident_states.services import IncidentStateService
    state_service = IncidentStateService(session)
    
    try:
        incidente = await state_service.resolve_incident(
            incident_id=incidente_id,
            resolved_by=current_user.id,
            resolution_notes="Marcado como completado por el cliente"
        )
        
        return create_success_response(
            data=IncidenteResponse.model_validate(incidente).model_dump(mode='json'),
            message="Incidente marcado como completado exitosamente",
        )
        
    except Exception as e:
        logger.error(f"Error al completar incidente {incidente_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al completar el incidente"
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
