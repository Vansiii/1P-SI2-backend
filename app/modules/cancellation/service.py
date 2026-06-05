"""
Service para gestión de cancelaciones mutuas de incidentes.
"""
from datetime import datetime, timedelta, UTC
from typing import Optional

from sqlalchemy import select, and_, desc, func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_logger, NotFoundException, ValidationException, ForbiddenException
from ...core.state_machine import IncidentStateMachine, IncidentState, UserRole
from ...core.event_publisher import EventPublisher
from ...shared.schemas.events.cancellation import (
    CancellationRequestedEvent,
    CancellationApprovedEvent,
    CancellationRejectedEvent
)
from ...shared.schemas.events.incident import IncidentStatusChangedEvent
from ...shared.schemas.events.dashboard import (
    DashboardIncidentCountChangedEvent,
    DashboardActiveTechniciansChangedEvent,
)
from ...models.assignment_attempt import AssignmentAttempt
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
        
        # Validar que el incidente esté en una etapa activa donde cancelar tenga sentido
        # (chat de cancelación puede ocurrir antes o durante la ejecución técnica).
        if incident.estado_actual not in [
            "pendiente", "sin_taller_disponible",
            "asignado", "aceptado", "en_camino", "en_proceso"
        ]:
            raise ValidationException(
                f"No se puede cancelar un incidente en estado '{incident.estado_actual}'"
            )
        
        # Validar rol permitido para solicitar cancelación mutua
        if user_type not in {"client", "workshop"}:
            raise ForbiddenException("Solo cliente o taller pueden solicitar cancelación mutua")

        # Validar permisos
        if user_type == "client" and incident.client_id != user_id:
            raise ForbiddenException("No tienes permiso para cancelar este incidente")
        elif user_type == "workshop" and incident.taller_id != user_id:
            raise ForbiddenException("No tienes permiso para cancelar este incidente")

        # Obtener la última solicitud para manejar idempotencia y reutilización.
        latest_request = await self.session.scalar(
            select(CancellationRequest)
            .where(CancellationRequest.incident_id == incident_id)
            .order_by(desc(CancellationRequest.created_at), desc(CancellationRequest.id))
            .limit(1)
        )

        # Si ya hay una pendiente vigente, devolverla para evitar 400 redundante.
        if latest_request and latest_request.status == "pending":
            now = datetime.now(UTC)
            if latest_request.expires_at > now:
                return latest_request
        
        # Verificar que no exista una solicitud pendiente no expirada
        existing_pending = await self.session.scalar(
            select(CancellationRequest).where(
                and_(
                    CancellationRequest.incident_id == incident_id,
                    CancellationRequest.status == "pending"
                )
            )
        )
        
        if existing_pending:
            now = datetime.now(UTC)
            if existing_pending.expires_at <= now:
                existing_pending.status = "expired"
                await self.session.commit()
                logger.info(
                    f"Solicitud de cancelación {existing_pending.id} expirada automáticamente "
                    f"para incidente {incident_id}"
                )
            else:
                raise ValidationException(
                    "Ya existe una solicitud de cancelación pendiente para este incidente"
                )
        
        # Validar longitud del motivo
        if len(reason.strip()) < 10:
            raise ValidationException("El motivo debe tener al menos 10 caracteres")
        
        # Crear solicitud de cancelación
        if latest_request and latest_request.status in ("accepted", "rejected", "expired"):
            cancellation_request = latest_request
            cancellation_request.requested_by = user_type
            cancellation_request.requested_by_user_id = user_id
            cancellation_request.reason = reason.strip()
            cancellation_request.status = "pending"
            cancellation_request.response_by_user_id = None
            cancellation_request.response_message = None
            cancellation_request.responded_at = None
            cancellation_request.created_at = datetime.now(UTC)
            cancellation_request.expires_at = datetime.now(UTC) + timedelta(hours=24)
        else:
            cancellation_request = CancellationRequest(
                incident_id=incident_id,
                requested_by=user_type,
                requested_by_user_id=user_id,
                reason=reason.strip(),
                status="pending",
                expires_at=datetime.now(UTC) + timedelta(hours=24)
            )
        
        self.session.add(cancellation_request)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            pending_request = await self.session.scalar(
                select(CancellationRequest).where(
                    and_(
                        CancellationRequest.incident_id == incident_id,
                        CancellationRequest.status == "pending"
                    )
                )
            )
            if pending_request:
                return pending_request
            raise ValidationException(
                "Ya existe una solicitud de cancelación pendiente para este incidente"
            )
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
            await self._cancel_incident_and_reassign(
                incident=incident,
                changed_by_user_id=user_id,
                changed_by_role=user_type,
            )
        
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
                    requested_by=cancellation_request.requested_by_user_id,
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
                    requested_by=cancellation_request.requested_by_user_id,
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
    
    async def _publish_incident_count_changed(self, status: str, delta: int) -> None:
        """Publicar cambio de contador por estado para dashboard admin."""
        try:
            count = await self.session.scalar(
                select(func.count(Incidente.id)).where(Incidente.estado_actual == status)
            ) or 0

            event = DashboardIncidentCountChangedEvent(
                status=status,
                count=count,
                delta=delta,
            )
            await EventPublisher.publish(self.session, event)
        except Exception as e:
            logger.error(
                f"Error publicando dashboard.incident_count_changed ({status}): {str(e)}",
                exc_info=True,
            )

    async def _publish_active_technicians_changed(self) -> None:
        """Publicar cambio de contadores de técnicos para dashboard admin."""
        try:
            from ...models.technician import Technician

            active_count = await self.session.scalar(
                select(func.count(Technician.id)).where(Technician.is_on_duty == True)
            ) or 0
            available_count = await self.session.scalar(
                select(func.count(Technician.id)).where(Technician.is_available == True)
            ) or 0

            event = DashboardActiveTechniciansChangedEvent(
                active_count=active_count,
                available_count=available_count,
                on_duty_count=active_count,
            )
            await EventPublisher.publish(self.session, event)
        except Exception as e:
            logger.error(
                f"Error publicando dashboard.active_technicians_changed: {str(e)}",
                exc_info=True,
            )

    async def _cancel_incident_and_reassign(
        self,
        incident: Incidente,
        changed_by_user_id: int,
        changed_by_role: str,
    ) -> None:
        """
        Anular incidente y decidir el siguiente paso según el modo de asignación.
        
        Args:
            incident: Incidente a anular
        """
        from ...models.rechazo_taller import RechazoTaller
        from ...models.historial_servicio import HistorialServicio
        from ...models.tracking_session import TrackingSession
        from ...models.technician import Technician
        from ...models.estados_servicio import EstadosServicio
        
        # Validate state transition using State Machine
        state_machine = IncidentStateMachine()
        current_state = IncidentState(incident.estado_actual)
        target_state = IncidentState.PENDIENTE
        assignment_mode = incident.assignment_mode or "automatic"
        
        can_transition, error_message = state_machine.can_transition(
            from_state=current_state,
            to_state=target_state,
            user_role=UserRole.ADMIN,
            incident=incident
        )
        
        if not can_transition:
            logger.error(f"State transition validation failed for cancellation: {error_message}")
            raise ValidationException(f"Cannot cancel and reassign incident: {error_message}")

        old_status = incident.estado_actual
        old_workshop_id = incident.taller_id
        
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
            next_action = (
                "El cliente debe seleccionar un nuevo taller."
                if assignment_mode == "manual"
                else "Buscando nuevo taller."
            )
            # Registrar en historial
            historial = HistorialServicio(
                incidente_id=incident.id,
                estado_id=estado_pendiente.id,
                comentario=(
                    f"Cancelación mutua acordada. Estado anterior: {incident.estado_actual}. "
                    f"{next_action}"
                ),
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
        
        await self.session.execute(
            update(AssignmentAttempt)
            .where(
                AssignmentAttempt.incident_id == incident.id,
                AssignmentAttempt.workshop_id == old_workshop_id,
                AssignmentAttempt.status.in_(["pending", "accepted"])
            )
            .values(
                status="cancelled",
                responded_at=datetime.now(UTC),
                response_message=(
                    "Cancelación mutua aceptada. El cliente debe seleccionar otro taller."
                    if assignment_mode == "manual"
                    else "Cancelación mutua aceptada. Se buscará otro taller."
                ),
            )
        )

        # Limpiar asignación y volver a pendiente
        incident.taller_id = None
        incident.tecnico_id = None
        incident.estado_actual = "pendiente"
        incident.assigned_at = None
        incident.updated_at = datetime.now(UTC)
        
        await self.session.commit()
        
        # Publicar eventos canónicos por outbox para que admin/web/mobile
        # reciban el cambio de estado y métricas en tiempo real.
        
        try:
            status_event = IncidentStatusChangedEvent(
                incident_id=incident.id,
                old_status=old_status,
                new_status="pendiente",
                workshop_id=old_workshop_id,
                changed_by=changed_by_user_id,
                changed_by_role=changed_by_role,
                reason="mutual_cancellation",
            )
            await EventPublisher.publish(self.session, status_event)

            await self._publish_incident_count_changed(status=old_status, delta=-1)
            await self._publish_incident_count_changed(status="pendiente", delta=+1)
            await self._publish_active_technicians_changed()

            await self.session.commit()
            logger.info(
                f"✅ Realtime mutual cancellation events published: "
                f"incident {incident.id} {old_status} → pendiente"
            )
        except Exception as publish_err:
            logger.error(
                f"Failed to publish mutual cancellation realtime events: {str(publish_err)}",
                exc_info=True,
            )
        
        logger.info(
            f"Incidente {incident.id} anulado por cancelación mutua. "
            f"Volviendo a estado pendiente para "
            f"{'selección manual' if assignment_mode == 'manual' else 'reasignación automática'}."
        )

        if assignment_mode != "manual":
            from ...modules.assignment.reassignment_service import ReassignmentService

            reassignment_service = ReassignmentService(self.session)
            result = await reassignment_service.reassign_to_next_candidate(incident.id)

            if result.success:
                logger.info(
                    f"✅ Reasignación automática tras cancelación mutua para incidente {incident.id}"
                )
            else:
                logger.warning(
                    f"⚠️ No se pudo reasignar automáticamente el incidente {incident.id}: "
                    f"{result.error_message}"
                )

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
