"""
Service para gestión de incidentes.
"""
from datetime import datetime, UTC
from typing import List, Optional, Tuple

from sqlalchemy import update, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_logger, NotFoundException, ForbiddenException
from ...core.websocket_events import emit_to_incident_room, EventTypes
from ...models.incidente import Incidente
from ...models.evidencia import Evidencia
from ...models.evidencia_imagen import EvidenciaImagen
from ...models.evidencia_audio import EvidenciaAudio
from ...models.vehiculo import Vehiculo
from ...models.technician import Technician
from .repository import IncidenteRepository
from .schemas import IncidenteCreateRequest

logger = get_logger(__name__)


class IncidenteService:
    """Service para lógica de negocio de incidentes."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = IncidenteRepository(session)
    
    async def create_incidente(
        self,
        client_id: int,
        request: IncidenteCreateRequest
    ) -> Incidente:
        """Crear un nuevo incidente/emergencia vehicular."""
        # Verificar que el vehículo existe y pertenece al cliente
        from sqlalchemy import select
        result = await self.session.execute(
            select(Vehiculo).where(
                Vehiculo.id == request.vehiculo_id,
                Vehiculo.client_id == client_id,
                Vehiculo.is_active == True
            )
        )
        vehiculo = result.scalar_one_or_none()
        
        if not vehiculo:
            raise NotFoundException(
                f"Vehículo con ID {request.vehiculo_id} no encontrado o no pertenece al cliente"
            )
        
        # Crear el incidente
        incidente = Incidente(
            client_id=client_id,
            vehiculo_id=request.vehiculo_id,
            latitude=request.latitude,
            longitude=request.longitude,
            direccion_referencia=request.direccion_referencia,
            descripcion=request.descripcion,
            estado_actual="pendiente",
            es_ambiguo=False,  # Se actualizará cuando se procese con IA
        )
        
        # Agregar a la sesión y hacer flush
        self.session.add(incidente)
        await self.session.flush()
        await self.session.refresh(incidente)
        created_incidente = incidente
        
        # Crear evidencias de texto (descripción principal)
        evidencia_texto = Evidencia(
            incidente_id=created_incidente.id,
            uploaded_by_user_id=client_id,
            tipo="TEXT",
            descripcion=request.descripcion,
        )
        evidencia_texto_created = await self.repository.create_evidencia(evidencia_texto)
        
        # Crear evidencias de imágenes
        if request.imagenes:
            evidencia_imagenes = Evidencia(
                incidente_id=created_incidente.id,
                uploaded_by_user_id=client_id,
                tipo="IMAGE",
                descripcion="Imágenes del incidente",
            )
            evidencia_img_created = await self.repository.create_evidencia(evidencia_imagenes)
            
            for imagen_url in request.imagenes:
                evidencia_imagen = EvidenciaImagen(
                    evidencia_id=evidencia_img_created.id,
                    file_url=imagen_url,
                    file_name="incident_image.jpg",  # Nombre genérico por ahora
                    file_type="image",
                    mime_type="image/jpeg",
                    size=0,  # Se actualizará si se tiene la info
                    uploaded_by=client_id,
                )
                evidencia_imagen_created = await self.repository.create_evidencia_imagen(evidencia_imagen)
                # Emit image evidence event after each image is saved
                await emit_to_incident_room(
                    incident_id=created_incidente.id,
                    event_type=EventTypes.EVIDENCE_IMAGE_UPLOADED,
                    data={
                        "evidence_id": evidencia_img_created.id,
                        "incident_id": created_incidente.id,
                        "evidence_type": "image",
                        "file_url": imagen_url,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
        
        # Crear evidencias de audios
        if request.audios:
            evidencia_audios = Evidencia(
                incidente_id=created_incidente.id,
                uploaded_by_user_id=client_id,
                tipo="AUDIO",
                descripcion="Audios del incidente",
            )
            evidencia_audio_created = await self.repository.create_evidencia(evidencia_audios)
            
            for audio_url in request.audios:
                evidencia_audio = EvidenciaAudio(
                    evidencia_id=evidencia_audio_created.id,
                    file_url=audio_url,
                    file_name="incident_audio.mp3",  # Nombre genérico por ahora
                    file_type="audio",
                    mime_type="audio/mpeg",
                    size=0,  # Se actualizará si se tiene la info
                    uploaded_by=client_id,
                )
                evidencia_audio_item_created = await self.repository.create_evidencia_audio(evidencia_audio)
                # Emit audio evidence event after each audio is saved
                await emit_to_incident_room(
                    incident_id=created_incidente.id,
                    event_type=EventTypes.EVIDENCE_AUDIO_UPLOADED,
                    data={
                        "evidence_id": evidencia_audio_created.id,
                        "incident_id": created_incidente.id,
                        "evidence_type": "audio",
                        "file_url": audio_url,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
        
        # Emit generic evidence_uploaded for the text evidence
        await emit_to_incident_room(
            incident_id=created_incidente.id,
            event_type=EventTypes.EVIDENCE_UPLOADED,
            data={
                "evidence_id": evidencia_texto_created.id,
                "incident_id": created_incidente.id,
                "evidence_type": "text",
                "file_url": None,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        
        # Commit all changes
        await self.session.commit()
        
        logger.info(
            "Incidente creado",
            incidente_id=created_incidente.id,
            client_id=client_id,
            vehiculo_id=request.vehiculo_id,
            estado="pendiente"
        )

        # Trigger asynchronous AI processing and automatic assignment without delaying the incident response.
        try:
            from .ai_service import IncidentAIService

            IncidentAIService.schedule_incident_processing(created_incidente.id)
            
            # Schedule automatic assignment after AI processing using asyncio
            import asyncio
            from ...modules.assignment.services import IntelligentAssignmentService
            
            # Create background task for automatic assignment
            async def auto_assign_after_ai():
                """Background task to assign incident after AI processing completes."""
                try:
                    # Wait for AI processing to complete (check every second, max 15 seconds)
                    from ...core.database import get_session_factory
                    session_factory = get_session_factory()
                    
                    max_wait_seconds = 15
                    for i in range(max_wait_seconds):
                        await asyncio.sleep(1)
                        
                        # Check if AI analysis is complete
                        async with session_factory() as check_session:
                            from ...models.incidente import Incidente
                            from sqlalchemy import select
                            
                            result = await check_session.execute(
                                select(Incidente).where(Incidente.id == created_incidente.id)
                            )
                            incident = result.scalar_one_or_none()
                            
                            # AI is complete if prioridad_ia and categoria_ia are set
                            if incident and incident.prioridad_ia and incident.categoria_ia:
                                logger.info(
                                    f"AI analysis complete for incident {created_incidente.id} "
                                    f"(prioridad={incident.prioridad_ia}, categoria={incident.categoria_ia}) "
                                    f"after {i+1} seconds"
                                )
                                break
                    else:
                        logger.warning(
                            f"AI analysis not complete after {max_wait_seconds} seconds, "
                            f"proceeding with assignment anyway"
                        )
                    
                    # Now assign with AI-determined priority
                    async with session_factory() as bg_session:
                        assignment_service = IntelligentAssignmentService(bg_session)
                        result = await assignment_service.assign_incident_automatically(
                            incident_id=created_incidente.id,
                            force_ai_analysis=False  # AI already ran
                        )
                        
                        if result.success:
                            logger.info(
                                f"Automatic assignment successful for new incident {created_incidente.id}: "
                                f"workshop={result.assigned_workshop.workshop_name}, "
                                f"technician={result.assigned_technician.first_name} {result.assigned_technician.last_name}"
                            )
                        else:
                            logger.warning(
                                f"Automatic assignment failed for new incident {created_incidente.id}: "
                                f"{result.error_message}"
                            )
                            
                except Exception as e:
                    logger.error(f"Background auto-assignment failed for incident {created_incidente.id}: {str(e)}", exc_info=True)
            
            # Schedule the background task using asyncio.create_task
            asyncio.create_task(auto_assign_after_ai())
            logger.info(f"Scheduled auto-assignment task for incident {created_incidente.id}")
            
        except Exception as exc:
            logger.warning(
                "Failed to schedule incident AI processing and auto-assignment",
                incidente_id=created_incidente.id,
                error=str(exc),
            )
        
        return created_incidente
    
    async def get_incidente(
        self,
        incidente_id: int,
        user_id: int,
        user_type: str
    ) -> Incidente:
        """Obtener un incidente por ID."""
        incidente = await self.repository.find_by_id(incidente_id)
        
        if not incidente:
            raise NotFoundException(f"Incidente con ID {incidente_id} no encontrado")
        
        # Verificar permisos según tipo de usuario
        if user_type == "client" and incidente.client_id != user_id:
            raise ForbiddenException("No tienes permiso para ver este incidente")
        elif user_type == "workshop":
            # Los talleres pueden ver:
            # 1. Incidentes asignados a ellos
            # 2. Incidentes pendientes (para poder aceptarlos)
            if incidente.taller_id is not None and incidente.taller_id != user_id:
                raise ForbiddenException("No tienes permiso para ver este incidente")
        elif user_type == "technician":
            # Verificar que el técnico pertenece al taller asignado
            from sqlalchemy import select
            from ...models.technician import Technician
            result = await self.session.execute(
                select(Technician).where(Technician.id == user_id)
            )
            technician = result.scalar_one_or_none()
            if not technician or technician.workshop_id != incidente.taller_id:
                raise ForbiddenException("No tienes permiso para ver este incidente")
        
        return incidente
    
    async def get_client_incidentes(
        self,
        client_id: int,
        estado: Optional[str] = None
    ) -> List[Incidente]:
        """Obtener incidentes de un cliente."""
        return await self.repository.find_by_client(client_id, estado)
    
    async def get_taller_incidentes(
        self,
        taller_id: int,
        estado: Optional[str] = None
    ) -> List[Incidente]:
        """Obtener incidentes asignados a un taller."""
        return await self.repository.find_by_taller(taller_id, estado)
    
    async def get_technician_incidentes(
        self,
        technician_id: int,
        estado: Optional[str] = None
    ) -> List[Incidente]:
        """Obtener incidentes asignados a un técnico."""
        return await self.repository.find_by_technician(technician_id, estado)
    
    async def get_pending_incidentes(self, taller_id: Optional[int] = None) -> List[Incidente]:
        """Obtener incidentes pendientes de asignación."""
        return await self.repository.find_pending_incidents(taller_id)
    
    async def get_suggested_technician_info(
        self,
        incidente_id: int,
        taller_id: int
    ) -> Optional[dict]:
        """
        Obtener información del técnico sugerido por la IA para un incidente.
        
        Args:
            incidente_id: ID del incidente
            taller_id: ID del taller
            
        Returns:
            Diccionario con información del técnico sugerido o None si no existe
        """
        from ...models.assignment_attempt import AssignmentAttempt
        from ...models.technician import Technician
        from sqlalchemy import select, and_
        
        # Buscar el assignment_attempt pendiente o con timeout para este taller
        result = await self.session.execute(
            select(AssignmentAttempt, Technician)
            .join(Technician, AssignmentAttempt.technician_id == Technician.id, isouter=True)
            .where(
                and_(
                    AssignmentAttempt.incident_id == incidente_id,
                    AssignmentAttempt.workshop_id == taller_id,
                    AssignmentAttempt.status.in_(['pending', 'timeout'])
                )
            )
            .order_by(AssignmentAttempt.created_at.desc())
            .limit(1)
        )
        
        row = result.first()
        if not row:
            return None
        
        assignment_attempt, technician = row
        
        # Si no hay técnico sugerido, retornar None
        if not technician:
            return None
        
        return {
            "technician_id": technician.id,
            "first_name": technician.first_name,
            "last_name": technician.last_name,
            "phone": technician.phone,
            "final_score": float(assignment_attempt.final_score),
            "distance_km": float(assignment_attempt.distance_km),
            "ai_reasoning": assignment_attempt.ai_reasoning,
            "assignment_strategy": assignment_attempt.assignment_strategy
        }
    
    async def accept_incidente(
        self,
        incidente_id: int,
        taller_id: int,
        accept_suggested_technician: bool = False
    ) -> Incidente:
        """
        Aceptar un incidente y asignarlo al taller.
        
        Args:
            incidente_id: ID del incidente
            taller_id: ID del taller que acepta
            accept_suggested_technician: Si True, acepta el técnico sugerido por la IA
        
        Returns:
            Incidente actualizado
        """
        # Obtener el incidente
        incidente = await self.repository.find_by_id(incidente_id)
        
        if not incidente:
            raise NotFoundException(f"Incidente con ID {incidente_id} no encontrado")
        
        # Verificar que el incidente esté pendiente
        if incidente.estado_actual != "pendiente":
            from ...core import ValidationException
            raise ValidationException(f"El incidente ya no está pendiente (estado actual: {incidente.estado_actual})")
        
        # Buscar el assignment_attempt para obtener el técnico sugerido
        suggested_technician_id = None
        if accept_suggested_technician:
            from ...models.assignment_attempt import AssignmentAttempt
            from sqlalchemy import select, and_
            
            result = await self.session.execute(
                select(AssignmentAttempt)
                .where(
                    and_(
                        AssignmentAttempt.incident_id == incidente_id,
                        AssignmentAttempt.workshop_id == taller_id,
                        AssignmentAttempt.status.in_(['pending', 'timeout'])
                    )
                )
                .order_by(AssignmentAttempt.created_at.desc())
                .limit(1)
            )
            assignment_attempt = result.scalar_one_or_none()
            
            if assignment_attempt and assignment_attempt.technician_id:
                suggested_technician_id = assignment_attempt.technician_id
                logger.info(
                    f"Técnico sugerido encontrado: {suggested_technician_id} (status: {assignment_attempt.status})",
                    incidente_id=incidente_id,
                    taller_id=taller_id
                )
        
        # Asignar el taller
        incidente.taller_id = taller_id
        incidente.assigned_at = datetime.now(UTC)
        
        # Marcar el assignment_attempt como aceptado
        from ...models.assignment_attempt import AssignmentAttempt
        from sqlalchemy import select, and_
        
        result = await self.session.execute(
            select(AssignmentAttempt)
            .where(
                and_(
                    AssignmentAttempt.incident_id == incidente_id,
                    AssignmentAttempt.workshop_id == taller_id,
                    AssignmentAttempt.status.in_(['pending', 'timeout'])
                )
            )
            .order_by(AssignmentAttempt.created_at.desc())
            .limit(1)
        )
        assignment_attempt = result.scalar_one_or_none()
        
        if assignment_attempt:
            assignment_attempt.status = 'accepted'
            assignment_attempt.responded_at = datetime.now(UTC)
            assignment_attempt.response_message = 'Solicitud aceptada por el taller'
            logger.info(
                f"Assignment attempt marcado como aceptado",
                incidente_id=incidente_id,
                taller_id=taller_id,
                previous_status=assignment_attempt.status
            )
        
        # 🔥 CANCELAR TODOS LOS TIMEOUTS PENDIENTES para este incidente
        # Cuando un taller acepta, ya no necesitamos más timeouts
        await self._cancel_pending_timeouts(incidente_id)
        
        # Si acepta el técnico sugerido y existe, asignarlo y cambiar a "en_proceso"
        if suggested_technician_id:
            incidente.tecnico_id = suggested_technician_id
            incidente.estado_actual = "en_proceso"
            
            # Marcar técnico como en servicio
            from ...models.technician import Technician
            technician = await self.session.get(Technician, suggested_technician_id)
            if technician:
                technician.is_on_duty = True
                technician.is_available = False  # No disponible mientras está en servicio
                technician.updated_at = datetime.now(UTC)
                logger.info(
                    f"Técnico {suggested_technician_id} marcado como en servicio (is_on_duty=True)"
                )
            
            # Crear sesión de tracking
            from ...models.tracking_session import TrackingSession
            tracking_session = TrackingSession(
                incidente_id=incidente_id,
                technician_id=suggested_technician_id,
                started_at=datetime.now(UTC),
                is_active=True
            )
            self.session.add(tracking_session)
            
            logger.info(
                "Incidente aceptado con técnico sugerido",
                incidente_id=incidente_id,
                taller_id=taller_id,
                tecnico_id=suggested_technician_id,
                estado="en_proceso"
            )
        else:
            # Solo asignar taller, sin técnico (asignación manual posterior)
            incidente.estado_actual = "asignado"
            
            logger.info(
                "Incidente aceptado sin técnico (asignación manual)",
                incidente_id=incidente_id,
                taller_id=taller_id,
                estado="asignado"
            )
        
        # Commit changes
        await self.session.commit()
        
        # Crear conversación de chat automáticamente al aceptar el incidente
        from ...modules.chat.services import ChatService
        chat_service = ChatService(self.session)
        
        try:
            conversation = await chat_service.get_or_create_conversation(
                incident_id=incidente_id,
                client_id=incidente.client_id,
                workshop_id=taller_id
            )
            
            # Enviar mensaje del sistema informando que el taller aceptó
            await chat_service.send_message(
                incident_id=incidente_id,
                sender_id=taller_id,  # El taller es el remitente
                message_text=f"✅ El taller ha aceptado tu solicitud. {'Un técnico ha sido asignado y está en camino.' if suggested_technician_id else 'Pronto asignaremos un técnico.'}",
                message_type="system"
            )
            
            logger.info(
                f"Conversación de chat creada para incidente {incidente_id}",
                conversation_id=conversation.id
            )
        except Exception as e:
            logger.error(
                f"Error al crear conversación de chat para incidente {incidente_id}: {str(e)}",
                exc_info=True
            )
            # No fallar la aceptación si falla la creación del chat
        
        # Recargar el incidente con las relaciones necesarias para serialización
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        
        result = await self.session.execute(
            select(Incidente)
            .options(
                selectinload(Incidente.workshop),
                selectinload(Incidente.technician)
            )
            .where(Incidente.id == incidente_id)
        )
        incidente = result.scalar_one()
        
        # Emit WebSocket event for assignment_accepted (Task 14)
        from ...core.websocket_events import emit_to_user, emit_to_incident_room, emit_to_admins, EventTypes
        
        # Get workshop name
        workshop_name = incidente.workshop.workshop_name if incidente.workshop else "Unknown"
        
        # Prepare payload
        assignment_payload = {
            "attempt_id": assignment_attempt.id if assignment_attempt else None,
            "incident_id": incidente_id,
            "workshop_id": taller_id,
            "workshop_name": workshop_name,
            "response_status": "accepted",
            "timestamp": datetime.now(UTC).isoformat()
        }
        
        # Send to client (personal message)
        await emit_to_user(
            user_id=incidente.client_id,
            event_type=EventTypes.ASSIGNMENT_ACCEPTED,
            data=assignment_payload
        )
        
        # Broadcast to incident room
        await emit_to_incident_room(
            incident_id=incidente_id,
            event_type=EventTypes.ASSIGNMENT_ACCEPTED,
            data=assignment_payload
        )
        
        logger.info(
            f"WebSocket event '{EventTypes.ASSIGNMENT_ACCEPTED}' emitted for incident {incidente_id}"
        )
        
        # Notificar al cliente que su solicitud fue aceptada
        from ...modules.push_notifications.services import PushNotificationService, PushNotificationData
        
        try:
            push_service = PushNotificationService(self.session)
            
            # Notificar al cliente
            if suggested_technician_id:
                notification_title = "✅ ¡Solicitud aceptada!"
                notification_body = "Tu solicitud ha sido aceptada y un técnico está en camino."
            else:
                notification_title = "✅ ¡Solicitud aceptada!"
                notification_body = "Tu solicitud ha sido aceptada. Pronto asignaremos un técnico."
            
            await push_service.send_to_user(
                user_id=incidente.client_id,
                notification_data=PushNotificationData(
                    title=notification_title,
                    body=notification_body,
                    data={
                        "type": "incident_accepted",
                        "incident_id": str(incidente_id),
                        "workshop_id": str(taller_id),
                        "technician_id": str(suggested_technician_id) if suggested_technician_id else None,
                        "click_action": f"/incidents/{incidente_id}"  # For mobile apps
                    },
                    click_action=None  # Set to None for web push
                ),
                save_to_db=True
            )
            
            # Si se asignó técnico, notificar al técnico
            if suggested_technician_id:
                await push_service.send_to_user(
                    user_id=suggested_technician_id,
                    notification_data=PushNotificationData(
                        title="🚗 Nueva asignación",
                        body=f"Has sido asignado a un nuevo servicio. Dirígete al lugar del incidente.",
                        data={
                            "type": "technician_assigned",
                            "incident_id": str(incidente_id),
                            "workshop_id": str(taller_id),
                            "click_action": f"/incidents/{incidente_id}"  # For mobile apps
                        },
                        click_action=None  # Set to None for web push
                    ),
                    save_to_db=True
                )
            
            logger.info(f"Notificaciones push enviadas para incidente {incidente_id}")
            
        except Exception as e:
            logger.error(f"Error al enviar notificaciones push: {str(e)}", exc_info=True)
            # No fallar la aceptación si fallan las notificaciones
        
        return incidente
    
    async def reject_incidente(
        self,
        incidente_id: int,
        taller_id: int,
        motivo: str
    ) -> Incidente:
        """Rechazar un incidente."""
        # Obtener el incidente
        incidente = await self.repository.find_by_id(incidente_id)
        
        if not incidente:
            raise NotFoundException(f"Incidente con ID {incidente_id} no encontrado")
        
        # Verificar que el incidente esté pendiente
        if incidente.estado_actual != "pendiente":
            from ...core import ValidationException
            raise ValidationException(f"El incidente ya no está pendiente (estado actual: {incidente.estado_actual})")
        
        # Guardar el rechazo en la base de datos
        from ...models.rechazo_taller import RechazoTaller
        rechazo = RechazoTaller(
            incidente_id=incidente_id,
            taller_id=taller_id,
            motivo=motivo
        )
        self.session.add(rechazo)
        
        # Mark the assignment_attempt as rejected
        from ...models.assignment_attempt import AssignmentAttempt
        from sqlalchemy import select, and_
        
        result = await self.session.execute(
            select(AssignmentAttempt)
            .where(
                and_(
                    AssignmentAttempt.incident_id == incidente_id,
                    AssignmentAttempt.workshop_id == taller_id,
                    AssignmentAttempt.status.in_(['pending', 'timeout'])
                )
            )
            .order_by(AssignmentAttempt.created_at.desc())
            .limit(1)
        )
        assignment_attempt = result.scalar_one_or_none()
        
        if assignment_attempt:
            assignment_attempt.status = 'rejected'
            assignment_attempt.responded_at = datetime.now(UTC)
            assignment_attempt.response_message = motivo
        
        await self.session.commit()
        
        logger.info(
            "Incidente rechazado y guardado en BD",
            incidente_id=incidente_id,
            taller_id=taller_id,
            motivo=motivo
        )
        
        # Emit WebSocket event for assignment_rejected (Task 14)
        from ...core.websocket_events import emit_to_admins, EventTypes
        from ...models.workshop import Workshop
        
        # Get workshop name
        workshop = await self.session.get(Workshop, taller_id)
        workshop_name = workshop.workshop_name if workshop else "Unknown"
        
        rejection_payload = {
            "attempt_id": assignment_attempt.id if assignment_attempt else None,
            "incident_id": incidente_id,
            "workshop_id": taller_id,
            "workshop_name": workshop_name,
            "response_status": "rejected",
            "rejection_reason": motivo,
            "timestamp": datetime.now(UTC).isoformat()
        }
        
        await emit_to_admins(
            event_type=EventTypes.ASSIGNMENT_REJECTED,
            data=rejection_payload
        )
        
        logger.info(
            f"WebSocket event '{EventTypes.ASSIGNMENT_REJECTED}' emitted for incident {incidente_id}"
        )
        
        # TODO: El motor de asignación debería buscar otro taller
        # TODO: Notificar al cliente que se está buscando otro proveedor
        
        # Por ahora, el incidente permanece pendiente para que otro taller lo tome
        return incidente
    
    async def anular_asignacion_ambigua(
        self,
        incidente_id: int,
        taller_id: int,
        motivo: str
    ) -> Incidente:
        """
        Anular asignación de un caso ambiguo después de chatear con el cliente (CU11).
        
        Este método es específico para casos ambiguos donde el taller:
        1. Ya aceptó la solicitud
        2. Chateó con el cliente para aclarar el problema
        3. Determinó que no puede atender el caso
        
        Validaciones:
        - El incidente debe ser ambiguo (es_ambiguo = True)
        - El incidente debe estar asignado al taller que solicita anular
        - Debe haber al menos un mensaje de chat entre taller y cliente
        
        Args:
            incidente_id: ID del incidente
            taller_id: ID del taller que anula
            motivo: Motivo de la anulación
            
        Returns:
            Incidente actualizado
            
        Raises:
            NotFoundException: Si el incidente no existe
            ValidationException: Si no cumple las validaciones
            ForbiddenException: Si el taller no es el asignado
        """
        # Obtener el incidente
        incidente = await self.repository.find_by_id(incidente_id)
        
        if not incidente:
            raise NotFoundException(f"Incidente con ID {incidente_id} no encontrado")
        
        # Validación 1: Verificar que el incidente sea ambiguo
        if not incidente.es_ambiguo:
            from ...core import ValidationException
            raise ValidationException(
                "Este endpoint solo puede usarse para casos ambiguos. "
                "Para rechazar solicitudes normales, use el endpoint /rechazar"
            )
        
        # Validación 2: Verificar que el taller esté asignado
        if incidente.taller_id != taller_id:
            if incidente.taller_id is None:
                from ...core import ValidationException
                raise ValidationException(
                    "No puedes anular una asignación que no existe. "
                    "El incidente no está asignado a ningún taller."
                )
            else:
                raise ForbiddenException(
                    f"No puedes anular este incidente. Está asignado a otro taller."
                )
        
        # Validación 3: Verificar que el incidente esté en estado asignado o en_proceso
        if incidente.estado_actual not in ["asignado", "en_proceso"]:
            from ...core import ValidationException
            raise ValidationException(
                f"No se puede anular un incidente en estado '{incidente.estado_actual}'. "
                f"Solo se pueden anular incidentes asignados o en proceso."
            )
        
        # Validación 4: Verificar que haya al menos un mensaje de chat
        from sqlalchemy import select, func
        from ...models.message import Message
        
        message_count = await self.session.scalar(
            select(func.count(Message.id))
            .where(Message.incident_id == incidente_id)
        )
        
        if not message_count or message_count == 0:
            from ...core import ValidationException
            raise ValidationException(
                "No se puede anular la asignación sin haber chateado con el cliente. "
                "Para casos ambiguos, debes comunicarte con el cliente antes de anular."
            )
        
        logger.info(
            f"Validaciones pasadas para anulación de caso ambiguo. "
            f"Incidente {incidente_id} tiene {message_count} mensajes de chat.",
            incidente_id=incidente_id,
            taller_id=taller_id,
            es_ambiguo=incidente.es_ambiguo,
            estado_actual=incidente.estado_actual
        )
        
        # Guardar el rechazo en la base de datos
        from ...models.rechazo_taller import RechazoTaller
        rechazo = RechazoTaller(
            incidente_id=incidente_id,
            taller_id=taller_id,
            motivo=f"[Caso ambiguo anulado] {motivo}"
        )
        self.session.add(rechazo)
        
        # Registrar en historial de servicio
        from ...models.historial_servicio import HistorialServicio
        from ...models.estados_servicio import EstadosServicio
        
        # Obtener estado_id para "pendiente"
        estado_pendiente = await self.session.scalar(
            select(EstadosServicio).where(EstadosServicio.nombre == "pendiente")
        )
        
        if estado_pendiente:
            historial = HistorialServicio(
                incidente_id=incidente_id,
                estado_id=estado_pendiente.id,
                comentario=f"Caso ambiguo anulado por taller {taller_id}. Estado anterior: {incidente.estado_actual}. Motivo: {motivo}",
                changed_by_user_id=taller_id
            )
            self.session.add(historial)
        else:
            logger.warning(f"Estado 'pendiente' no encontrado en estados_servicio")
        
        # Liberar al técnico si estaba asignado
        if incidente.tecnico_id:
            # Finalizar sesión de tracking
            from ...models.tracking_session import TrackingSession
            await self.session.execute(
                update(TrackingSession)
                .where(
                    TrackingSession.incidente_id == incidente_id,
                    TrackingSession.is_active == True
                )
                .values(
                    is_active=False,
                    ended_at=datetime.now(UTC)
                )
            )
            
            # Liberar técnico
            technician = await self.session.get(Technician, incidente.tecnico_id)
            if technician:
                technician.is_on_duty = False
                technician.updated_at = datetime.now(UTC)
                logger.info(
                    f"Técnico {incidente.tecnico_id} liberado por anulación de caso ambiguo"
                )
        
        # Limpiar asignación y volver a pendiente
        incidente.taller_id = None
        incidente.tecnico_id = None
        incidente.estado_actual = "pendiente"
        incidente.assigned_at = None
        incidente.updated_at = datetime.now(UTC)
        
        # Marcar assignment_attempt como rejected
        from ...models.assignment_attempt import AssignmentAttempt
        from sqlalchemy import and_
        
        await self.session.execute(
            update(AssignmentAttempt)
            .where(
                and_(
                    AssignmentAttempt.incident_id == incidente_id,
                    AssignmentAttempt.workshop_id == taller_id,
                    AssignmentAttempt.status == 'accepted'
                )
            )
            .values(
                status='rejected',
                response_message=f'Caso ambiguo anulado: {motivo}',
                responded_at=datetime.now(UTC)
            )
        )
        
        await self.session.commit()
        await self.session.refresh(incidente)
        
        logger.info(
            "Asignación de caso ambiguo anulada exitosamente",
            incidente_id=incidente_id,
            taller_id=taller_id,
            motivo=motivo,
            message_count=message_count
        )
        
        # Notificar al cliente sobre la anulación
        from ...modules.push_notifications.services import PushNotificationService, PushNotificationData
        
        try:
            push_service = PushNotificationService(self.session)
            await push_service.send_to_user(
                user_id=incidente.client_id,
                notification_data=PushNotificationData(
                    title="🔄 Buscando nuevo taller",
                    body=f"El taller no pudo atender tu solicitud después de revisar el caso. Estamos buscando otro taller disponible.",
                    data={
                        "type": "incident_ambiguous_cancelled",
                        "incident_id": str(incidente_id),
                        "priority": incidente.prioridad_ia or "media",
                        "action": "view_incident",
                        "action_url": f"/incidents/{incidente_id}"
                    }
                )
            )
            logger.info(f"✅ Notified client {incidente.client_id} about ambiguous case cancellation")
        except Exception as e:
            logger.error(f"Failed to notify client about ambiguous case cancellation: {str(e)}")
        
        return incidente
    
    async def get_all_incidentes(self) -> List[Incidente]:
        """
        Obtener incidentes sin taller asignado (solo admin).
        
        El admin ve incidentes pendientes que no tienen taller asignado,
        es decir, incidencias que no fueron atendidas y requieren intervención manual.
        """
        # Usar el método existente find_pending_incidents sin taller_id
        # Esto devuelve todos los incidentes en estado 'pendiente'
        return await self.repository.find_pending_incidents(taller_id=None, skip=0, limit=10000)
    
    async def get_all_incidentes_by_estado(self, estado: str) -> List[Incidente]:
        """Obtener todos los incidentes por estado (solo admin)."""
        return await self.repository.find_by_estado(estado, skip=0, limit=10000)
    
    async def update_estado(
        self,
        incidente_id: int,
        nuevo_estado: str,
        user_id: int,
        user_type: str
    ) -> Incidente:
        """Actualizar el estado de un incidente."""
        incidente = await self.get_incidente(incidente_id, user_id, user_type)
        
        # Validar transición de estado
        estados_validos = ["pendiente", "asignado", "en_proceso", "resuelto", "cancelado"]
        if nuevo_estado not in estados_validos:
            from ...core import ValidationException
            raise ValidationException(f"Estado '{nuevo_estado}' no es válido")
        
        # Actualizar estado
        incidente.estado_actual = nuevo_estado
        incidente.updated_at = datetime.now(UTC)
        
        # Si el incidente se resuelve o cancela, liberar al técnico
        if nuevo_estado in ["resuelto", "cancelado"] and incidente.tecnico_id:
            # Usar el objeto directamente en lugar de update() para evitar problemas con herencia
            technician = await self.session.get(Technician, incidente.tecnico_id)
            if technician:
                technician.is_on_duty = False
                technician.is_available = True  # Marcar como disponible nuevamente
                technician.updated_at = datetime.now(UTC)
                logger.info(
                    f"Técnico {incidente.tecnico_id} liberado (is_on_duty=False, is_available=True) por incidente {incidente_id} en estado '{nuevo_estado}'"
                )
                
                # Notificar cambio de disponibilidad via WebSocket
                from ...core.websocket import manager
                if technician.workshop_id:
                    await manager.send_personal_message(technician.workshop_id, {
                        "type": "technician_status_update",
                        "data": {
                            "technician_id": incidente.tecnico_id,
                            "is_available": True,
                            "is_on_duty": False,
                            "timestamp": datetime.now(UTC).isoformat()
                        }
                    })
        
        await self.session.commit()
        await self.session.refresh(incidente)
        
        logger.info(
            f"Estado de incidente actualizado a '{nuevo_estado}'",
            incidente_id=incidente_id,
            user_id=user_id,
            user_type=user_type
        )
        
        return incidente
    
    async def cancel_incidente(
        self,
        incidente_id: int,
        user_id: int,
        user_type: str,
        motivo: Optional[str] = None
    ) -> Incidente:
        """
        Cancelar un incidente.
        
        Permite al cliente cancelar su propio incidente si:
        - Está en estado pendiente o asignado
        - Lo solucionó por su cuenta
        - Ya no necesita el servicio
        
        Args:
            incidente_id: ID del incidente a cancelar
            user_id: ID del usuario que cancela
            user_type: Tipo de usuario (client, admin)
            motivo: Motivo opcional de la cancelación
            
        Returns:
            Incidente cancelado
        """
        # Obtener el incidente
        incidente = await self.repository.find_by_id(incidente_id)
        
        if not incidente:
            raise NotFoundException(f"Incidente con ID {incidente_id} no encontrado")
        
        # Verificar permisos
        if user_type == "client":
            # El cliente solo puede cancelar sus propios incidentes
            if incidente.client_id != user_id:
                raise ForbiddenException("No tienes permiso para cancelar este incidente")
        elif user_type not in ["admin", "workshop"]:
            raise ForbiddenException("No tienes permiso para cancelar incidentes")
        
        # Verificar que el incidente se pueda cancelar
        if incidente.estado_actual in ["resuelto", "cancelado"]:
            from ...core import ValidationException
            raise ValidationException(
                f"No se puede cancelar un incidente en estado '{incidente.estado_actual}'"
            )
        
        # Si está en proceso, verificar que sea admin o el cliente
        if incidente.estado_actual == "en_proceso" and user_type not in ["admin", "client"]:
            from ...core import ValidationException
            raise ValidationException(
                "Solo el cliente o un administrador pueden cancelar un incidente en proceso"
            )
        
        # Actualizar estado a cancelado
        estado_anterior = incidente.estado_actual
        incidente.estado_actual = "cancelado"
        incidente.updated_at = datetime.now(UTC)
        
        # Guardar en historial
        from ...models.historial_servicio import HistorialServicio
        from ...models.estados_servicio import EstadosServicio
        
        estado_cancelado = await self.session.scalar(
            select(EstadosServicio).where(EstadosServicio.nombre == "cancelado")
        )
        
        if estado_cancelado:
            comentario = f"Cancelado por {user_type}. Estado anterior: {estado_anterior}"
            if motivo:
                comentario += f". Motivo: {motivo}"
            
            historial = HistorialServicio(
                incidente_id=incidente_id,
                estado_id=estado_cancelado.id,
                comentario=comentario,
                changed_by_user_id=user_id
            )
            self.session.add(historial)
        else:
            logger.warning(f"Estado 'cancelado' no encontrado en estados_servicio")
        
        # Si había un técnico asignado, liberar la sesión de tracking y el técnico
        if incidente.tecnico_id:
            from ...models.tracking_session import TrackingSession
            
            # Liberar sesión de tracking
            await self.session.execute(
                update(TrackingSession)
                .where(
                    TrackingSession.incidente_id == incidente_id,
                    TrackingSession.is_active == True
                )
                .values(
                    is_active=False,
                    ended_at=datetime.now(UTC)
                )
            )
            
            # Liberar técnico (marcar como no en servicio y disponible)
            # Usar el objeto directamente en lugar de update() para evitar problemas con herencia
            technician = await self.session.get(Technician, incidente.tecnico_id)
            if technician:
                technician.is_on_duty = False
                technician.is_available = True  # Marcar como disponible nuevamente
                technician.updated_at = datetime.now(UTC)
                logger.info(
                    f"Técnico {incidente.tecnico_id} liberado (is_on_duty=False, is_available=True) por cancelación de incidente {incidente_id}"
                )
                
                # Notificar cambio de disponibilidad via WebSocket
                from ...core.websocket import manager
                if technician.workshop_id:
                    await manager.send_personal_message(technician.workshop_id, {
                        "type": "technician_status_update",
                        "data": {
                            "technician_id": incidente.tecnico_id,
                            "is_available": True,
                            "is_on_duty": False,
                            "timestamp": datetime.now(UTC).isoformat()
                        }
                    })
        
        # Marcar intentos de asignación como cancelados
        from ...models.assignment_attempt import AssignmentAttempt
        from sqlalchemy import and_
        
        await self.session.execute(
            update(AssignmentAttempt)
            .where(
                and_(
                    AssignmentAttempt.incident_id == incidente_id,
                    AssignmentAttempt.status == 'pending'
                )
            )
            .values(
                status='cancelled',
                response_message='Incidente cancelado por el usuario',
                responded_at=datetime.now(UTC)
            )
        )
        
        await self.session.commit()
        await self.session.refresh(incidente)
        
        logger.info(
            f"Incidente cancelado",
            incidente_id=incidente_id,
            user_id=user_id,
            user_type=user_type,
            motivo=motivo or "Sin motivo especificado"
        )
        
        # TODO: Notificar al taller/técnico asignado si lo había
        # TODO: Notificar al cliente si fue cancelado por admin
        
        return incidente
    
    async def get_incidente_with_evidencias(
        self,
        incidente_id: int,
        user_id: int,
        user_type: str
    ) -> Tuple[Incidente, List[Evidencia], List[EvidenciaImagen], List[EvidenciaAudio]]:
        """Obtener incidente con todas sus evidencias."""
        incidente = await self.get_incidente(incidente_id, user_id, user_type)
        
        evidencias = await self.repository.find_evidencias_by_incidente(incidente_id)
        
        # Obtener imágenes y audios de todas las evidencias
        imagenes = []
        audios = []
        
        for evidencia in evidencias:
            if evidencia.tipo == "IMAGE":
                imgs = await self.repository.find_imagenes_by_evidencia(evidencia.id)
                imagenes.extend(imgs)
            elif evidencia.tipo == "AUDIO":
                auds = await self.repository.find_audios_by_evidencia(evidencia.id)
                audios.extend(auds)
        
        return incidente, evidencias, imagenes, audios

    async def delete_evidencia(
        self,
        evidencia_id: int,
        incident_id: int,
        user_id: int,
    ) -> None:
        """
        Eliminar una evidencia y emitir evento WebSocket.

        Args:
            evidencia_id: ID de la evidencia a eliminar
            incident_id: ID del incidente al que pertenece la evidencia
            user_id: ID del usuario que realiza la eliminación (para autorización)

        Raises:
            NotFoundException: Si la evidencia no existe
            ForbiddenException: Si el usuario no tiene permiso para eliminar la evidencia
        """
        result = await self.session.execute(
            select(Evidencia).where(Evidencia.id == evidencia_id)
        )
        evidencia = result.scalar_one_or_none()

        if not evidencia:
            raise NotFoundException(f"Evidencia con ID {evidencia_id} no encontrada")

        if evidencia.incidente_id != incident_id:
            raise ForbiddenException("La evidencia no pertenece al incidente especificado")

        if evidencia.uploaded_by_user_id != user_id:
            raise ForbiddenException("No tienes permiso para eliminar esta evidencia")

        await self.session.delete(evidencia)
        await self.session.commit()

        logger.info(
            "Evidencia eliminada",
            evidencia_id=evidencia_id,
            incident_id=incident_id,
            user_id=user_id,
        )

        # Emit evidence_deleted event to the incident room
        await emit_to_incident_room(
            incident_id=incident_id,
            event_type=EventTypes.EVIDENCE_DELETED,
            data={
                "evidence_id": evidencia_id,
                "incident_id": incident_id,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    async def _cancel_pending_timeouts(self, incidente_id: int) -> None:
        """
        Cancelar todos los timeouts pendientes para un incidente.
        
        Se llama cuando:
        - Un taller acepta la asignación
        - El incidente se resuelve
        - El incidente se cancela
        
        Args:
            incidente_id: ID del incidente
        """
        try:
            from ...models.assignment_attempt import AssignmentAttempt
            from sqlalchemy import and_
            
            # Marcar todos los intentos pendientes como cancelados
            result = await self.session.execute(
                update(AssignmentAttempt)
                .where(
                    and_(
                        AssignmentAttempt.incident_id == incidente_id,
                        AssignmentAttempt.status == 'pending'
                    )
                )
                .values(
                    status='cancelled',
                    response_message='Timeout cancelado - incidente aceptado por otro taller',
                    responded_at=datetime.now(UTC)
                )
            )
            
            cancelled_count = result.rowcount
            
            if cancelled_count > 0:
                logger.info(
                    f"🔥 Cancelados {cancelled_count} timeouts pendientes para incidente {incidente_id}"
                )
            
        except Exception as e:
            logger.error(f"Error cancelando timeouts para incidente {incidente_id}: {str(e)}")
            # No re-lanzar la excepción para no afectar el flujo principal
