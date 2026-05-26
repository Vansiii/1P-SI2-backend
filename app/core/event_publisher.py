"""
Event Publisher for Transactional Outbox Pattern.

This module provides the EventPublisher class that publishes events
to the outbox table within the same database transaction as business operations.
This guarantees eventual consistency between database state and emitted events.

IMPORTANT: For critical real-time events (HIGH priority), this publisher also
sends immediate WebSocket notifications to ensure low latency, while still
using the OutboxProcessor as a reliable fallback for offline users.
"""

import json
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.outbox_event import OutboxEvent
from ..shared.schemas.events.base import BaseEvent, EventPriority
from .logging import get_logger

logger = get_logger(__name__)


class EventPublisher:
    """
    Event Publisher for transactional event publishing.
    
    This class publishes events to the outbox table within the same
    database transaction as business operations. Events are then
    processed asynchronously by the OutboxProcessor.
    
    For HIGH priority events, it also sends immediate WebSocket notifications
    to online users for low-latency delivery, while the OutboxProcessor
    handles FCM fallback for offline users.
    
    Usage:
        ```python
        async with get_db_session() as session:
            # Business operation
            incident = Incidente(...)
            session.add(incident)
            
            # Publish event in same transaction
            event = IncidentCreatedEvent(
                incident_id=incident.id,
                client_id=incident.client_id,
                ...
            )
            await EventPublisher.publish(session, event)
            
            # Commit transaction (both incident and event)
            await session.commit()
        ```
    
    Benefits:
        - Atomic: Event is persisted with business operation
        - Consistent: No event without DB change, no DB change without event
        - Reliable: Events are never lost
        - Decoupled: Business logic doesn't depend on WebSocket/FCM
        - Low-latency: HIGH priority events sent immediately via WebSocket
    """
    
    @staticmethod
    async def publish(
        session: AsyncSession,
        event: BaseEvent,
        *,
        commit: bool = False,
        send_immediate: bool = True
    ) -> OutboxEvent:
        """
        Publish a single event to the outbox.
        
        Args:
            session: Database session (must be active transaction)
            event: Event to publish (must inherit from BaseEvent)
            commit: Whether to commit the transaction (default: False)
            send_immediate: Whether to send immediate WebSocket notification for HIGH priority events (default: True)
        
        Returns:
            OutboxEvent: The created outbox event record
        
        Raises:
            ValueError: If event is invalid
            SQLAlchemyError: If database operation fails
        
        Example:
            ```python
            event = IncidentCreatedEvent(
                incident_id=123,
                client_id=456,
                location={"lat": 40.7128, "lng": -74.0060},
                description="Engine problem"
            )
            outbox_event = await EventPublisher.publish(session, event)
            ```
        """
        try:
            # Serialize event to JSON
            payload = event.json()
            
            # Create outbox event
            outbox_event = OutboxEvent(
                event_id=event.event_id,
                event_type=event.event_type,
                payload=payload,
                version=event.version,
                priority=event.priority,
                processed=False,
                retry_count=0,
                ws_immediate_sent=False
            )
            
            # Add to session (will be committed with business operation)
            session.add(outbox_event)
            
            # Optionally commit immediately
            if commit:
                await session.commit()
                await session.refresh(outbox_event)
            
            logger.debug(
                f"Published event to outbox: {event.event_type} "
                f"(event_id={event.event_id}, priority={event.priority})"
            )
            
            # 🚀 For HIGH priority events, send immediate WebSocket notification
            if (send_immediate and 
                event.priority == EventPriority.HIGH):
                await EventPublisher._send_immediate_websocket(session, event)
            
            return outbox_event
            
        except Exception as e:
            logger.error(
                f"Failed to publish event {event.event_type}: {str(e)}",
                exc_info=True
            )
            raise
    
    @staticmethod
    async def _send_immediate_websocket(
        session: AsyncSession,
        event: BaseEvent
    ):
        """
        Send immediate WebSocket notification for HIGH priority events.

        CRITICAL FIX: Uses the outbox event's own event_id for deduplication
        so the OutboxProcessor won't re-deliver the same event via WS.
        Broadcasts via send_personal_message (with dedup enabled) so the
        server-side dedup cache is populated, preventing the OutboxProcessor
        from sending the same event again via WebSocket.

        Individual user sends replace workshop broadcasts entirely to avoid
        double-delivery to workshop members (who are also in the recipients set).
        """
        try:
            from ..core.websocket import manager as ws_manager
            from ..core.websocket_events import _build_event_payload
            from ..models.incidente import Incidente
            from ..models.user import User

            event_data = json.loads(event.json())
            incident_id = event_data.get("incident_id")

            # Use the outbox event's own event_id so dedup is consistent
            ws_payload = _build_event_payload(event.event_type, event_data, event_id=str(event.event_id))

            recipients = set()

            # Handle notification.* events (have user_id instead of incident_id)
            if event.event_type.startswith("notification."):
                user_id = event_data.get("user_id")
                if user_id:
                    recipients.add(user_id)
                    if ws_manager.is_user_connected(user_id):
                        try:
                            await ws_manager.send_personal_message(
                                user_id, ws_payload, check_dedup=True
                            )
                            logger.debug(
                                f"Sent immediate WS notification event to user {user_id}"
                            )
                        except Exception as e:
                            logger.warning(
                                f"Failed immediate WS notification to user {user_id}: {str(e)}"
                            )
                return

            # Handle dashboard.* events (broadcast to all admins)
            if event.event_type.startswith("dashboard."):
                from sqlalchemy import select
                admin_result = await session.execute(
                    select(User.id).where(User.user_type == "admin")
                )
                admin_ids = admin_result.scalars().all()
                for admin_id in admin_ids:
                    recipients.add(admin_id)
                    if ws_manager.is_user_connected(admin_id):
                        try:
                            await ws_manager.send_personal_message(
                                admin_id, ws_payload, check_dedup=True
                            )
                        except Exception as e:
                            logger.debug(
                                f"Failed immediate WS dashboard to admin {admin_id}: {str(e)}"
                            )
                if recipients:
                    logger.info(
                        f"Sent immediate WS for dashboard event {event.event_type} "
                        f"to {len(recipients)} admins"
                    )
                return

            if not incident_id:
                return

            incident = await session.get(Incidente, incident_id)
            if incident:
                if incident.client_id:
                    recipients.add(incident.client_id)
                if incident.taller_id:
                    recipients.add(incident.taller_id)
                if incident.tecnico_id:
                    recipients.add(incident.tecnico_id)

            # For cancellation.* events, also include the original requester
            # (incident.taller_id may have been cleared by _cancel_incident_and_reassign).
            requested_by = event_data.get("requested_by")
            if requested_by:
                recipients.add(requested_by)

            workshop_id = event_data.get("workshop_id")
            if workshop_id:
                recipients.add(workshop_id)

            if event.event_type == "incident.assignment_accepted":
                from ..models.assignment_attempt import AssignmentAttempt
                from sqlalchemy import select, and_

                result = await session.execute(
                    select(AssignmentAttempt.workshop_id)
                    .where(
                        and_(
                            AssignmentAttempt.incident_id == incident_id,
                            AssignmentAttempt.status.in_(["pending", "timeout", "no_response"])
                        )
                    )
                    .distinct()
                )
                affected_workshops = [row[0] for row in result.all()]
                recipients.update(affected_workshops)

                if affected_workshops:
                    logger.info(
                        f"Notifying {len(affected_workshops)} workshops with pending/timeout "
                        f"assignments for incident {incident_id}"
                    )

            if event.event_type == "chat.message_sent":
                sender_id = event_data.get("sender_id")
                if sender_id:
                    recipients.discard(sender_id)

            admin_event_prefixes = (
                "incident.created", "incident.cancelled",
                "incident.status_changed", "incident.assigned",
                "incident.assignment_accepted", "incident.assignment_rejected",
                "incident.assignment_timeout", "incident.no_workshop_available"
            )
            if event.event_type.startswith(admin_event_prefixes):
                from sqlalchemy import select
                admin_result = await session.execute(
                    select(User.id).where(User.user_type == "admin")
                )
                admin_ids = admin_result.scalars().all()
                recipients.update(admin_ids)

            online_count = 0
            sent_user_ids = set()
            for user_id in recipients:
                if ws_manager.is_user_connected(user_id):
                    try:
                        await ws_manager.send_personal_message(
                            user_id, ws_payload, check_dedup=True
                        )
                        online_count += 1
                        sent_user_ids.add(user_id)
                    except Exception as e:
                        logger.warning(
                            f"Failed immediate WebSocket to user {user_id}: {str(e)}"
                        )

            # Broadcast to workshop rooms for workshop-relevant events
            # Workshop staff (beyond the owner) need to receive notifications
            target_workshop = workshop_id or (incident.taller_id if incident else None)
            workshop_event_prefixes = (
                "incident.assigned", "incident.assignment_accepted",
                "incident.status_changed", "incident.work_started",
                "incident.work_completed", "incident.cancelled",
                "incident.technician_on_way", "incident.technician_arrived",
                "incident.photos_uploaded"
            )
            if target_workshop and event.event_type.startswith(workshop_event_prefixes):
                try:
                    await ws_manager.broadcast_to_workshop(
                        target_workshop, ws_payload
                    )
                    logger.debug(
                        f"Broadcasted {event.event_type} to workshop room {target_workshop}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed workshop room broadcast: {str(e)}"
                    )

            if online_count > 0:
                logger.info(
                    f"Sent immediate WebSocket for {event.event_type} "
                    f"to {online_count} online users (event_id={event.event_id})"
                )

        except Exception as e:
            logger.warning(
                f"Failed to send immediate WebSocket for {event.event_type}: {str(e)}"
            )
    
    @staticmethod
    async def publish_batch(
        session: AsyncSession,
        events: List[BaseEvent],
        *,
        commit: bool = False,
        send_immediate: bool = True
    ) -> List[OutboxEvent]:
        """
        Publish multiple events to the outbox in a single transaction.
        
        Args:
            session: Database session (must be active transaction)
            events: List of events to publish
            commit: Whether to commit the transaction (default: False)
            send_immediate: Whether to send immediate WebSocket notifications for HIGH priority events (default: True)
        
        Returns:
            List[OutboxEvent]: The created outbox event records
        
        Raises:
            ValueError: If any event is invalid
            SQLAlchemyError: If database operation fails
        
        Example:
            ```python
            events = [
                IncidentCreatedEvent(...),
                NotificationReceivedEvent(...),
                DashboardMetricsUpdatedEvent(...)
            ]
            outbox_events = await EventPublisher.publish_batch(session, events)
            ```
        """
        if not events:
            logger.warning("publish_batch called with empty events list")
            return []
        
        try:
            outbox_events = []
            
            for event in events:
                # Serialize event to JSON
                payload = event.json()
                
                # Create outbox event
                outbox_event = OutboxEvent(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    payload=payload,
                    version=event.version,
                    priority=event.priority,
                    processed=False,
                    retry_count=0
                )
                
                session.add(outbox_event)
                outbox_events.append(outbox_event)
                
                # 🚀 For HIGH priority events, send immediate WebSocket notification
                if send_immediate and event.priority == EventPriority.HIGH:
                    await EventPublisher._send_immediate_websocket(session, event)
            
            # Optionally commit immediately
            if commit:
                await session.commit()
                for outbox_event in outbox_events:
                    await session.refresh(outbox_event)
            
            logger.debug(
                f"Published {len(events)} events to outbox in batch"
            )
            
            return outbox_events
            
        except Exception as e:
            logger.error(
                f"Failed to publish batch of {len(events)} events: {str(e)}",
                exc_info=True
            )
            raise
    
    @staticmethod
    def validate_event(event: BaseEvent) -> bool:
        """
        Validate that an event is properly structured.
        
        Args:
            event: Event to validate
        
        Returns:
            bool: True if valid, False otherwise
        
        Raises:
            ValueError: If event is invalid with detailed message
        """
        if not isinstance(event, BaseEvent):
            raise ValueError(
                f"Event must inherit from BaseEvent, got {type(event)}"
            )
        
        if not event.event_type:
            raise ValueError("Event must have event_type")
        
        if not event.event_id:
            raise ValueError("Event must have event_id")
        
        if not event.timestamp:
            raise ValueError("Event must have timestamp")
        
        return True
