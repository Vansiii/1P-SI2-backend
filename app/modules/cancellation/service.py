"""
Service para gestión de cancelaciones mutuas de incidentes.
"""
from datetime import datetime, timedelta, UTC
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_logger, NotFoundException, ValidationException, ForbiddenException
from ...core.state_machine import IncidentStateMachine, IncidentState, UserRole
from ...core.event_publisher import EventPublisher
from ...shared.schemas.events.cancellation import (
    CancellationRequestedEvent,
    CancellationApprovedEvent,
    CancellationRejectedEvent
)
from ...models.cancellation_request import CancellationRequest
from ...models.incidente import Incidente

logger = get_logger(__name__)


class CancellationService:
    """Service para lógica de negocio de cancelaciones mutuas de incidentes."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def request_cancellation(
        self,
        incident_id: int,
        user_id: int,
        user_type: str,
        reason: str
    ) -> CancellationRequest:
        """
        Solicitar cancelación mutua de un incidente ambiguo.
        
        Args:
            incident_id: ID del incidente
            user_id: ID del usuario que solicita
            user_type: Tipo de usuario ('client' o 'workshop')
            reason: Motivo de la cancelación
            
        Returns:
            CancellationRequest creado
            
        Raises:
            NotFoundException: Si el incidente no existe
            ValidationException: Si no cumple validaciones
            ForbiddenException: Si no tiene permisos
        """
        # Obtener el incidente
        incident = await self.session.scalar(
            select(Incidente).where(Incidente.id == incident_id)
        )
        
        if not incident:
            raise NotFoundException(f"Incidente {incident_id} no encontrado")
        
        # Validar que el incidente esté asignado o en proceso
        if incident.estado_actual not in ["asignado", "en_proceso"]:
            raise ValidationException(
                f"No se puede cancelar un incidente en estado '{incident.estado_actual}'"
            )
        
        # Validate state transition using State Machine
        state_machine = IncidentStateMachine()
        current_state = IncidentState(incident.estado_actual)
        target_state = IncidentState.CANCELADO
        
        # Determine user role
        user_role = UserRole.CLIENTE if user_type == "client" else UserRole.TALLER
        
        can_transition, error_message = state_machine.can_transition(
            from_state=current_state,
            to_state=target_state,
            user_role=user_role,
            incident=incident
        )
        
        if not can_transition:
            logger.warning(f"State transition validation failed for cancellation request: {error_message}")
            raise ValidationException(f"Cannot request cancellation: {error_message}")
        
        # Validar permisos
        if user_type == "client" and incident.client_id != user_id:
            raise ForbiddenException("No tienes permiso para cancelar este incidente")
        elif user_type == "workshop" and incident.taller_id != user_id:
            raise ForbiddenException("No tienes permiso para cancelar este incidente")
        
        # Verificar que no exista una solicitud pendiente
        existing_request = await self.session.scalar(
            select(CancellationRequest).where(
                and_(
                    CancellationRequest.incident_id == incident_id,
                    CancellationRequest.status == "pending"
                )
            )
        )
        
        if existing_request:
            raise ValidationException(
                "Ya existe una solicitud de cancelación pendiente para este incidente"
            )
        
        # Validar longitud del motivo
        if len(reason.strip()) < 10:
            raise ValidationException("El motivo debe tener al menos 10 caracteres")
        
        # Crear solicitud de cancelación
        cancellation_request = CancellationRequest(
            incident_id=incident_id,
            requested_by=user_type,
            requested_by_user_id=user_id,
            reason=reason.strip(),
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(hours=24)
        )
        
        self.session.add(cancellation_request)
        await self.session.commit()
        await self.session.refresh(cancellation_request)
        
        logger.info(
            f"Solicitud de cancelación creada para incidente {incident_id} por {user_type} {user_id}"
        )
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ PUBLICAR EVENTO DE CANCELACIÓN SOLICITADA
        # ═══════════════════════════════════════════════════════════════════════
        try:
            cancellation_requested_event = CancellationRequestedEvent(
                incident_id=incident_id,
                cancellation_request_id=cancellation_request.id,
                requested_by=user_id,
                requested_by_role=user_type,
                reason=reason,
                requested_at=cancellation_request.created_at
            )
            
            await EventPublisher.publish(self.session, cancellation_requested_event)
            await self.session.commit()
            
            logger.info(
                f"✅ Evento CANCELLATION_REQUESTED publicado para incidente {incident_id}",
                incident_id=incident_id,
                request_id=cancellation_request.id
            )
            
        except Exception as e:
            logger.error(
                f"❌ Error publicando evento CANCELLATION_REQUESTED: {str(e)}",
                exc_info=True
            )
        # ═══════════════════════════════════════════════════════════════════════
        
        # Notificaciones persistentes/push gestionadas por OutboxProcessor.
        
        return cancellation_request
    
    async def respond_to_cancellation(
        self,
        request_id: int,
        user_id: int,
        user_type: str,
        accept: bool,
        response_message: Optional[str] = None
    ) -> CancellationRequest:
        """
        Responder a una solicitud de cancelación.
        
        Args:
            request_id: ID de la solicitud
            user_id: ID del usuario que responde
            user_type: Tipo de usuario ('client' o 'workshop')
            accept: True para aceptar, False para rechazar
            response_message: Mensaje opcional de respuesta
            
        Returns:
            CancellationRequest actualizado
            
        Raises:
            NotFoundException: Si la solicitud no existe
            ValidationException: Si no cumple validaciones
            ForbiddenException: Si no tiene permisos
        """
        # Obtener la solicitud
        cancellation_request = await self.session.scalar(
            select(CancellationRequest).where(CancellationRequest.id == request_id)
        )
        
        if not cancellation_request:
            raise NotFoundException(f"Solicitud de cancelación {request_id} no encontrada")
        
        # Validar que esté pendiente
        if cancellation_request.status != "pending":
            raise ValidationException(
                f"La solicitud ya fue {cancellation_request.status}"
            )
        
        # Validar que no haya expirado
        if datetime.now(UTC) > cancellation_request.expires_at:
            cancellation_request.status = "expired"
            await self.session.commit()
            raise ValidationException("La solicitud ha expirado")
        
        # Validar que sea la otra parte quien responde
        if cancellation_request.requested_by == user_type:
            raise ForbiddenException(
                "No puedes responder a tu propia solicitud de cancelación"
            )
        
        # Obtener el incidente
        incident = await self.session.scalar(
            select(Incidente).where(Incidente.id == cancellation_request.incident_id)
        )
        
        if not incident:
            raise NotFoundException("Incidente no encontrado")
        
        # Validar permisos
        if user_type == "client" and incident.client_id != user_id:
            raise ForbiddenException("No tienes permiso para responder a esta solicitud")
        elif user_type == "workshop" and incident.taller_id != user_id:
            raise ForbiddenException("No tienes permiso para responder a esta solicitud")
        
        # Actualizar solicitud
        cancellation_request.response_by_user_id = user_id
        cancellation_request.response_message = response_message
        cancellation_request.responded_at = datetime.now(UTC)
        cancellation_request.status = "accepted" if accept else "rejected"
        
        # Si fue aceptada, anular el incidente y buscar nuevo taller ANTES del commit
        # para que sea transaccional
        if accept:
            await self._cancel_incident_and_reassign(incident)
        
        # Commit después de todas las operaciones para que sea transaccional
        await self.session.commit()
        
        logger.info(
            f"Solicitud de cancelación {request_id} {'aceptada' if accept else 'rechazada'} "
            f"por {user_type} {user_id}"
        )
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ PUBLICAR EVENTO DE CANCELACIÓN APROBADA O RECHAZADA
        # ═══════════════════════════════════════════════════════════════════════
        try:
            if accept:
                cancellation_approved_event = CancellationApprovedEvent(
                    incident_id=cancellation_request.incident_id,
                    cancellation_request_id=request_id,
                    approved_by=user_id,
                    approved_by_role=user_type,
                    approved_at=cancellation_request.responded_at
                )
                
                await EventPublisher.publish(self.session, cancellation_approved_event)
                await self.session.commit()
                
                logger.info(
                    f"✅ Evento CANCELLATION_APPROVED publicado para incidente {cancellation_request.incident_id}",
                    incident_id=cancellation_request.incident_id,
                    request_id=request_id
                )
            else:
                cancellation_rejected_event = CancellationRejectedEvent(
                    incident_id=cancellation_request.incident_id,
                    cancellation_request_id=request_id,
                    rejected_by=user_id,
                    rejected_by_role=user_type,
                    reason=response_message,
                    rejected_at=cancellation_request.responded_at
                )
                
                await EventPublisher.publish(self.session, cancellation_rejected_event)
                await self.session.commit()
                
                logger.info(
                    f"✅ Evento CANCELLATION_REJECTED publicado para incidente {cancellation_request.incident_id}",
                    incident_id=cancellation_request.incident_id,
                    request_id=request_id
                )
                
        except Exception as e:
            logger.error(
                f"❌ Error publicando evento de cancelación: {str(e)}",
                exc_info=True
            )
        # ═══════════════════════════════════════════════════════════════════════
        
        # Notificaciones persistentes/push gestionadas por OutboxProcessor.
        
        return cancellation_request
    
    async def _cancel_incident_and_reassign(self, incident: Incidente) -> None:
        """
        Anular incidente y buscar nuevo taller.
        
        Args:
            incident: Incidente a anular
        """
        from ...models.rechazo_taller import RechazoTaller
        from ...models.historial_servicio import HistorialServicio
        from ...models.tracking_session import TrackingSession
        from ...models.technician import Technician
        from ...models.estados_servicio import EstadosServicio
        from sqlalchemy import update
        
        # Validate state transition using State Machine
        state_machine = IncidentStateMachine()
        current_state = IncidentState(incident.estado_actual)
        target_state = IncidentState.PENDIENTE  # Returning to pending for reassignment
        
        can_transition, error_message = state_machine.can_transition(
            from_state=current_state,
            to_state=target_state,
            user_role=UserRole.ADMIN,  # System acts as admin for cancellation and reassignment
            incident=incident
        )
        
        if not can_transition:
            logger.error(f"State transition validation failed for cancellation: {error_message}")
            raise ValidationException(f"Cannot cancel and reassign incident: {error_message}")
        
        # Guardar rechazo
        rechazo = RechazoTaller(
            incidente_id=incident.id,
            taller_id=incident.taller_id,
            motivo="[Cancelación mutua] Ambas partes acordaron cancelar el servicio"
        )
        self.session.add(rechazo)
        
        # Obtener el estado_id para "pendiente"
        estado_pendiente = await self.session.scalar(
            select(EstadosServicio).where(EstadosServicio.nombre == "pendiente")
        )
        
        if not estado_pendiente:
            logger.error("Estado 'pendiente' no encontrado en estados_servicio")
            # Fallback: no registrar en historial si no existe el estado
        else:
            # Registrar en historial
            historial = HistorialServicio(
                incidente_id=incident.id,
                estado_id=estado_pendiente.id,
                comentario=f"Cancelación mutua acordada. Estado anterior: {incident.estado_actual}. Buscando nuevo taller.",
                changed_by_user_id=incident.taller_id
            )
            self.session.add(historial)
        
        # Liberar técnico si estaba asignado
        if incident.tecnico_id:
            # Finalizar sesión de tracking
            await self.session.execute(
                update(TrackingSession)
                .where(
                    TrackingSession.incidente_id == incident.id,
                    TrackingSession.is_active == True
                )
                .values(
                    is_active=False,
                    ended_at=datetime.now(UTC)
                )
            )
            
            # Liberar técnico
            technician = await self.session.get(Technician, incident.tecnico_id)
            if technician:
                technician.is_on_duty = False
                technician.is_available = True  # Marcar como disponible nuevamente
                technician.updated_at = datetime.now(UTC)
                logger.info(
                    f"Técnico {incident.tecnico_id} liberado (is_on_duty=False, is_available=True) por cancelación mutua"
                )
                
                # Notificar cambio de disponibilidad via EventPublisher
                from ...core.event_publisher import EventPublisher
                from ...shared.schemas.events.incident import IncidentTechnicianArrivedEvent
                
                technician_event_data = {
                    "incident_id": incident.id,
                    "technician_id": incident.tecnico_id,
                    "technician_name": f"{technician.first_name} {technician.last_name}" if technician else "Unknown",
                    "new_status": "available",
                    "old_status": "on_duty",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "workshop_id": technician.workshop_id,
                }
        
        # Limpiar asignación y volver a pendiente
        incident.taller_id = None
        incident.tecnico_id = None
        incident.estado_actual = "pendiente"
        incident.assigned_at = None
        incident.updated_at = datetime.now(UTC)
        
        await self.session.commit()
        
        # ✅ Emitir evento WebSocket dirigido SOLO a participantes del incidente
        from ...core.websocket_events import emit_to_incident_room, EventTypes
        
        try:
            await emit_to_incident_room(
                incident_id=incident.id,
                event_type=EventTypes.INCIDENT_STATUS_CHANGED,
                data={
                    "incident_id": incident.id,
                    "estado_actual": "pendiente",
                    "new_status": "pendiente",
                    "old_status": incident.estado_actual,
                    "reason": "mutual_cancellation",
                    "timestamp": datetime.now(UTC).isoformat()
                }
            )
            logger.info(f"✅ WebSocket event emitted to incident room: {incident.id} → pendiente (mutual cancellation)")
        except Exception as ws_err:
            logger.error(f"Failed to emit status change WebSocket event: {str(ws_err)}")
        
        logger.info(
            f"Incidente {incident.id} anulado por cancelación mutua. "
            f"Volviendo a estado pendiente para nueva asignación."
        )
        
        # Trigger automatic reassignment immediately
        # Ejecutar reasignación automática inmediatamente después de la cancelación
        try:
            from ...modules.assignment.services import IntelligentAssignmentService
            
            logger.info(f"Iniciando reasignación automática inmediata para incidente {incident.id}")
            
            # Usar la sesión actual para la reasignación
            assignment_service = IntelligentAssignmentService(self.session)
            result = await assignment_service.assign_incident_automatically(
                incident_id=incident.id,
                force_ai_analysis=False
            )
            
            if result.success:
                logger.info(
                    f"✅ Reasignación automática exitosa para incidente {incident.id}: "
                    f"workshop={result.assigned_workshop.workshop_name if result.assigned_workshop else 'N/A'}"
                )
                
                # ═══════════════════════════════════════════════════════════════════════
                # ✅ NOTIFICACIONES MANEJADAS POR OUTBOX PROCESSOR
                # assignment_service.assign_incident_automatically ya publica los eventos
                # incident.assigned y incident.no_workshop_available.
                # NO enviar notificaciones duplicadas aquí.
                # ═══════════════════════════════════════════════════════════════════════
                    
            else:
                logger.warning(
                    f"⚠️ Reasignación automática falló para incidente {incident.id}: "
                    f"{result.error_message}"
                )
                
                # ═══════════════════════════════════════════════════════════════════════
                # ✅ NOTIFICACIONES MANEJADAS POR OUTBOX PROCESSOR
                # ═══════════════════════════════════════════════════════════════════════
                        
        except Exception as e:
            logger.error(
                f"❌ Error en reasignación automática para incidente {incident.id}: {str(e)}",
                exc_info=True
            )
            
            # ═══════════════════════════════════════════════════════════════════════
            # ✅ NOTIFICACIONES MANEJADAS POR OUTBOX PROCESSOR
            # ═══════════════════════════════════════════════════════════════════════    
    async def get_pending_cancellation(
        self,
        incident_id: int
    ) -> Optional[CancellationRequest]:
        """
        Obtener solicitud de cancelación pendiente para un incidente.
        
        Args:
            incident_id: ID del incidente
            
        Returns:
            CancellationRequest pendiente o None
        """
        return await self.session.scalar(
            select(CancellationRequest).where(
                and_(
                    CancellationRequest.incident_id == incident_id,
                    CancellationRequest.status == "pending"
                )
            )
        )
