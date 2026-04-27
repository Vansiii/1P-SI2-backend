"""
Service para gestión de incidentes.
"""
from datetime import datetime, UTC
from typing import List, Optional, Tuple

from sqlalchemy import update, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_logger, NotFoundException, ForbiddenException
from ...core.event_publisher import EventPublisher
from ...shared.schemas.events.incident import (
    IncidentCreatedEvent,
    IncidentAssignmentAcceptedEvent,
    IncidentAssignmentRejectedEvent,
    IncidentStatusChangedEvent,
    IncidentCancelledEvent
)
from ...shared.schemas.events.evidence import (
    EvidenceUploadedEvent,
    EvidenceImageUploadedEvent,
    EvidenceAudioUploadedEvent,
    EvidenceDeletedEvent
)
from ...shared.schemas.events.dashboard import (
    DashboardIncidentCountChangedEvent,
    DashboardActiveTechniciansChangedEvent
)
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
    
    async def _publish_incident_count_changed(
        self,
        status: str,
        delta: int
    ) -> None:
        """
        Publicar evento de cambio en contador de incidentes por estado.
        
        Args:
            status: Estado del incidente
            delta: Cambio en el contador (+1 para incremento, -1 para decremento)
        """
        try:
            # Calcular el contador actual para este estado
            count = await self.session.scalar(
                select(func.count(Incidente.id)).where(
                    Incidente.estado_actual == status
                )
            )
            
            # Crear y publicar evento
            event = DashboardIncidentCountChangedEvent(
                status=status,
                count=count or 0,
                delta=delta
            )
            
            await EventPublisher.publish(self.session, event)
            
            logger.info(
                f"✅ Evento DASHBOARD_INCIDENT_COUNT_CHANGED publicado: status={status}, count={count}, delta={delta}"
            )
            
        except Exception as e:
            logger.error(
                f"❌ Error publicando evento DASHBOARD_INCIDENT_COUNT_CHANGED: {str(e)}",
                exc_info=True
            )
    
    async def _publish_active_technicians_changed(self) -> None:
        """
        Publicar evento de cambio en contadores de técnicos activos.
        
        Calcula:
        - active_count: Técnicos con is_on_duty=True
        - available_count: Técnicos con is_available=True
        - on_duty_count: Técnicos con is_on_duty=True (mismo que active_count)
        """
        try:
            # Contar técnicos activos (en servicio)
            active_count = await self.session.scalar(
                select(func.count(Technician.id)).where(
                    Technician.is_on_duty == True
                )
            ) or 0
            
            # Contar técnicos disponibles
            available_count = await self.session.scalar(
                select(func.count(Technician.id)).where(
                    Technician.is_available == True
                )
            ) or 0
            
            # on_duty_count es lo mismo que active_count
            on_duty_count = active_count
            
            # Crear y publicar evento
            event = DashboardActiveTechniciansChangedEvent(
                active_count=active_count,
                available_count=available_count,
                on_duty_count=on_duty_count
            )
            
            await EventPublisher.publish(self.session, event)
            
            logger.info(
                f"✅ Evento DASHBOARD_ACTIVE_TECHNICIANS_CHANGED publicado: "
                f"active={active_count}, available={available_count}, on_duty={on_duty_count}"
            )
            
        except Exception as e:
            logger.error(
                f"❌ Error publicando evento DASHBOARD_ACTIVE_TECHNICIANS_CHANGED: {str(e)}",
                exc_info=True
            )
    
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
                
                # Publicar evento de imagen subida
                try:
                    image_event = EvidenceImageUploadedEvent(
                        evidence_id=evidencia_img_created.id,
                        evidence_image_id=evidencia_imagen_created.id,
                        incident_id=created_incidente.id,
                        file_url=imagen_url,
                        file_name="incident_image.jpg",
                        mime_type="image/jpeg",
                        file_size=0,
                        uploaded_by=client_id
                    )
                    await EventPublisher.publish(self.session, image_event)
                except Exception as e:
                    logger.error(f"Error publicando evento de imagen: {str(e)}", exc_info=True)
        
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
                
                # Publicar evento de audio subido
                try:
                    audio_event = EvidenceAudioUploadedEvent(
                        evidence_id=evidencia_audio_created.id,
                        evidence_audio_id=evidencia_audio_item_created.id,
                        incident_id=created_incidente.id,
                        file_url=audio_url,
                        file_name="incident_audio.mp3",
                        mime_type="audio/mpeg",
                        file_size=0,
                        duration_seconds=None,
                        uploaded_by=client_id
                    )
                    await EventPublisher.publish(self.session, audio_event)
                except Exception as e:
                    logger.error(f"Error publicando evento de audio: {str(e)}", exc_info=True)
        
        # Publicar evento genérico de evidencia de texto
        try:
            text_evidence_event = EvidenceUploadedEvent(
                evidence_id=evidencia_texto_created.id,
                incident_id=created_incidente.id,
                evidence_type="TEXT",
                uploaded_by=client_id,
                uploaded_by_role="client",
                file_url=None,
                file_name=None,
                file_size=None,
                description=request.descripcion
            )
            await EventPublisher.publish(self.session, text_evidence_event)
        except Exception as e:
            logger.error(f"Error publicando evento de evidencia de texto: {str(e)}", exc_info=True)
        
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
                    # Wait for AI processing to complete with timeout
                    from ...core.database import get_session_factory
                    from ...core.config import get_settings
                    session_factory = get_session_factory()
                    settings = get_settings()
                    
                    check_interval = 2  # Revisar cada 2 segundos
                    elapsed_seconds = 0
                    max_wait_seconds = settings.ai_assignment_wait_timeout_seconds  # ✅ TIMEOUT MÁXIMO
                    
                    logger.info(
                        f"⏳ Waiting for AI analysis to complete for incident {created_incidente.id} "
                        f"(max wait: {max_wait_seconds}s)..."
                    )
                    
                    # Esperar hasta el timeout máximo
                    while elapsed_seconds < max_wait_seconds:
                        await asyncio.sleep(check_interval)
                        elapsed_seconds += check_interval
                        
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
                                    f"✅ AI analysis complete for incident {created_incidente.id} "
                                    f"(prioridad={incident.prioridad_ia}, categoria={incident.categoria_ia}) "
                                    f"after {elapsed_seconds} seconds"
                                )
                                
                                # Note: AI analysis completion event will be published by the AI service
                                # when it completes the analysis
                                
                                break
                            
                            # Log de progreso cada 30 segundos
                            if elapsed_seconds % 30 == 0:
                                logger.info(
                                    f"⏳ Still waiting for AI analysis for incident {created_incidente.id} "
                                    f"({elapsed_seconds}/{max_wait_seconds} seconds elapsed)..."
                                )
                    
                    # ✅ TIMEOUT: Si llegamos aquí sin completar, proceder sin IA
                    if elapsed_seconds >= max_wait_seconds:
                        logger.warning(
                            f"⚠️ AI analysis TIMEOUT for incident {created_incidente.id} "
                            f"after {max_wait_seconds} seconds. Proceeding with assignment without AI priority."
                        )
                        # Continuar con asignación usando prioridad por defecto
                    
                    # Now assign with AI-determined priority (or default if timeout)
                    async with session_factory() as bg_session:
                        assignment_service = IntelligentAssignmentService(bg_session)
                        result = await assignment_service.assign_incident_automatically(
                            incident_id=created_incidente.id,
                            force_ai_analysis=False  # AI already ran (or timed out)
                        )
                        
                        if result.success:
                            logger.info(
                                f"✅ Automatic assignment successful for new incident {created_incidente.id}: "
                                f"workshop={result.assigned_workshop.workshop_name}, "
                                f"technician={result.assigned_technician.first_name} {result.assigned_technician.last_name}"
                            )
                        else:
                            logger.warning(
                                f"⚠️ Automatic assignment failed for new incident {created_incidente.id}: "
                                f"{result.error_message}"
                            )
                            
                except Exception as e:
                    logger.error(f"❌ Background auto-assignment failed for incident {created_incidente.id}: {str(e)}", exc_info=True)
            
            # Schedule the background task using asyncio.create_task
            asyncio.create_task(auto_assign_after_ai())
            logger.info(f"Scheduled auto-assignment task for incident {created_incidente.id}")
            
        except Exception as exc:
            logger.warning(
                "Failed to schedule incident AI processing and auto-assignment",
                incidente_id=created_incidente.id,
                error=str(exc),
            )
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ PUBLICAR EVENTO DE INCIDENTE CREADO AL OUTBOX
        # ═══════════════════════════════════════════════════════════════════════
        # El OutboxProcessor se encargará de entregar el evento a los destinatarios
        # apropiados (administradores en este caso)
        # ═══════════════════════════════════════════════════════════════════════
        
        try:
            # Crear evento de incidente creado
            incident_event = IncidentCreatedEvent(
                incident_id=created_incidente.id,
                client_id=client_id,
                location={
                    "latitude": float(request.latitude),
                    "longitude": float(request.longitude),
                    "address": request.direccion_referencia
                },
                description=request.descripcion,
                photos=[],  # Las imágenes se agregan después si existen
                vehicle_id=request.vehiculo_id
            )
            
            # Publicar al outbox (se entregará de forma confiable)
            await EventPublisher.publish(self.session, incident_event)
            await self.session.commit()
            
            logger.info(
                f"✅ Evento INCIDENT_CREATED publicado al outbox para incidente {created_incidente.id}",
                incidente_id=created_incidente.id,
                client_id=client_id
            )
            
        except Exception as e:
            # No fallar la creación si la publicación del evento falla
            logger.error(
                f"❌ Error publicando evento INCIDENT_CREATED para incidente {created_incidente.id}: {str(e)}",
                exc_info=True
            )
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ PUBLICAR EVENTO DE CAMBIO EN CONTADOR DE INCIDENTES (DASHBOARD)
        # ═══════════════════════════════════════════════════════════════════════
        # Nuevo incidente creado en estado "pendiente" → incrementar contador
        await self._publish_incident_count_changed(status="pendiente", delta=+1)
        await self.session.commit()
        # ═══════════════════════════════════════════════════════════════════════
        
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
        
        # ✅ VALIDAR TRANSICIÓN DE ESTADO CON STATE MACHINE
        from ...core import IncidentStateMachine, ValidationException
        
        # El taller acepta el incidente: transición a "aceptado"
        target_state = "aceptado"
        
        is_valid, error_message = IncidentStateMachine.can_transition(
            from_state=incidente.estado_actual,
            to_state=target_state,
            user_role="workshop",
            incident=incidente
        )
        
        if not is_valid:
            logger.error(
                f"State Machine validation failed: Workshop {taller_id} cannot accept "
                f"incident {incidente_id} in state '{incidente.estado_actual}': {error_message}"
            )
            raise ValidationException(error_message)
        
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
        
        # Guardar el estado anterior para los eventos de dashboard
        estado_anterior = "pendiente"  # Siempre viene de pendiente cuando se acepta
        nuevo_estado = incidente.estado_actual
        
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
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ PUBLICAR EVENTO DE ASIGNACIÓN ACEPTADA AL OUTBOX
        # ═══════════════════════════════════════════════════════════════════════
        
        try:
            # Obtener el técnico ANTES de crear el evento
            technician = None
            technician_name = "Unknown"
            
            if suggested_technician_id:
                from ...models.technician import Technician
                technician = await self.session.get(Technician, suggested_technician_id)
                if technician:
                    technician_name = f"{technician.first_name} {technician.last_name}"
                    logger.info(f"✅ Technician data loaded: {technician_name}")
                else:
                    logger.warning(f"⚠️ Technician {suggested_technician_id} not found")
            
            # Crear evento de asignación aceptada con datos correctos
            assignment_event = IncidentAssignmentAcceptedEvent(
                incident_id=incidente_id,
                workshop_id=taller_id,
                workshop_name=incidente.workshop.workshop_name if incidente.workshop else "Unknown",
                technician_id=suggested_technician_id if suggested_technician_id else 0,
                technician_name=technician_name,
                eta=None  # Could be calculated based on distance
            )
            
            # Publicar al outbox (se entregará de forma confiable)
            await EventPublisher.publish(self.session, assignment_event)
            await self.session.commit()
            
            logger.info(
                f"✅ Evento ASSIGNMENT_ACCEPTED publicado al outbox para incidente {incidente_id}",
                incidente_id=incidente_id,
                taller_id=taller_id
            )
            
        except Exception as e:
            # No fallar la aceptación si la publicación del evento falla
            logger.error(
                f"❌ Error publicando evento ASSIGNMENT_ACCEPTED para incidente {incidente_id}: {str(e)}",
                exc_info=True
            )
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ Las notificaciones push se envían automáticamente por el OutboxProcessor
        # No se necesitan llamadas directas a push_service.send_to_user()
        # ═══════════════════════════════════════════════════════════════════════
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ PUBLICAR EVENTOS DE DASHBOARD
        # ═══════════════════════════════════════════════════════════════════════
        # Decrementar contador de "pendiente" (estado anterior)
        await self._publish_incident_count_changed(status=estado_anterior, delta=-1)
        # Incrementar contador del nuevo estado
        await self._publish_incident_count_changed(status=nuevo_estado, delta=+1)
        
        # Si se asignó un técnico, publicar cambio en técnicos activos
        if suggested_technician_id:
            await self._publish_active_technicians_changed()
        
        await self.session.commit()
        # ═══════════════════════════════════════════════════════════════════════
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ EMISIÓN DIRIGIDA DE EVENTO WEBSOCKET (solo a participantes del incidente)
        # Corrige el bug de emit_to_all que enviaba datos a todos los usuarios.
        # ═══════════════════════════════════════════════════════════════════════
        try:
            from ...core.websocket_events import emit_to_users, EventTypes
            
            # Preparar payload del evento
            event_data = {
                "incident_id": incidente_id,
                "workshop_id": taller_id,
                "workshop_name": incidente.workshop.workshop_name if incidente.workshop else "Unknown",
                "technician_id": suggested_technician_id if suggested_technician_id else None,
                "technician_name": technician_name if suggested_technician_id else None,
                "old_status": estado_anterior,
                "new_status": nuevo_estado,
                "estado_actual": nuevo_estado,
                "timestamp": datetime.now(UTC).isoformat()
            }
            
            # Emitir solo a los participantes del incidente: cliente y taller
            participants = [p for p in [incidente.client_id, taller_id] if p is not None]
            if participants:
                await emit_to_users(
                    user_ids=participants,
                    event_type=EventTypes.ASSIGNMENT_ACCEPTED,
                    data=event_data
                )
            
            logger.info(
                f"✅ WebSocket event ASSIGNMENT_ACCEPTED emitted to participants {participants} "
                f"for incident {incidente_id} → workshop {taller_id} (estado: {nuevo_estado})"
            )
            
        except Exception as ws_err:
            # ⚠️ NO fallar la operación si WebSocket falla
            logger.error(
                f"❌ Error emitting WebSocket event ASSIGNMENT_ACCEPTED: {str(ws_err)}", 
                exc_info=True
            )
        
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
        
        # ✅ VALIDAR TRANSICIÓN DE ESTADO CON STATE MACHINE
        from ...core import IncidentStateMachine, ValidationException
        
        # El taller rechaza el incidente: transición a "rechazado"
        target_state = "rechazado"
        
        is_valid, error_message = IncidentStateMachine.can_transition(
            from_state=incidente.estado_actual,
            to_state=target_state,
            user_role="workshop",
            incident=incidente
        )
        
        if not is_valid:
            logger.error(
                f"State Machine validation failed: Workshop {taller_id} cannot reject "
                f"incident {incidente_id} in state '{incidente.estado_actual}': {error_message}"
            )
            raise ValidationException(error_message)
        
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
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ PUBLICAR EVENTO DE ASIGNACIÓN RECHAZADA AL OUTBOX
        # ═══════════════════════════════════════════════════════════════════════
        
        try:
            from ...models.workshop import Workshop
            
            # Get workshop name
            workshop = await self.session.get(Workshop, taller_id)
            workshop_name = workshop.workshop_name if workshop else "Unknown"
            
            # Crear evento de asignación rechazada
            rejection_event = IncidentAssignmentRejectedEvent(
                incident_id=incidente_id,
                workshop_id=taller_id,
                workshop_name=workshop_name,
                reason=motivo
            )
            
            # Publicar al outbox (se entregará de forma confiable)
            await EventPublisher.publish(self.session, rejection_event)
            await self.session.commit()
            
            logger.info(
                f"✅ Evento ASSIGNMENT_REJECTED publicado al outbox para incidente {incidente_id}",
                incidente_id=incidente_id,
                taller_id=taller_id
            )
            
            # ✅ EMISIÓN DIRIGIDA DE EVENTO WEBSOCKET (solo al cliente del incidente)
            # El taller ya sabe que rechazó; el cliente necesita saber que se busca otro taller.
            from ...core.websocket_events import emit_to_users, EventTypes
            
            # Preparar payload del evento
            event_data = {
                "incident_id": incidente_id,
                "workshop_id": taller_id,
                "workshop_name": workshop_name,
                "rejection_reason": motivo,
                "old_status": incidente.estado_actual,
                "new_status": "rechazado",
                "estado_actual": "rechazado",
                "timestamp": datetime.now(UTC).isoformat()
            }
            
            # Emitir solo al cliente (el taller que rechazó ya lo sabe)
            if incidente.client_id:
                await emit_to_users(
                    user_ids=[incidente.client_id],
                    event_type=EventTypes.ASSIGNMENT_REJECTED,
                    data=event_data
                )
            
            logger.info(
                f"✅ WebSocket event ASSIGNMENT_REJECTED emitted to client {incidente.client_id} "
                f"for incident {incidente_id} → workshop {taller_id}"
            )
            
        except Exception as e:
            # No fallar el rechazo si la publicación del evento falla
            logger.error(
                f"❌ Error publicando evento ASSIGNMENT_REJECTED para incidente {incidente_id}: {str(e)}",
                exc_info=True
            )
        
        # ═══════════════════════════════════════════════════════════════════════
        
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
        
        # Guardar estado anterior para eventos de dashboard
        estado_anterior = incidente.estado_actual
        technician_freed = bool(incidente.tecnico_id)  # Track if we'll free a technician
        
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
        
        # ✅ Publicar evento de reasignación iniciada
        try:
            from ...shared.schemas.events.incident import IncidentReassignmentStartedEvent
            
            reassignment_event = IncidentReassignmentStartedEvent(
                incident_id=incidente_id,
                previous_workshop_id=incidente.taller_id,
                reason="Caso ambiguo - Requiere revisión adicional",
                message="Buscando un nuevo taller disponible"
            )
            
            await EventPublisher.publish(self.session, reassignment_event)
            logger.info(f"✅ Published reassignment_started event for incident {incidente_id}")
        except Exception as e:
            logger.error(f"Failed to publish reassignment event: {str(e)}")
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ PUBLICAR EVENTOS DE DASHBOARD
        # ═══════════════════════════════════════════════════════════════════════
        # Decrementar contador del estado anterior
        await self._publish_incident_count_changed(status=estado_anterior, delta=-1)
        # Incrementar contador de "pendiente" (vuelve a pendiente)
        await self._publish_incident_count_changed(status="pendiente", delta=+1)
        
        # Si se liberó un técnico, publicar cambio en técnicos activos
        if technician_freed:
            await self._publish_active_technicians_changed()
        
        await self.session.commit()
        # ═══════════════════════════════════════════════════════════════════════
        
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
        
        # Guardar estado anterior para eventos de dashboard
        estado_anterior = incidente.estado_actual
        technician_freed = False
        
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
                technician_freed = True
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
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ PUBLICAR EVENTO DE CAMBIO DE ESTADO AL OUTBOX
        # ═══════════════════════════════════════════════════════════════════════
        
        try:
            # Determinar el estado anterior (necesitamos guardarlo antes del commit)
            # Por ahora usamos el estado actual ya que ya se actualizó
            old_status = "unknown"  # Idealmente esto debería guardarse antes del update
            
            # Crear evento de cambio de estado
            status_event = IncidentStatusChangedEvent(
                incident_id=incidente_id,
                old_status=old_status,
                new_status=nuevo_estado,
                changed_by=user_id,
                changed_by_role=user_type,
                reason=None
            )
            
            # Publicar al outbox (se entregará de forma confiable)
            await EventPublisher.publish(self.session, status_event)
            await self.session.commit()
            
            logger.info(
                f"✅ Evento INCIDENT_STATUS_CHANGED publicado al outbox para incidente {incidente_id} → {nuevo_estado}",
                incidente_id=incidente_id,
                nuevo_estado=nuevo_estado,
                user_id=user_id
            )
            
        except Exception as e:
            # No fallar la operación si la publicación del evento falla
            logger.error(
                f"❌ Error publicando evento INCIDENT_STATUS_CHANGED para incidente {incidente_id}: {str(e)}",
                exc_info=True
            )
        
        # ═══════════════════════════════════════════════════════════════════════
        
        logger.info(
            f"Estado de incidente actualizado a '{nuevo_estado}'",
            incidente_id=incidente_id,
            user_id=user_id,
            user_type=user_type
        )
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ PUBLICAR EVENTOS DE DASHBOARD
        # ═══════════════════════════════════════════════════════════════════════
        # Decrementar contador del estado anterior
        await self._publish_incident_count_changed(status=estado_anterior, delta=-1)
        # Incrementar contador del nuevo estado
        await self._publish_incident_count_changed(status=nuevo_estado, delta=+1)
        
        # Si se liberó un técnico, publicar cambio en técnicos activos
        if technician_freed:
            await self._publish_active_technicians_changed()
        
        await self.session.commit()
        # ═══════════════════════════════════════════════════════════════════════
        
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
        
        # ✅ VALIDAR TRANSICIÓN DE ESTADO CON STATE MACHINE
        from ...core import IncidentStateMachine, ValidationException
        
        # Cancelar incidente: transición a "cancelado"
        target_state = "cancelado"
        
        is_valid, error_message = IncidentStateMachine.can_transition(
            from_state=incidente.estado_actual,
            to_state=target_state,
            user_role=user_type,
            incident=incidente
        )
        
        if not is_valid:
            logger.error(
                f"State Machine validation failed: User {user_id} ({user_type}) cannot cancel "
                f"incident {incidente_id} in state '{incidente.estado_actual}': {error_message}"
            )
            raise ValidationException(error_message)
        
        # Actualizar estado a cancelado
        estado_anterior = incidente.estado_actual
        incidente.estado_actual = "cancelado"
        incidente.updated_at = datetime.now(UTC)
        
        technician_freed = False
        
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
                technician_freed = True
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
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ EMIT WEBSOCKET EVENT FOR REAL-TIME UPDATE (CANCELLATION)
        # ═══════════════════════════════════════════════════════════════════════
        try:
            from ...core.websocket_events import emit_to_all, EventTypes
            
            await emit_to_all(
                event_type=EventTypes.INCIDENT_CANCELLED,
                data={
                    "incident_id": incidente_id,
                    "old_status": estado_anterior,
                    "new_status": "cancelado",
                    "estado_actual": "cancelado",
                    "cancelled_by": user_id,
                    "cancelled_by_role": user_type,
                    "cancellation_reason": motivo or "Sin motivo especificado",
                    "timestamp": datetime.now(UTC).isoformat()
                }
            )
            
            logger.info(
                f"✅ WebSocket event emitted: incident {incidente_id} cancelled {estado_anterior} → cancelado"
            )
            
        except Exception as ws_err:
            # ⚠️ NO fallar la operación si WebSocket falla
            logger.error(
                f"❌ Failed to emit WebSocket event for incident {incidente_id}: {str(ws_err)}"
            )
        # ═══════════════════════════════════════════════════════════════════════
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ PUBLICAR EVENTO DE CANCELACIÓN AL OUTBOX
        # ═══════════════════════════════════════════════════════════════════════
        
        try:
            # Crear evento de cancelación
            cancellation_event = IncidentCancelledEvent(
                incident_id=incidente_id,
                cancelled_by=user_id,
                cancelled_by_role=user_type,
                reason=motivo or "Sin motivo especificado"
            )
            
            # Publicar al outbox (se entregará de forma confiable)
            await EventPublisher.publish(self.session, cancellation_event)
            await self.session.commit()
            
            logger.info(
                f"✅ Evento INCIDENT_CANCELLED publicado al outbox para incidente {incidente_id}",
                incidente_id=incidente_id,
                cancelled_by=user_id
            )
            
        except Exception as e:
            # No fallar la cancelación si la publicación del evento falla
            logger.error(
                f"❌ Error publicando evento INCIDENT_CANCELLED para incidente {incidente_id}: {str(e)}",
                exc_info=True
            )
        
        # ═══════════════════════════════════════════════════════════════════════
        
        logger.info(
            f"Incidente cancelado",
            incidente_id=incidente_id,
            user_id=user_id,
            user_type=user_type,
            motivo=motivo or "Sin motivo especificado"
        )
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ PUBLICAR EVENTOS DE DASHBOARD
        # ═══════════════════════════════════════════════════════════════════════
        # Decrementar contador del estado anterior
        await self._publish_incident_count_changed(status=estado_anterior, delta=-1)
        # Incrementar contador de "cancelado"
        await self._publish_incident_count_changed(status="cancelado", delta=+1)
        
        # Si se liberó un técnico, publicar cambio en técnicos activos
        if technician_freed:
            await self._publish_active_technicians_changed()
        
        await self.session.commit()
        # ═══════════════════════════════════════════════════════════════════════
        
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

        # Note: Evidence deletion events can be added later if needed
        # For now, we focus on the main incident lifecycle events

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

    async def upload_photos(
        self,
        incidente_id: int,
        photo_urls: List[str],
        user_id: int,
        user_type: str
    ) -> Incidente:
        """
        Subir fotos adicionales a un incidente existente.
        
        Args:
            incidente_id: ID del incidente
            photo_urls: Lista de URLs de las fotos subidas
            user_id: ID del usuario que sube las fotos
            user_type: Tipo de usuario (client, technician, workshop, admin)
            
        Returns:
            Incidente actualizado
            
        Raises:
            NotFoundException: Si el incidente no existe
            ForbiddenException: Si el usuario no tiene permiso
        """
        # Obtener el incidente
        incidente = await self.repository.find_by_id(incidente_id)
        
        if not incidente:
            raise NotFoundException(f"Incidente con ID {incidente_id} no encontrado")
        
        # Verificar permisos
        if user_type == "client" and incidente.client_id != user_id:
            raise ForbiddenException("No tienes permiso para subir fotos a este incidente")
        elif user_type == "technician":
            # Verificar que el técnico esté asignado al incidente
            if incidente.tecnico_id != user_id:
                raise ForbiddenException("No tienes permiso para subir fotos a este incidente")
        elif user_type == "workshop":
            # Verificar que el taller esté asignado al incidente
            if incidente.taller_id != user_id:
                raise ForbiddenException("No tienes permiso para subir fotos a este incidente")
        elif user_type not in ["admin"]:
            raise ForbiddenException("No tienes permiso para subir fotos")
        
        # Crear evidencia de imágenes
        evidencia_imagenes = Evidencia(
            incidente_id=incidente_id,
            uploaded_by_user_id=user_id,
            tipo="IMAGE",
            descripcion=f"Fotos adicionales subidas por {user_type}",
        )
        evidencia_img_created = await self.repository.create_evidencia(evidencia_imagenes)
        
        # Crear registros de imágenes individuales
        for photo_url in photo_urls:
            evidencia_imagen = EvidenciaImagen(
                evidencia_id=evidencia_img_created.id,
                file_url=photo_url,
                file_name="additional_photo.jpg",
                file_type="image",
                mime_type="image/jpeg",
                size=0,
                uploaded_by=user_id,
            )
            await self.repository.create_evidencia_imagen(evidencia_imagen)
        
        await self.session.commit()
        await self.session.refresh(incidente)
        
        logger.info(
            f"Fotos subidas al incidente {incidente_id}",
            incidente_id=incidente_id,
            user_id=user_id,
            photo_count=len(photo_urls)
        )
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ PUBLICAR EVENTO DE FOTOS SUBIDAS AL OUTBOX
        # ═══════════════════════════════════════════════════════════════════════
        
        try:
            from ...shared.schemas.events.incident import IncidentPhotosUploadedEvent
            
            photos_event = IncidentPhotosUploadedEvent(
                incident_id=incidente_id,
                photo_urls=photo_urls,
                uploaded_by=user_id,
                uploaded_by_role=user_type
            )
            
            await EventPublisher.publish(self.session, photos_event)
            await self.session.commit()
            
            logger.info(
                f"✅ Evento INCIDENT_PHOTOS_UPLOADED publicado al outbox para incidente {incidente_id}",
                incidente_id=incidente_id,
                photo_count=len(photo_urls)
            )
            
        except Exception as e:
            logger.error(
                f"❌ Error publicando evento INCIDENT_PHOTOS_UPLOADED para incidente {incidente_id}: {str(e)}",
                exc_info=True
            )
        
        # ═══════════════════════════════════════════════════════════════════════
        
        return incidente


    async def start_work(
        self,
        incidente_id: int,
        technician_id: int
    ) -> Incidente:
        """
        Marcar que el técnico ha comenzado a trabajar en el incidente.
        
        Este método:
        1. Valida la transición de estado (EN_CAMINO/ACEPTADO → EN_PROCESO)
        2. Actualiza el estado del incidente
        3. Publica IncidentWorkStartedEvent
        
        Args:
            incidente_id: ID del incidente
            technician_id: ID del técnico
            
        Returns:
            Incidente actualizado
            
        Raises:
            NotFoundException: Si el incidente no existe
            ValidationException: Si la transición de estado es inválida
        """
        # Obtener el incidente
        incidente = await self.repository.find_by_id(incidente_id)
        
        if not incidente:
            raise NotFoundException(f"Incidente con ID {incidente_id} no encontrado")
        
        # Verificar que el técnico está asignado al incidente
        if incidente.tecnico_id != technician_id:
            raise ForbiddenException(
                f"El técnico {technician_id} no está asignado a este incidente"
            )
        
        # ✅ VALIDAR TRANSICIÓN DE ESTADO CON STATE MACHINE
        from ...core import IncidentStateMachine, ValidationException
        
        target_state = "en_proceso"
        
        is_valid, error_message = IncidentStateMachine.can_transition(
            from_state=incidente.estado_actual,
            to_state=target_state,
            user_role="technician",
            incident=incidente
        )
        
        if not is_valid:
            logger.error(
                f"State Machine validation failed: Technician {technician_id} cannot start work on "
                f"incident {incidente_id} in state '{incidente.estado_actual}': {error_message}"
            )
            raise ValidationException(error_message)
        
        # Guardar estado anterior para eventos de dashboard
        estado_anterior = incidente.estado_actual
        
        # Actualizar estado del incidente
        incidente.estado_actual = "en_proceso"
        incidente.updated_at = datetime.now(UTC)
        
        await self.session.commit()
        await self.session.refresh(incidente)
        
        logger.info(
            f"✅ Trabajo iniciado en incidente {incidente_id} por técnico {technician_id}"
        )
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ EMIT WEBSOCKET EVENT FOR REAL-TIME UPDATE
        # ═══════════════════════════════════════════════════════════════════════
        await self._emit_status_change_event(
            incident_id=incidente_id,
            old_status=estado_anterior,
            new_status="en_proceso",
            changed_by=technician_id,
            changed_by_role="technician"
        )
        # ═══════════════════════════════════════════════════════════════════════
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ PUBLICAR EVENTO DE TRABAJO INICIADO
        # ═══════════════════════════════════════════════════════════════════════
        try:
            from ...shared.schemas.events.incident import IncidentWorkStartedEvent
            from ...models.technician import Technician
            
            # Get technician info
            technician = await self.session.get(Technician, technician_id)
            technician_name = f"{technician.first_name} {technician.last_name}" if technician else "Unknown"
            
            work_started_event = IncidentWorkStartedEvent(
                incident_id=incidente_id,
                technician_id=technician_id,
                technician_name=technician_name,
                start_time=datetime.now(UTC)
            )
            
            await EventPublisher.publish(self.session, work_started_event)
            await self.session.commit()
            
            logger.info(
                f"✅ Evento WORK_STARTED publicado para incidente {incidente_id}",
                technician_id=technician_id
            )
            
        except Exception as e:
            logger.error(
                f"❌ Error publicando evento WORK_STARTED: {str(e)}",
                exc_info=True
            )
        # ═══════════════════════════════════════════════════════════════════════
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ PUBLICAR EVENTOS DE DASHBOARD
        # ═══════════════════════════════════════════════════════════════════════
        # Decrementar contador del estado anterior
        await self._publish_incident_count_changed(status=estado_anterior, delta=-1)
        # Incrementar contador de "en_proceso"
        await self._publish_incident_count_changed(status="en_proceso", delta=+1)
        
        await self.session.commit()
        # ═══════════════════════════════════════════════════════════════════════
        
        return incidente

    async def complete_work(
        self,
        incidente_id: int,
        technician_id: int,
        summary: Optional[str] = None
    ) -> Incidente:
        """
        Marcar que el técnico ha completado el trabajo en el incidente.
        
        Este método:
        1. Valida la transición de estado (EN_PROCESO → COMPLETADO)
        2. Actualiza el estado del incidente
        3. Libera al técnico (marca como disponible)
        4. Finaliza la sesión de tracking
        5. Publica IncidentWorkCompletedEvent
        
        Args:
            incidente_id: ID del incidente
            technician_id: ID del técnico
            summary: Resumen opcional del trabajo realizado
            
        Returns:
            Incidente actualizado
            
        Raises:
            NotFoundException: Si el incidente no existe
            ValidationException: Si la transición de estado es inválida
        """
        # Obtener el incidente
        incidente = await self.repository.find_by_id(incidente_id)
        
        if not incidente:
            raise NotFoundException(f"Incidente con ID {incidente_id} no encontrado")
        
        # Verificar que el técnico está asignado al incidente
        if incidente.tecnico_id != technician_id:
            raise ForbiddenException(
                f"El técnico {technician_id} no está asignado a este incidente"
            )
        
        # ✅ VALIDAR TRANSICIÓN DE ESTADO CON STATE MACHINE
        from ...core import IncidentStateMachine, ValidationException
        
        target_state = "completado"
        
        is_valid, error_message = IncidentStateMachine.can_transition(
            from_state=incidente.estado_actual,
            to_state=target_state,
            user_role="technician",
            incident=incidente
        )
        
        if not is_valid:
            logger.error(
                f"State Machine validation failed: Technician {technician_id} cannot complete work on "
                f"incident {incidente_id} in state '{incidente.estado_actual}': {error_message}"
            )
            raise ValidationException(error_message)
        
        # Calcular duración del trabajo
        duration_minutes = None
        if incidente.assigned_at:
            duration_seconds = (datetime.now(UTC) - incidente.assigned_at).total_seconds()
            duration_minutes = int(duration_seconds / 60)
        
        # Guardar estado anterior para eventos de dashboard
        estado_anterior = incidente.estado_actual
        
        # Actualizar estado del incidente
        incidente.estado_actual = "completado"
        incidente.updated_at = datetime.now(UTC)
        
        # Liberar al técnico
        from ...models.technician import Technician
        technician = await self.session.get(Technician, technician_id)
        if technician:
            technician.is_on_duty = False
            technician.is_available = True
            technician.updated_at = datetime.now(UTC)
            logger.info(
                f"Técnico {technician_id} liberado (is_on_duty=False, is_available=True)"
            )
        
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
        
        await self.session.commit()
        await self.session.refresh(incidente)
        
        logger.info(
            f"✅ Trabajo completado en incidente {incidente_id} por técnico {technician_id}"
        )
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ EMIT WEBSOCKET EVENT FOR REAL-TIME UPDATE
        # ═══════════════════════════════════════════════════════════════════════
        await self._emit_status_change_event(
            incident_id=incidente_id,
            old_status=estado_anterior,
            new_status="completado",
            changed_by=technician_id,
            changed_by_role="technician"
        )
        # ═══════════════════════════════════════════════════════════════════════
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ PUBLICAR EVENTO DE TRABAJO COMPLETADO
        # ═══════════════════════════════════════════════════════════════════════
        try:
            from ...shared.schemas.events.incident import IncidentWorkCompletedEvent
            
            technician_name = f"{technician.first_name} {technician.last_name}" if technician else "Unknown"
            
            work_completed_event = IncidentWorkCompletedEvent(
                incident_id=incidente_id,
                technician_id=technician_id,
                technician_name=technician_name,
                completion_time=datetime.now(UTC),
                summary=summary,
                duration_minutes=duration_minutes
            )
            
            await EventPublisher.publish(self.session, work_completed_event)
            await self.session.commit()
            
            logger.info(
                f"✅ Evento WORK_COMPLETED publicado para incidente {incidente_id}",
                technician_id=technician_id,
                duration_minutes=duration_minutes
            )
            
        except Exception as e:
            logger.error(
                f"❌ Error publicando evento WORK_COMPLETED: {str(e)}",
                exc_info=True
            )
        # ═══════════════════════════════════════════════════════════════════════
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ PUBLICAR EVENTOS DE DASHBOARD
        # ═══════════════════════════════════════════════════════════════════════
        # Decrementar contador del estado anterior
        await self._publish_incident_count_changed(status=estado_anterior, delta=-1)
        # Incrementar contador de "completado"
        await self._publish_incident_count_changed(status="completado", delta=+1)
        
        # Publicar cambio en técnicos activos (técnico liberado)
        await self._publish_active_technicians_changed()
        
        await self.session.commit()
        # ═══════════════════════════════════════════════════════════════════════
        
        return incidente

    # ═══════════════════════════════════════════════════════════════════════
    # ✅ HELPER METHOD FOR WEBSOCKET EVENT EMISSION
    # ═══════════════════════════════════════════════════════════════════════
    
    async def _emit_status_change_event(
        self,
        incident_id: int,
        old_status: str,
        new_status: str,
        changed_by: Optional[int] = None,
        changed_by_role: Optional[str] = None
    ) -> None:
        """
        Helper method to emit WebSocket event for incident status changes.
        
        Args:
            incident_id: ID of the incident
            old_status: Previous status
            new_status: New status
            changed_by: User ID who made the change (optional)
            changed_by_role: Role of the user who made the change (optional)
        """
        try:
            from ...core.websocket_events import emit_to_all, EventTypes
            from datetime import datetime, UTC
            
            await emit_to_all(
                event_type=EventTypes.INCIDENT_STATUS_CHANGED,
                data={
                    "incident_id": incident_id,
                    "old_status": old_status,
                    "new_status": new_status,
                    "estado_actual": new_status,
                    "changed_by": changed_by,
                    "changed_by_role": changed_by_role,
                    "timestamp": datetime.now(UTC).isoformat()
                }
            )
            
            logger.info(
                f"✅ WebSocket event emitted: incident {incident_id} status changed {old_status} → {new_status}"
            )
            
        except Exception as ws_err:
            # ⚠️ NO fallar la operación si WebSocket falla
            logger.error(
                f"❌ Failed to emit WebSocket event for incident {incident_id}: {str(ws_err)}"
            )
