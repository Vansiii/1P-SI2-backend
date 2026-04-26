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
                retry_count=0
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
            # ⚠️ DISABLED for chat.message_sent - OutboxProcessor handles it with full payload
            if (send_immediate and 
                event.priority == EventPriority.HIGH and 
                event.event_type != "chat.message_sent"):
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
        
        This provides low-latency delivery to online users while the
        OutboxProcessor handles FCM fallback for offline users.
        
        Args:
            session: Database session
            event: Event to send
        """
        try:
            from ..core.websocket import manager as ws_manager
            from ..models.incidente import Incidente
            from ..models.user import User
            import json
            
            # Parse event data
            event_data = json.loads(event.json())
            incident_id = event_data.get("incident_id")
            
            if not incident_id:
                # No incident_id, skip immediate delivery
                return
            
            # Determine recipients based on event type
            recipients = set()
            
            # Get incident to find participants
            incident = await session.get(Incidente, incident_id)
            if incident:
                # Add client
                if incident.client_id:
                    recipients.add(incident.client_id)
                
                # Add workshop
                if incident.taller_id:
                    recipients.add(incident.taller_id)
                
                # Add technician
                if incident.tecnico_id:
                    recipients.add(incident.tecnico_id)
            
            # For incident.assigned events, add workshop_id from payload
            if event.event_type == "incident.assigned":
                workshop_id = event_data.get("workshop_id")
                if workshop_id:
                    recipients.add(workshop_id)
            
            # For incident.assignment_accepted/rejected, add workshop_id from payload
            if event.event_type in ("incident.assignment_accepted", "incident.assignment_rejected"):
                workshop_id = event_data.get("workshop_id")
                if workshop_id:
                    recipients.add(workshop_id)
            
            # For incident.assigned events, add workshop_id from payload
            if event.event_type == "incident.assigned":
                workshop_id = event_data.get("workshop_id")
                if workshop_id:
                    recipients.add(workshop_id)
                    logger.info(f"✅ Added workshop {workshop_id} to recipients for incident.assigned event")
            
            # For incident.assignment_accepted/rejected, add workshop_id from payload
            if event.event_type in ("incident.assignment_accepted", "incident.assignment_rejected"):
                workshop_id = event_data.get("workshop_id")
                if workshop_id:
                    recipients.add(workshop_id)
                    logger.info(f"✅ Added workshop {workshop_id} to recipients for {event.event_type} event")
            
            # For incident.assignment_accepted, notify ALL workshops with pending assignments
            # so they can remove the incident from their list
            if event.event_type == "incident.assignment_accepted":
                from ..models.assignment_attempt import AssignmentAttempt
                from sqlalchemy import select, and_
                
                # Get all workshops with pending assignments for this incident
                result = await session.execute(
                    select(AssignmentAttempt.workshop_id)
                    .where(
                        and_(
                            AssignmentAttempt.incident_id == incident_id,
                            AssignmentAttempt.status == 'pending'
                        )
                    )
                    .distinct()
                )
                pending_workshops = [row[0] for row in result.all()]
                
                # Add all pending workshops to recipients
                recipients.update(pending_workshops)
                logger.info(
                    f"✅ Added {len(pending_workshops)} workshops with pending assignments "
                    f"to recipients for incident.assignment_accepted event: {pending_workshops}"
                )
            
            # For chat messages, exclude sender
            if event.event_type == "chat.message_sent":
                sender_id = event_data.get("sender_id")
                if sender_id and sender_id in recipients:
                    recipients.remove(sender_id)
                    logger.debug(f"Excluded sender {sender_id} from immediate WebSocket recipients")
            
            # Add administrators for critical events
            if event.event_type.startswith(("incident.created", "incident.cancelled", "incident.status_changed")):
                from sqlalchemy import select
                admin_result = await session.execute(
                    select(User.id).where(User.user_type == "administrator")
                )
                admin_ids = admin_result.scalars().all()
                recipients.update(admin_ids)
            
            # Send to online recipients via WebSocket
            online_count = 0
            for user_id in recipients:
                if ws_manager.is_user_connected(user_id):
                    try:
                        logger.info(f"🚀 Sending immediate WebSocket to user {user_id}: {event.event_type}")
                        await ws_manager.send_to_user(user_id, event_data)
                        online_count += 1
                        logger.info(f"✅ Immediate WebSocket sent successfully to user {user_id}")
                    except Exception as e:
                        logger.warning(f"Failed immediate WebSocket to user {user_id}: {str(e)}")
            
            if online_count > 0:
                logger.info(
                    f"🚀 Sent immediate WebSocket for {event.event_type} to {online_count} online users "
                    f"(event_id={event.event_id})"
                )
            
        except Exception as e:
            # Don't fail the entire publish operation if immediate delivery fails
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
