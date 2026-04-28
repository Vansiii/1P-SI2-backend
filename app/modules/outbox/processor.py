"""
Outbox Processor for asynchronous event delivery.

This processor continuously polls the outbox_events table for pending events
and delivers them via WebSocket and FCM, ensuring reliable event delivery.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import List, Optional, Set
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_session_factory
from ...core.websocket import ConnectionManager
from ...core.push_integration import send_notification_with_fallback
from ...core.logging import get_logger
from ...models.outbox_event import OutboxEvent, EventPriority
from ...models.event_log import EventLog
from ...models.user import User
from ...models.incidente import Incidente
from .delivery_strategies import DeliveryStrategyFactory
from .notification_filter import NotificationFilter, DeliveryMode

logger = get_logger(__name__)


class OutboxProcessor:
    """
    Outbox Processor for asynchronous event delivery.
    
    This processor runs as a background task and continuously processes
    pending events from the outbox_events table. It:
    
    1. Queries pending events (processed=False, retry_count<3)
    2. Determines recipients based on event type
    3. Delivers via WebSocket if user is online
    4. Delivers via FCM if user is offline
    5. Logs delivery in event_log table
    6. Marks event as processed
    7. Handles retries on failure
    
    Attributes:
        ws_manager: WebSocket connection manager
        session_factory: Database session factory
        running: Whether processor is running
        batch_size: Number of events to process per batch
        poll_interval: Seconds between polls
        max_retries: Maximum retry attempts
    """
    
    def __init__(
        self,
        ws_manager: ConnectionManager,
        batch_size: int = 100,
        poll_interval: float = 1.0,
        max_retries: int = 3
    ):
        """
        Initialize OutboxProcessor.
        
        Args:
            ws_manager: WebSocket connection manager
            batch_size: Number of events to process per batch (default: 100)
            poll_interval: Seconds between polls (default: 1.0)
            max_retries: Maximum retry attempts (default: 3)
        """
        self.ws_manager = ws_manager
        self.session_factory = get_session_factory()
        self.running = False
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self.max_retries = max_retries
        self._task: Optional[asyncio.Task] = None
        
        # Initialize delivery strategy factory
        self.strategy_factory = DeliveryStrategyFactory(ws_manager)
        
        # Health check metrics
        self._last_poll_time: Optional[datetime] = None
        self._total_events_processed: int = 0
        self._total_events_failed: int = 0
        self._last_error: Optional[str] = None
        self._last_error_time: Optional[datetime] = None
    
    async def start(self):
        """Start the outbox processor background task."""
        if self.running:
            logger.warning("OutboxProcessor is already running")
            return
        
        self.running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info(
            f"🚀 OutboxProcessor started "
            f"(batch_size={self.batch_size}, poll_interval={self.poll_interval}s)"
        )
    
    async def stop(self):
        """Stop the outbox processor background task."""
        if not self.running:
            return
        
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("🛑 OutboxProcessor stopped")
    
    async def _process_loop(self):
        """Main processing loop that runs continuously."""
        logger.info("OutboxProcessor loop started")
        
        while self.running:
            try:
                self._last_poll_time = datetime.now()
                await self.process_pending_events()
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                logger.info("OutboxProcessor loop cancelled")
                break
            except Exception as e:
                self._last_error = str(e)
                self._last_error_time = datetime.now()
                logger.error(
                    f"Error in OutboxProcessor loop: {str(e)}",
                    exc_info=True
                )
                # Continue processing despite errors
                await asyncio.sleep(self.poll_interval)
    
    async def process_pending_events(self) -> int:
        """
        Process pending events from the outbox.
        
        Returns:
            int: Number of events processed
        """
        async with self.session_factory() as session:
            try:
                # Query pending events
                pending_events = await self._get_pending_events(session)
                
                if not pending_events:
                    return 0
                
                logger.debug(f"Processing {len(pending_events)} pending events")
                
                # Process each event
                processed_count = 0
                failed_count = 0
                for outbox_event in pending_events:
                    try:
                        await self._dispatch_event(session, outbox_event)
                        processed_count += 1
                        self._total_events_processed += 1
                    except Exception as e:
                        failed_count += 1
                        self._total_events_failed += 1
                        self._last_error = str(e)
                        self._last_error_time = datetime.now()
                        logger.error(
                            f"Failed to dispatch event {outbox_event.id}: {str(e)}",
                            exc_info=True
                        )
                        # Mark as failed with retry
                        await self._mark_failed(session, outbox_event, str(e))
                
                # Commit all changes
                await session.commit()
                
                if processed_count > 0:
                    logger.info(f"✅ Processed {processed_count} events (failed: {failed_count})")
                
                return processed_count
                
            except Exception as e:
                self._last_error = str(e)
                self._last_error_time = datetime.now()
                logger.error(
                    f"Error processing pending events: {str(e)}",
                    exc_info=True
                )
                await session.rollback()
                return 0
    
    async def _get_pending_events(
        self,
        session: AsyncSession
    ) -> List[OutboxEvent]:
        """
        Get pending events ordered by priority and creation time.
        
        Args:
            session: Database session
        
        Returns:
            List of pending OutboxEvent records
        """
        # Query pending events (not processed, retry_count < max_retries)
        query = select(OutboxEvent).where(
            and_(
                OutboxEvent.processed == False,
                OutboxEvent.retry_count < self.max_retries
            )
        ).order_by(
            # Order by priority (CRITICAL first) then creation time
            OutboxEvent.priority.desc(),
            OutboxEvent.created_at.asc()
        ).limit(self.batch_size).with_for_update(skip_locked=True)
        
        result = await session.execute(query)
        return list(result.scalars().all())
    
    async def _dispatch_event(
        self,
        session: AsyncSession,
        outbox_event: OutboxEvent
    ):
        """
        Dispatch a single event to recipients.
        
        Args:
            session: Database session
            outbox_event: Event to dispatch
        """
        # Parse event payload
        event_data = json.loads(outbox_event.payload)
        
        # Determine recipients based on event type
        recipients = await self._get_event_recipients(
            session,
            outbox_event.event_type,
            event_data
        )
        
        if not recipients:
            logger.warning(
                f"No recipients found for event {outbox_event.event_type} "
                f"(event_id={outbox_event.event_id})"
            )
            # Mark as processed anyway (no recipients)
            await self._mark_processed(session, outbox_event)
            return
        
        logger.info(
            f"📤 Dispatching event {outbox_event.event_type} to {len(recipients)} recipients: {list(recipients)}"
        )
        
        # Deliver to each recipient
        for user_id in recipients:
            await self._deliver_to_user(
                session,
                outbox_event,
                user_id,
                event_data
            )
        
        # Mark as processed
        await self._mark_processed(session, outbox_event)
    
    async def _get_event_recipients(
        self,
        session: AsyncSession,
        event_type: str,
        event_data: dict
    ) -> Set[int]:
        """
        Determinar destinatarios para un evento con FILTRADO INTELIGENTE.
        
        Aplica NotificationFilter para evitar spam y enviar solo notificaciones relevantes.
        
        Args:
            session: Database session
            event_type: Tipo de evento
            event_data: Event payload data
        
        Returns:
            Set de user IDs que deben recibir este evento (filtrados)
        """
        # Verificar si es evento silencioso (no notificar a nadie)
        if event_type in NotificationFilter.SILENT_EVENTS:
            logger.debug(f"🔇 Event {event_type} is SILENT - no notifications will be sent")
            return set()
        
        # Obtener candidatos iniciales
        candidate_recipients = set()
        incident_participants = {
            "client_id": None,
            "workshop_id": None,
            "technician_id": None
        }
        
        # Extract incident_id if present
        incident_id = event_data.get("incident_id")
        
        logger.info(f"🔍 Determining recipients for {event_type}, incident_id={incident_id}")
        
        if incident_id:
            # Get incident participants
            incident = await session.get(Incidente, incident_id)
            if incident:
                # Store participants for filtering
                incident_participants["client_id"] = incident.client_id
                incident_participants["workshop_id"] = incident.taller_id
                incident_participants["technician_id"] = incident.tecnico_id
                
                # Add as candidates
                if incident.client_id:
                    candidate_recipients.add(incident.client_id)
                if incident.taller_id:
                    candidate_recipients.add(incident.taller_id)
                if incident.tecnico_id:
                    candidate_recipients.add(incident.tecnico_id)
        
        # For incident.assigned events, add workshop_id from payload
        if event_type == "incident.assigned":
            workshop_id = event_data.get("workshop_id")
            if workshop_id:
                candidate_recipients.add(workshop_id)
                incident_participants["workshop_id"] = workshop_id
        
        # For incident.assignment_accepted/rejected, add workshop_id from payload
        if event_type in ("incident.assignment_accepted", "incident.assignment_rejected"):
            workshop_id = event_data.get("workshop_id")
            if workshop_id:
                candidate_recipients.add(workshop_id)
        
        # For incident.assignment_timeout, add workshops that had attempts
        if event_type == "incident.assignment_timeout" and incident_id:
            from ...models.assignment_attempt import AssignmentAttempt
            attempt_result = await session.execute(
                select(AssignmentAttempt.workshop_id).where(
                    AssignmentAttempt.incident_id == incident_id
                ).distinct()
            )
            workshop_ids = attempt_result.scalars().all()
            candidate_recipients.update(workshop_ids)
        
        # For incident.status_changed to 'sin_taller_disponible', add workshops
        if event_type == "incident.status_changed":
            new_status = event_data.get("new_status")
            if new_status == "sin_taller_disponible" and incident_id:
                from ...models.assignment_attempt import AssignmentAttempt
                attempt_result = await session.execute(
                    select(AssignmentAttempt.workshop_id).where(
                        AssignmentAttempt.incident_id == incident_id
                    ).distinct()
                )
                workshop_ids = attempt_result.scalars().all()
                candidate_recipients.update(workshop_ids)
        
        # For incident.no_workshop_available, add admins
        if event_type == "incident.no_workshop_available" and incident_id:
            admin_result = await session.execute(
                select(User.id).where(User.user_type == "administrator")
            )
            admin_ids = admin_result.scalars().all()
            candidate_recipients.update(admin_ids)
        
        # For technician events, add technician
        if event_type in ("incident.technician_on_way", "incident.technician_arrived", 
                         "incident.work_started", "incident.work_completed"):
            technician_id = event_data.get("technician_id")
            if technician_id:
                candidate_recipients.add(technician_id)
        
        # Add administrators for critical system events
        if event_type.startswith(("incident.created", "incident.cancelled", "audit.")):
            admin_result = await session.execute(
                select(User.id).where(User.user_type == "administrator")
            )
            admin_ids = admin_result.scalars().all()
            candidate_recipients.update(admin_ids)
        
        # Dashboard events go to all admins
        if event_type.startswith("dashboard."):
            admin_result = await session.execute(
                select(User.id).where(User.user_type == "administrator")
            )
            admin_ids = admin_result.scalars().all()
            candidate_recipients.update(admin_ids)
        
        # Notification events have explicit recipient
        if event_type.startswith("notification."):
            user_id = event_data.get("user_id")
            if user_id:
                candidate_recipients.add(user_id)
        
        # APLICAR FILTRO INTELIGENTE
        if not candidate_recipients:
            logger.debug(f"No candidate recipients for {event_type}")
            return set()
        
        # Obtener datos de usuarios para filtrado
        users_result = await session.execute(
            select(User.id, User.user_type).where(User.id.in_(candidate_recipients))
        )
        users_data = {row.id: {"user_type": row.user_type} for row in users_result}
        
        # Aplicar filtro
        filtered_recipients = set()
        for user_id in candidate_recipients:
            user_info = users_data.get(user_id, {})
            user_type = user_info.get("user_type", "unknown")
            
            # Special logging for chat messages
            if event_type == "chat.message_sent":
                sender_id = event_data.get("sender_id")
                logger.info(
                    f"  🔍 Chat filter check: user={user_id}, type={user_type}, "
                    f"sender={sender_id}, participants={incident_participants}"
                )
            
            if NotificationFilter.should_notify_user(
                event_type=event_type,
                user_type=user_type,
                user_id=user_id,
                event_data=event_data,
                incident_participants=incident_participants
            ):
                filtered_recipients.add(user_id)
                logger.info(f"  ✅ User {user_id} ({user_type}) will receive notification")
            else:
                logger.debug(f"  🚫 User {user_id} ({user_type}) filtered out (not relevant)")
        
        if not filtered_recipients:
            logger.info(f"🔇 No recipients after filtering for {event_type}")
        else:
            logger.info(f"📤 {len(filtered_recipients)} recipients after filtering: {list(filtered_recipients)}")
        
        return filtered_recipients
    
    async def _deliver_to_user(
        self,
        session: AsyncSession,
        outbox_event: OutboxEvent,
        user_id: int,
        event_data: dict
    ) -> bool:
        """
        Deliver event to a specific user using appropriate delivery strategy.
        
        This method has been refactored to use the Delivery Strategies Pattern.
        No more "assumed delivery" logic - all deliveries are verified.
        
        Args:
            session: Database session
            outbox_event: Event to deliver
            user_id: User ID to deliver to
            event_data: Event payload data
            
        Returns:
            True if delivery succeeded, False otherwise
        """
        # Get appropriate delivery strategy for this event type
        strategy = self.strategy_factory.get_strategy(outbox_event.event_type)
        
        logger.debug(
            f"Using {strategy.__class__.__name__} for event {outbox_event.event_type} "
            f"to user {user_id}"
        )
        
        # Execute delivery via strategy
        result = await strategy.deliver(session, user_id, event_data)
        
        # Log delivery if successful
        if result.success:
            await self._log_delivery(
                session,
                outbox_event,
                user_id,
                result.channel
            )
            
            logger.info(
                f"✅ Delivered event {outbox_event.event_type} to user {user_id} "
                f"via {result.channel}"
            )
            
            # Publish chat.message_delivered event if applicable
            if outbox_event.event_type == "chat.message_sent":
                await self._publish_message_delivered_event(
                    session,
                    event_data,
                    user_id,
                    result.channel
                )
        else:
            logger.warning(
                f"❌ Failed to deliver event {outbox_event.event_type} to user {user_id}: "
                f"{result.reason}"
            )
        
        return result.success
    
    async def _publish_message_delivered_event(
        self,
        session: AsyncSession,
        event_data: dict,
        delivered_to: int,
        delivered_via: str
    ):
        """
        Publish chat.message_delivered event for chat messages.
        
        Args:
            session: Database session
            event_data: Original event data
            delivered_to: User ID who received the message
            delivered_via: Delivery channel used
        """
        try:
            from ...shared.schemas.events.chat import ChatMessageDeliveredEvent
            
            message_id = event_data.get("message_id")
            if not message_id:
                return
            
            delivered_event = ChatMessageDeliveredEvent(
                message_id=message_id,
                delivered_to=delivered_to,
                delivered_at=datetime.utcnow()
            )
            
            from ...core.event_publisher import EventPublisher
            await EventPublisher.publish(session, delivered_event)
            
            logger.debug(
                f"✅ Published MESSAGE_DELIVERED event for message {message_id} "
                f"delivered to user {delivered_to} via {delivered_via}"
            )
        except Exception as e:
            logger.error(
                f"❌ Error publishing MESSAGE_DELIVERED event: {str(e)}",
                exc_info=True
            )
    
    def _get_notification_title(self, event_type: str) -> str:
        """Get notification title based on event type - Professional and minimalist."""
        title_map = {
            "incident.created": "Solicitud Recibida",
            "incident.analysis_completed": "Diagnóstico de IA Completado",
            "incident.assigned": "Taller Asignado",
            "incident.technician_assigned": "Técnico Asignado",
            "incident.assignment_accepted": "Solicitud Aceptada",
            "incident.assignment_rejected": "Solicitud Rechazada",
            "incident.assignment_timeout": "Tiempo de Espera Agotado",
            "incident.technician_on_way": "Técnico en Camino",
            "incident.technician_arrived": "Técnico en Sitio",
            "incident.work_started": "Servicio Iniciado",
            "incident.work_completed": "Servicio Finalizado",
            "incident.cancelled": "Solicitud Cancelada",
            "incident.no_workshop_available": "Sin Talleres Disponibles",
            "chat.message_sent": "Nuevo mensaje",
            "notification.received": "Notificación",
        }
        return title_map.get(event_type, "Actualización")
    
    def _get_notification_body(self, event_data: dict) -> str:
        """Get notification body from event data - Professional and context-aware."""
        event_type = event_data.get("event_type", "")
        incident_id = event_data.get("incident_id", "")
        
        # Custom messages based on event type
        body_map = {
            "incident.analysis_completed": "El análisis inicial de tu solicitud está listo.",
            "incident.assigned": f"Hemos asignado un taller para tu solicitud #{incident_id}",
            "incident.technician_assigned": "Se ha asignado un técnico a tu solicitud",
            "incident.assignment_accepted": f"El taller ha aceptado tu solicitud #{incident_id}",
            "incident.assignment_rejected": f"Buscando alternativa para tu solicitud #{incident_id}",
            "incident.assignment_timeout": f"Reasignando tu solicitud #{incident_id}",
            
            "incident.technician_on_way": "El técnico se dirige a tu ubicación",
            "incident.technician_arrived": "El técnico ha llegado al lugar",
            "incident.work_started": "El servicio ha iniciado",
            "incident.work_completed": "El servicio ha sido completado",
            
            "incident.searching_workshop": "Buscando el mejor taller disponible para tu solicitud",
            "incident.no_workshop_available": "No hay talleres disponibles. Puedes esperar o cancelar la solicitud",
            "incident.reassignment_started": "Buscando un nuevo taller para tu solicitud",
            
            "incident.cancelled": f"La solicitud #{incident_id} ha sido cancelada",
            
            "chat.message_sent": event_data.get("content", "Tienes un nuevo mensaje")[:100],
        }
        
        # Return custom message or extract from event data
        if event_type in body_map:
            return body_map[event_type]
        
        # Fallback: try to extract meaningful message from event data
        if "message" in event_data:
            return event_data["message"][:100]
        elif "description" in event_data:
            return event_data["description"][:100]
        elif "body" in event_data:
            return event_data["body"][:100]
        elif "content" in event_data:
            return event_data["content"][:100]
        else:
            return "Tienes una actualización"
    
    async def _log_delivery(
        self,
        session: AsyncSession,
        outbox_event: OutboxEvent,
        user_id: int,
        delivered_via: str
    ):
        """Log event delivery in event_log table."""
        event_log = EventLog(
            event_id=outbox_event.event_id,
            event_type=outbox_event.event_type,
            payload=outbox_event.payload,
            delivered_via=delivered_via,
            delivered_to=user_id,
            delivered_at=datetime.utcnow()
        )
        session.add(event_log)
    
    async def _mark_processed(
        self,
        session: AsyncSession,
        outbox_event: OutboxEvent
    ):
        """Mark event as successfully processed."""
        outbox_event.processed = True
        outbox_event.processed_at = datetime.utcnow()
        outbox_event.last_error = None
    
    async def _mark_failed(
        self,
        session: AsyncSession,
        outbox_event: OutboxEvent,
        error: str
    ):
        """Mark event as failed and increment retry count."""
        outbox_event.retry_count += 1
        outbox_event.last_error = error[:500]  # Truncate error message
        
        # If max retries reached, mark as processed (failed permanently)
        if outbox_event.retry_count >= self.max_retries:
            outbox_event.processed = True
            outbox_event.processed_at = datetime.utcnow()
            logger.error(
                f"Event {outbox_event.id} failed permanently after {self.max_retries} retries"
            )
    def get_health_status(self) -> dict:
        """
        Get health status of the OutboxProcessor.
        
        Returns:
            dict: Health status information
        """
        now = datetime.now()
        
        # Check if processor is running
        is_healthy = self.running
        
        # Check if last poll was recent (within 2x poll interval)
        if self._last_poll_time:
            time_since_last_poll = (now - self._last_poll_time).total_seconds()
            poll_threshold = self.poll_interval * 2
            is_polling_healthy = time_since_last_poll <= poll_threshold
        else:
            is_polling_healthy = False
            time_since_last_poll = None
        
        # Check error rate (if more than 50% of events are failing)
        total_events = self._total_events_processed + self._total_events_failed
        error_rate = (self._total_events_failed / total_events * 100) if total_events > 0 else 0
        is_error_rate_healthy = error_rate < 50.0
        
        # Overall health
        overall_healthy = is_healthy and is_polling_healthy and is_error_rate_healthy
        
        return {
            "status": "healthy" if overall_healthy else "unhealthy",
            "running": self.running,
            "last_poll_time": self._last_poll_time.isoformat() if self._last_poll_time else None,
            "time_since_last_poll_seconds": time_since_last_poll,
            "polling_healthy": is_polling_healthy,
            "configuration": {
                "batch_size": self.batch_size,
                "poll_interval": self.poll_interval,
                "max_retries": self.max_retries
            },
            "metrics": {
                "total_events_processed": self._total_events_processed,
                "total_events_failed": self._total_events_failed,
                "error_rate_percent": round(error_rate, 2),
                "error_rate_healthy": is_error_rate_healthy
            },
            "last_error": {
                "message": self._last_error,
                "timestamp": self._last_error_time.isoformat() if self._last_error_time else None
            } if self._last_error else None,
            "task_info": {
                "task_running": self._task is not None and not self._task.done(),
                "task_cancelled": self._task.cancelled() if self._task else False,
                "task_done": self._task.done() if self._task else False
            }
        }
    
    async def get_pending_events_count(self) -> dict:
        """
        Get count of pending events in the outbox.
        
        Returns:
            dict: Pending events statistics
        """
        async with self.session_factory() as session:
            try:
                # Count pending events by priority
                from sqlalchemy import func
                
                query = select(
                    OutboxEvent.priority,
                    func.count(OutboxEvent.id).label('count')
                ).where(
                    and_(
                        OutboxEvent.processed == False,
                        OutboxEvent.retry_count < self.max_retries
                    )
                ).group_by(OutboxEvent.priority)
                
                result = await session.execute(query)
                priority_counts = {row.priority.value: row.count for row in result}
                
                # Total pending
                total_pending = sum(priority_counts.values())
                
                # Count failed events (max retries reached)
                failed_query = select(func.count(OutboxEvent.id)).where(
                    and_(
                        OutboxEvent.processed == False,
                        OutboxEvent.retry_count >= self.max_retries
                    )
                )
                failed_result = await session.execute(failed_query)
                failed_count = failed_result.scalar() or 0
                
                return {
                    "total_pending": total_pending,
                    "by_priority": priority_counts,
                    "failed_permanently": failed_count,
                    "is_backlog_healthy": total_pending < 1000  # Threshold for healthy backlog
                }
                
            except Exception as e:
                logger.error(f"Error getting pending events count: {str(e)}")
                return {
                    "error": str(e),
                    "total_pending": None,
                    "by_priority": {},
                    "failed_permanently": None,
                    "is_backlog_healthy": False
                }