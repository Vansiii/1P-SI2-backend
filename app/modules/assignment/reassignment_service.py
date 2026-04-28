"""
Reassignment Service - Automatic incident reassignment with dynamic recalculation.

This service handles:
- Automatic reassignment after workshop rejection
- Timeout monitoring and reassignment
- Dynamic candidate recalculation (fresh data)
- Admin notification when no workshops available
"""
import json
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update

from ...core.logging import get_logger
from ...core.config import get_settings
from ...models.incidente import Incidente
from ...models.assignment_attempt import AssignmentAttempt
from ...models.administrator import Administrator
from ...models.notification import Notification
from .services import IntelligentAssignmentService, AssignmentResult
from ..push_notifications.services import PushNotificationService, PushNotificationData

logger = get_logger(__name__)
settings = get_settings()


class ReassignmentService:
    """
    Service for automatic incident reassignment with dynamic recalculation.
    
    Key Features:
    - Monitors timeouts of pending assignments
    - Reassigns automatically after rejection or timeout
    - RECALCULATES candidates in real-time (fresh data)
    - Excludes workshops that already rejected/timeout
    - Escalates to admin when no workshops available
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.assignment_service = IntelligentAssignmentService(session)
        self.push_service = PushNotificationService(session)

    async def handle_rejection(
        self,
        incident_id: int,
        workshop_id: int,
        rejection_reason: str
    ) -> AssignmentResult:
        """
        Handle explicit rejection and reassign with recalculation.
        
        Flow:
        1. Mark current attempt as 'rejected'
        2. Notify client about rejection
        3. Get list of excluded workshops (rejected + timeout)
        4. RECALCULATE available candidates (fresh data)
        5. Assign to best available candidate NOW
        6. If no candidates, notify admin and client
        
        Args:
            incident_id: ID of the incident
            workshop_id: ID of the workshop that rejected
            rejection_reason: Reason for rejection
            
        Returns:
            AssignmentResult with reassignment details
        """
        try:
            logger.info(
                f"🔄 Handling rejection for incident {incident_id} from workshop {workshop_id}. "
                f"Reason: {rejection_reason}"
            )
            
            # 1. Mark as rejected (already done in router, but ensure it's set)
            await self.assignment_service._update_assignment_attempt_status(
                incident_id=incident_id,
                workshop_id=workshop_id,
                status="rejected",
                response_message=rejection_reason
            )
            
            # 2. Notify client about rejection and reassignment
            incident = await self._load_incident(incident_id)
            if incident:
                try:
                    from ...shared.schemas.events.incident import IncidentReassignmentStartedEvent
                    from ...core.event_publisher import EventPublisher
                    
                    reassignment_event = IncidentReassignmentStartedEvent(
                        incident_id=incident_id,
                        previous_workshop_id=workshop_id,
                        reason=f"Rechazo del taller: {rejection_reason}",
                        message="Buscando un nuevo taller disponible"
                    )
                    await EventPublisher.publish(self.session, reassignment_event)
                    logger.info(f"✅ Published reassignment_started event for incident {incident_id}")
                except Exception as e:
                    logger.error(f"Failed to publish reassignment event: {str(e)}")
            
            # 3. Wait a bit before reassigning (configurable delay)
            # This gives time for notifications to be processed
            # In production, this could be handled by a background task
            # For now, we proceed immediately
            
            # 4. Reassign with recalculation
            result = await self.reassign_to_next_candidate(incident_id)
            
            if result.success:
                logger.info(
                    f"✅ Successfully reassigned incident {incident_id} to "
                    f"{result.assigned_workshop.workshop_name if result.assigned_workshop else 'unknown'}"
                )
            else:
                logger.warning(
                    f"⚠️ Failed to reassign incident {incident_id}: {result.error_message}"
                )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error handling rejection: {str(e)}", exc_info=True)
            return AssignmentResult(
                success=False,
                error_message=f"Rejection handling error: {str(e)}"
            )

    async def check_timeouts(self) -> List[int]:
        """
        Check for pending assignments that exceeded timeout.
        Executed by background task every minute.
        
        IMPORTANTE: Solo procesa incidentes que AÚN están pendientes de asignación.
        Si un incidente ya fue aceptado (estado 'en_proceso' o 'asignado'), 
        no debe procesarse para timeout.
        
        Returns:
            List of incident_ids that had timeout
        """
        try:
            now = datetime.utcnow()
            
            # Find pending attempts with expired timeout
            # PERO solo para incidentes que AÚN están pendientes
            result = await self.session.execute(
                select(AssignmentAttempt, Incidente)
                .join(Incidente, AssignmentAttempt.incident_id == Incidente.id)
                .where(
                    and_(
                        AssignmentAttempt.status == 'pending',
                        AssignmentAttempt.timeout_at.isnot(None),
                        AssignmentAttempt.timeout_at <= now,
                        # 🔥 CLAVE: Solo procesar incidentes que AÚN están pendientes
                        Incidente.estado_actual == 'pendiente'
                    )
                )
            )
            
            timed_out_data = list(result.all())
            
            if not timed_out_data:
                return []
            
            logger.info(f"⏰ Found {len(timed_out_data)} timed out assignments for PENDING incidents")
            
            incident_ids = []
            
            for attempt, incident in timed_out_data:
                # Verificar una vez más que el incidente sigue pendiente
                if incident.estado_actual != 'pendiente':
                    logger.info(
                        f"⏰ Skipping timeout for incident {attempt.incident_id} - "
                        f"already in state '{incident.estado_actual}'"
                    )
                    continue
                
                # Mark as timeout
                attempt.status = 'timeout'
                attempt.responded_at = now
                attempt.response_message = "Timeout: No response within time limit"
                incident_ids.append(attempt.incident_id)
                
                logger.warning(
                    f"⏰ Timeout for incident {attempt.incident_id}, "
                    f"workshop {attempt.workshop_id}"
                )
            
            await self.session.commit()
            
            # Emit assignment_timeout WebSocket events (Task 14)
            from ...core.websocket_events import emit_to_admins, emit_to_user, emit_to_users, emit_to_all, EventTypes
            from ...models.workshop import Workshop
            
            for attempt, incident in timed_out_data:
                if incident.estado_actual != 'pendiente':
                    continue
                    
                try:
                    workshop = await self.session.get(Workshop, attempt.workshop_id)
                    workshop_name = workshop.workshop_name if workshop else "Unknown"
                    
                    timeout_payload = {
                        "attempt_id": attempt.id,
                        "incident_id": attempt.incident_id,
                        "workshop_id": attempt.workshop_id,
                        "workshop_name": workshop_name,
                        "response_status": "timeout",
                        "timestamp": now.isoformat()
                    }
                    
                    # Emit to admins
                    await emit_to_admins(
                        event_type=EventTypes.ASSIGNMENT_TIMEOUT,
                        data=timeout_payload
                    )
                    
                    # Emit to the workshop that timed out (so their UI updates)
                    # and to the client so they know what's happening
                    targeted_users = []
                    if workshop:
                        targeted_users.append(workshop.id)
                    if incident.client_id:
                        targeted_users.append(incident.client_id)
                    
                    if targeted_users:
                        await emit_to_users(
                            user_ids=targeted_users,
                            event_type=EventTypes.ASSIGNMENT_TIMEOUT,
                            data=timeout_payload
                        )
                        logger.info(
                            f"WebSocket event '{EventTypes.ASSIGNMENT_TIMEOUT}' emitted to "
                            f"participants {targeted_users} for incident {attempt.incident_id}"
                        )
                except Exception as ws_err:
                    logger.error(
                        f"Failed to emit assignment_timeout WebSocket event: {str(ws_err)}"
                    )
            
            # Return unique incident IDs
            return list(set(incident_ids))
            
        except Exception as e:
            logger.error(f"❌ Error checking timeouts: {str(e)}", exc_info=True)
            return []

    async def reassign_to_next_candidate(
        self,
        incident_id: int
    ) -> AssignmentResult:
        """
        Reassign incident by RECALCULATING candidates in real-time.
        
        Advantages of recalculation:
        - Always up-to-date data
        - Considers technicians that became available
        - Considers location changes
        - Excludes workshops that already rejected/timeout
        
        Flow:
        1. Load incident
        2. Validate incident state
        3. Get excluded workshops (rejected + timeout)
        4. Check max attempts limit
        5. RECALCULATE candidates with fresh data
        6. Assign to best available candidate NOW
        7. If no candidates, notify admin
        
        Args:
            incident_id: ID of the incident to reassign
            
        Returns:
            AssignmentResult with reassignment details
        """
        try:
            # 1. Load incident
            incident = await self._load_incident(incident_id)
            if not incident:
                return AssignmentResult(
                    success=False,
                    error_message=f"Incident {incident_id} not found"
                )
            
            # 2. Validate incident state
            if incident.estado_actual in ["resuelto", "cancelado", "sin_taller_disponible"]:
                logger.warning(
                    f"⚠️ Cannot reassign incident {incident_id} in state '{incident.estado_actual}'"
                )
                return AssignmentResult(
                    success=False,
                    error_message=f"Incident is in final state: {incident.estado_actual}"
                )
            
            # 3. Get excluded workshops
            excluded_workshops = await self.assignment_service._get_excluded_workshops(incident_id)
            
            # 4. Check if we've exceeded max attempts
            attempt_count = len(excluded_workshops)
            max_attempts = settings.assignment_max_attempts
            
            logger.info(
                f"🔄 Reassigning incident {incident_id}. "
                f"Excluded workshops: {len(excluded_workshops)} "
                f"(attempt {attempt_count + 1}/{max_attempts})"
            )
            
            if attempt_count >= max_attempts:
                logger.warning(
                    f"⚠️ Max attempts ({max_attempts}) reached for incident {incident_id}. "
                    f"Notifying administrator."
                )
                await self.notify_admin_no_workshops(incident_id)
                return AssignmentResult(
                    success=False,
                    error_message=f"Max attempts ({max_attempts}) reached. Admin notified."
                )
            
            # 5. RECALCULATE candidates (fresh data)
            candidates = await self.assignment_service._find_and_score_candidates(
                incident=incident,
                exclude_workshops=excluded_workshops
            )
            
            # 6. If no candidates, notify admin
            if not candidates:
                logger.warning(
                    f"⚠️ No workshops available for incident {incident_id} after exclusions. "
                    f"Notifying administrator."
                )
                await self.notify_admin_no_workshops(incident_id)
                return AssignmentResult(
                    success=False,
                    error_message="No workshops available after exclusions. Admin notified."
                )
            
            # 7. Validate best candidate
            best_candidate = candidates[0]
            
            # Additional validation: ensure workshop is still active and available
            if not best_candidate.workshop.is_active or not best_candidate.workshop.is_available:
                logger.warning(
                    f"⚠️ Best candidate workshop {best_candidate.workshop.workshop_name} "
                    f"is no longer active/available. Trying next candidate..."
                )
                # Remove this candidate and try again
                excluded_workshops.append(best_candidate.workshop.id)
                return await self.reassign_to_next_candidate(incident_id)
            
            # Validate technicians are still available
            if not best_candidate.available_technicians:
                logger.warning(
                    f"⚠️ Workshop {best_candidate.workshop.workshop_name} "
                    f"has no available technicians. Trying next candidate..."
                )
                excluded_workshops.append(best_candidate.workshop.id)
                return await self.reassign_to_next_candidate(incident_id)
            
            logger.info(
                f"✅ New candidate found: {best_candidate.workshop.workshop_name} "
                f"(score: {best_candidate.final_score:.3f}, "
                f"distance: {best_candidate.distance_km:.2f} km, "
                f"technicians: {len(best_candidate.available_technicians)})"
            )
            
            # 8. Execute assignment
            success = await self.assignment_service._execute_assignment(incident, best_candidate)
            
            if success:
                # Configure timeout for the new attempt
                timeout_minutes = self._get_timeout_minutes(incident)
                await self.assignment_service._set_assignment_timeout(
                    incident_id=incident_id,
                    workshop_id=best_candidate.workshop.id,
                    timeout_minutes=timeout_minutes
                )
                
                # Emit WebSocket event for incident reassignment
                from ...core.websocket_events import emit_to_incident_room, EventTypes
                
                old_workshop_id = incident.taller_id
                new_workshop_id = best_candidate.workshop.id
                
                reassignment_data = {
                    "incident_id": incident_id,
                    "old_workshop_id": old_workshop_id,
                    "new_workshop_id": new_workshop_id,
                    "new_workshop_name": best_candidate.workshop.workshop_name,
                    "reason": "automatic_reassignment",
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                # Emit to incident room (all participants: client, prev workshop, new workshop)
                await emit_to_incident_room(
                    incident_id=incident_id,
                    event_type=EventTypes.INCIDENT_REASSIGNED,
                    data=reassignment_data
                )
                
                logger.info(
                    f"WebSocket event 'incident_reassigned' emitted to incident room {incident_id} "
                    f"(old_workshop: {old_workshop_id}, new_workshop: {new_workshop_id})"
                )
                
                # Notification is handled by OutboxProcessor via incident_reassigned event
                logger.info(f"✅ Reassignment event will be processed by OutboxProcessor for client {incident.client_id}")
                
                logger.info(
                    f"✅ Successfully reassigned incident {incident_id} to "
                    f"{best_candidate.workshop.workshop_name} "
                    f"(timeout: {timeout_minutes} minutes)"
                )
                
                return AssignmentResult(
                    success=True,
                    assigned_workshop=best_candidate.workshop,
                    assigned_technician=best_candidate.available_technicians[0] if best_candidate.available_technicians else None,
                    strategy_used=best_candidate.assignment_strategy,
                    candidates_evaluated=len(candidates),
                    reasoning=f"Reassigned after recalculation. Score: {best_candidate.final_score:.3f}"
                )
            else:
                logger.error(f"❌ Failed to execute reassignment for incident {incident_id}")
                return AssignmentResult(
                    success=False,
                    error_message="Failed to execute reassignment"
                )
                
        except Exception as e:
            logger.error(f"❌ Error reassigning incident {incident_id}: {str(e)}", exc_info=True)
            return AssignmentResult(
                success=False,
                error_message=f"Reassignment error: {str(e)}"
            )

    async def notify_admin_no_workshops(self, incident_id: int) -> bool:
        """
        Notify all administrators AND the client when no workshops are available.
        Uses event publishing instead of direct push notifications.
        
        Args:
            incident_id: ID of the incident
            
        Returns:
            True if notifications were sent successfully
        """
        try:
            # Get incident details
            incident = await self._load_incident(incident_id)
            if not incident:
                logger.error(f"Cannot notify admin: incident {incident_id} not found")
                return False
            
            # Get all active administrators
            result = await self.session.execute(
                select(Administrator).where(Administrator.is_active == True)
            )
            admins = list(result.scalars().all())
            
            if not admins:
                logger.warning("No active administrators found to notify")
                # Continue to notify client even if no admins
            
            logger.info(f"📧 Notifying {len(admins)} administrators about incident {incident_id}")
            
            # Count assignment attempts
            attempt_count = await self._count_assignment_attempts(incident_id)
            
            # Publish incident.no_workshop_available event (OutboxProcessor will handle notifications)
            try:
                from ...shared.schemas.events.incident import IncidentNoWorkshopAvailableEvent
                from ...core.event_publisher import EventPublisher
                
                no_workshop_event = IncidentNoWorkshopAvailableEvent(
                    incident_id=incident_id,
                    reason=f"No hay talleres disponibles después de {attempt_count} intentos",
                    workshops_contacted=attempt_count,
                    message="No hay talleres disponibles. Puedes esperar o cancelar la solicitud"
                )
                await EventPublisher.publish(self.session, no_workshop_event)
                logger.info(f"✅ Published no_workshop_available event for incident {incident_id}")
            except Exception as e:
                logger.error(f"Failed to publish no_workshop_available event: {str(e)}")
            
            # Notifications are handled by OutboxProcessor via status_changed event
            logger.info(f"✅ Status change event will be processed by OutboxProcessor for {len(admins)} admins")
            
            # Create notification in database for each admin (user_id cannot be null)
            for admin in admins:
                admin_notification = Notification(
                    user_id=admin.id,
                    type="incident_no_workshop",
                    title="Incidente sin taller disponible",
                    message=f"Incidente #{incident_id} requiere intervención manual después de {attempt_count} intentos",
                    data_json=json.dumps({
                        "incident_id": incident_id,
                        "attempts": attempt_count,
                        "priority": incident.prioridad_ia,
                        "category": incident.categoria_ia
                    }),
                    is_read=False
                )
                self.session.add(admin_notification)
            
            # Create notification in database for client
            client_notification = Notification(
                user_id=incident.client_id,
                type="incident_no_workshop_client",
                title="No hay talleres disponibles",
                message=f"Por el momento no hay talleres disponibles para atender tu solicitud #{incident_id}. Puedes esperar a que se libere un taller o cancelar la solicitud si lo prefieres.",
                data_json=json.dumps({
                    "incident_id": incident_id,
                    "priority": incident.prioridad_ia,
                    "category": incident.categoria_ia,
                    "can_cancel": True,
                    "action": "view_incident"
                }),
                is_read=False
            )
            self.session.add(client_notification)
            
            # Update incident status
            await self.session.execute(
                update(Incidente)
                .where(Incidente.id == incident_id)
                .values(estado_actual="sin_taller_disponible")
            )
            
            await self.session.commit()
            
            # ✅ Emit WebSocket event for status change to all users
            from ...core.websocket_events import emit_to_all, EventTypes
            
            try:
                await emit_to_all(
                    event_type=EventTypes.INCIDENT_STATUS_CHANGED,
                    data={
                        "incident_id": incident_id,
                        "estado_actual": "sin_taller_disponible",
                        "new_status": "sin_taller_disponible",
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
                logger.info(f"✅ WebSocket event emitted: incident {incident_id} → sin_taller_disponible")
            except Exception as ws_err:
                logger.error(f"Failed to emit status change WebSocket event: {str(ws_err)}")
            
            logger.warning(
                f"⚠️ Administrators and client notified: incident {incident_id} has no available workshops "
                f"after {attempt_count} attempts"
            )
            return True
            
        except Exception as e:
            logger.error(f"❌ Error notifying administrators and client: {str(e)}", exc_info=True)
            return False

    async def _load_incident(self, incident_id: int) -> Optional[Incidente]:
        """Load incident by ID."""
        result = await self.session.execute(
            select(Incidente).where(Incidente.id == incident_id)
        )
        return result.scalar_one_or_none()

    def _get_timeout_minutes(self, incident: Incidente) -> int:
        """
        Get timeout in minutes based on incident priority.
        
        Args:
            incident: Incident object
            
        Returns:
            Timeout in minutes
        """
        # Determine priority based on incident attributes
        # Use prioridad_ia (not severidad_ia which doesn't exist)
        # High priority: prioridad_ia is alta
        # Medium priority: default
        # Low priority: prioridad_ia is baja
        
        priority = "media"  # default (solo como fallback, no debería usarse)
        
        if incident.prioridad_ia:
            prioridad_lower = incident.prioridad_ia.lower()
            if prioridad_lower in ["alta", "high"]:
                priority = "alta"
            elif prioridad_lower in ["baja", "low"]:
                priority = "baja"
            elif prioridad_lower in ["media", "medium"]:
                priority = "media"
        else:
            # Esto no debería pasar ahora que esperamos a la IA
            logger.warning(
                f"⚠️ Incident {incident.id} has no prioridad_ia! Using default 'media'. "
                f"This should not happen."
            )
        
        # Map priority to timeout
        timeout_map = {
            "alta": settings.assignment_timeout_high_priority,
            "media": settings.assignment_timeout_medium_priority,
            "baja": settings.assignment_timeout_low_priority
        }
        
        timeout_minutes = timeout_map.get(priority, settings.assignment_timeout_minutes)
        
        # Log para debugging
        logger.info(
            f"🕐 Timeout calculation for incident {incident.id}: "
            f"prioridad_ia='{incident.prioridad_ia}' → priority='{priority}' → timeout={timeout_minutes} minutes"
        )
        
        return timeout_minutes

    async def handle_timeout(
        self,
        incident_id: int,
        workshop_id: int
    ) -> AssignmentResult:
        """
        Handle timeout notification from frontend and reassign with recalculation.
        
        This method is called when the frontend detects a timeout or when the
        backend timeout checker finds expired assignments.
        
        Flow:
        1. Mark current attempt as 'timeout'
        2. Notify client about timeout
        3. Get list of excluded workshops (rejected + timeout)
        4. RECALCULATE available candidates (fresh data)
        5. Assign to best available candidate NOW
        6. If no candidates, notify admin and client
        
        Args:
            incident_id: ID of the incident
            workshop_id: ID of the workshop that timed out
            
        Returns:
            AssignmentResult with reassignment details
        """
        try:
            logger.info(
                f"⏰ Handling timeout for incident {incident_id} from workshop {workshop_id}"
            )
            
            # 1. Mark as timeout (may already be done by caller, but ensure it's set)
            await self.assignment_service._update_assignment_attempt_status(
                incident_id=incident_id,
                workshop_id=workshop_id,
                status="timeout",
                response_message="Timeout: No response within time limit"
            )
            
            # 2. Notify client about timeout and reassignment
            incident = await self._load_incident(incident_id)
            if incident:
                try:
                    from ...shared.schemas.events.incident import IncidentReassignmentStartedEvent
                    from ...core.event_publisher import EventPublisher
                    
                    reassignment_event = IncidentReassignmentStartedEvent(
                        incident_id=incident_id,
                        previous_workshop_id=workshop_id,
                        reason="Timeout: El taller no respondió a tiempo",
                        message="Buscando un nuevo taller disponible"
                    )
                    await EventPublisher.publish(self.session, reassignment_event)
                    logger.info(f"✅ Published reassignment_started event for incident {incident_id}")
                except Exception as e:
                    logger.error(f"Failed to publish reassignment event: {str(e)}")
            
            # 3. Wait a bit before reassigning (configurable delay)
            # This gives time for notifications to be processed
            # In production, this could be handled by a background task
            # For now, we proceed immediately
            
            # 4. Reassign with recalculation
            result = await self.reassign_to_next_candidate(incident_id)
            
            if result.success:
                logger.info(
                    f"✅ Successfully reassigned incident {incident_id} after timeout to "
                    f"{result.assigned_workshop.workshop_name if result.assigned_workshop else 'unknown'}"
                )
            else:
                logger.warning(
                    f"⚠️ Failed to reassign incident {incident_id} after timeout: {result.error_message}"
                )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error handling timeout: {str(e)}", exc_info=True)
            return AssignmentResult(
                success=False,
                error_message=f"Timeout handling error: {str(e)}"
            )

    async def _count_assignment_attempts(self, incident_id: int) -> int:
        """Count total assignment attempts for an incident."""
        result = await self.session.execute(
            select(AssignmentAttempt)
            .where(AssignmentAttempt.incident_id == incident_id)
        )
        return len(list(result.scalars().all()))
