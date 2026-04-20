"""
Chat service for managing conversations and messages.
"""
from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_, func
from sqlalchemy.orm import selectinload

from ...core.logging import get_logger
from ...core.exceptions import NotFoundError, ValidationError
from ...models.message import Message
from ...models.conversation import Conversation
from ...models.incidente import Incidente
from ...models.user import User
from ...core.websocket import manager
from ...core.websocket_events import emit_to_incident_room, EventTypes
from ..push_notifications.services import PushNotificationService

logger = get_logger(__name__)


class ChatService:
    """
    Service for managing chat conversations and messages.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.push_service = PushNotificationService(session)

    async def get_or_create_conversation(
        self,
        incident_id: int,
        client_id: int,
        workshop_id: Optional[int] = None
    ) -> Conversation:
        """
        Get existing conversation or create new one for an incident.
        
        Args:
            incident_id: ID of the incident
            client_id: ID of the client
            workshop_id: Optional ID of the workshop
            
        Returns:
            Conversation object
        """
        # Try to get existing conversation
        conversation = await self.session.scalar(
            select(Conversation).where(Conversation.incident_id == incident_id)
        )

        if conversation:
            return conversation

        # Create new conversation
        conversation = Conversation(
            incident_id=incident_id,
            client_id=client_id,
            workshop_id=workshop_id,
            unread_count_client=0,
            unread_count_workshop=0
        )

        self.session.add(conversation)
        await self.session.commit()
        await self.session.refresh(conversation)

        logger.info(f"Created conversation {conversation.id} for incident {incident_id}")
        return conversation

    async def send_message(
        self,
        incident_id: int,
        sender_id: int,
        message_text: str,
        message_type: str = "text"
    ) -> Message:
        """
        Send a message in a conversation.
        
        Validates that sender is authorized participant:
        - Client can always send messages
        - Workshop staff can send when workshop is assigned
        - Technician can send when assigned to incident
        
        Args:
            incident_id: ID of the incident
            sender_id: ID of the message sender
            message_text: Content of the message
            message_type: Type of message (text, image, audio, system)
            
        Returns:
            Created message
            
        Raises:
            NotFoundError: If incident not found
            ValidationError: If message is empty or sender not authorized
        """
        if not message_text.strip():
            raise ValidationError("Message cannot be empty")

        # Verify incident exists and load relationships
        incident = await self.session.scalar(
            select(Incidente)
            .options(selectinload(Incidente.technician))
            .where(Incidente.id == incident_id)
        )
        if not incident:
            raise NotFoundError(f"Incident {incident_id} not found")

        # Validate sender is authorized participant
        is_client = sender_id == incident.client_id
        is_workshop_staff = False
        is_technician = sender_id == incident.tecnico_id
        
        # Check if sender is workshop staff (owner or other staff)
        if incident.taller_id:
            workshop_user = await self.session.scalar(
                select(User).where(
                    and_(
                        User.id == sender_id,
                        User.user_type == 'workshop'
                    )
                )
            )
            # For now, allow any workshop user if workshop is assigned
            # TODO: Add more granular permission check
            is_workshop_staff = workshop_user is not None

        if not (is_client or is_workshop_staff or is_technician):
            raise ValidationError(
                "You are not authorized to send messages in this conversation. "
                "Only the client, assigned workshop staff, and assigned technician can participate."
            )

        # Get or create conversation
        conversation = await self.get_or_create_conversation(
            incident_id=incident_id,
            client_id=incident.client_id,
            workshop_id=incident.taller_id
        )

        # Create message
        message = Message(
            incident_id=incident_id,
            sender_id=sender_id,
            message=message_text,
            message_type=message_type,
            is_read=False
        )

        self.session.add(message)

        # Update conversation
        conversation.last_message_at = datetime.utcnow()
        
        # Increment unread count for recipients
        if is_client:
            # Message from client, increment workshop unread count
            conversation.unread_count_workshop += 1
        else:
            # Message from workshop/technician, increment client unread count
            conversation.unread_count_client += 1

        await self.session.commit()
        await self.session.refresh(message)

        # Get sender info for broadcast
        sender = await self.session.scalar(
            select(User).where(User.id == sender_id)
        )

        sender_name = f"{sender.first_name} {sender.last_name}" if sender else "Unknown"

        # Broadcast message via WebSocket
        await manager.send_message_notification(
            incident_id=incident_id,
            sender_id=sender_id,
            sender_name=sender_name,
            message_text=message_text
        )
        
        # 🔔 Emit detailed WebSocket event for real-time chat update
        await self._emit_new_message_event(
            message=message,
            sender_name=sender_name,
            sender_role=sender.user_type if sender else None,
            incident_id=incident_id
        )

        # Send push notification to recipients
        await self._send_chat_push_notification(
            incident=incident,
            sender_id=sender_id,
            sender_name=sender_name,
            message_text=message_text
        )

        logger.info(
            f"Message {message.id} sent in incident {incident_id} by user {sender_id} "
            f"(client={is_client}, workshop={is_workshop_staff}, technician={is_technician})"
        )

        # Return enriched message dict
        return {
            "id": message.id,
            "incident_id": message.incident_id,
            "sender_id": message.sender_id,
            "sender_name": sender_name,
            "sender_role": sender.user_type if sender else None,
            "message": message.message,
            "message_type": message.message_type,
            "is_read": message.is_read,
            "read_at": message.read_at,
            "created_at": message.created_at,
            "updated_at": message.updated_at,
        }

    async def get_messages(
        self,
        incident_id: int,
        limit: int = 50,
        offset: int = 0,
        before_id: Optional[int] = None
    ) -> List[dict]:
        """
        Get messages for an incident, enriched with sender name and role.
        """
        query = (
            select(Message, User)
            .join(User, Message.sender_id == User.id, isouter=True)
            .where(Message.incident_id == incident_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        if before_id:
            query = query.where(Message.id < before_id)

        result = await self.session.execute(query)
        rows = result.all()

        messages = []
        for message, user in rows:
            sender_name = None
            sender_role = None
            if user:
                first = user.first_name or ''
                last = user.last_name or ''
                sender_name = f"{first} {last}".strip() or user.email
                sender_role = user.user_type

            messages.append({
                "id": message.id,
                "incident_id": message.incident_id,
                "sender_id": message.sender_id,
                "sender_name": sender_name,
                "sender_role": sender_role,
                "message": message.message,
                "message_type": message.message_type,
                "is_read": message.is_read,
                "read_at": message.read_at,
                "created_at": message.created_at,
                "updated_at": message.updated_at,
            })

        return messages

    async def mark_messages_as_read(
        self,
        incident_id: int,
        user_id: int
    ) -> int:
        """
        Mark all unread messages as read for a user in an incident.
        
        Args:
            incident_id: ID of the incident
            user_id: ID of the user marking messages as read
            
        Returns:
            Number of messages marked as read
        """
        # Get incident to determine if user is client or workshop
        incident = await self.session.scalar(
            select(Incidente).where(Incidente.id == incident_id)
        )
        
        if not incident:
            raise NotFoundError(f"Incident {incident_id} not found")

        # Mark messages as read (messages sent by others, not by this user)
        result = await self.session.execute(
            update(Message)
            .where(
                and_(
                    Message.incident_id == incident_id,
                    Message.sender_id != user_id,
                    Message.is_read == False
                )
            )
            .values(
                is_read=True,
                read_at=datetime.utcnow()
            )
        )

        # Update conversation unread count
        conversation = await self.session.scalar(
            select(Conversation).where(Conversation.incident_id == incident_id)
        )

        if conversation:
            if user_id == incident.client_id:
                conversation.unread_count_client = 0
            else:
                conversation.unread_count_workshop = 0

        await self.session.commit()

        marked_count = result.rowcount
        logger.info(f"Marked {marked_count} messages as read for user {user_id} in incident {incident_id}")

        # Emit message_read event so senders see read receipts in real-time
        if marked_count > 0:
            await emit_to_incident_room(
                incident_id=incident_id,
                event_type=EventTypes.MESSAGE_READ,
                data={
                    "incident_id": incident_id,
                    "read_by_user_id": user_id,
                    "marked_count": marked_count,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

        return marked_count

    async def get_conversation(self, incident_id: int) -> Optional[Conversation]:
        """
        Get conversation for an incident.
        
        Args:
            incident_id: ID of the incident
            
        Returns:
            Conversation or None if not found
        """
        return await self.session.scalar(
            select(Conversation).where(Conversation.incident_id == incident_id)
        )

    async def get_user_conversations(
        self,
        user_id: int,
        is_client: bool = True,
        limit: int = 20
    ) -> List[Conversation]:
        """
        Get all conversations for a user.
        
        Args:
            user_id: ID of the user
            is_client: Whether the user is a client (True) or workshop staff (False)
            limit: Maximum number of conversations to return
            
        Returns:
            List of conversations ordered by last message time
        """
        if is_client:
            query = (
                select(Conversation)
                .where(Conversation.client_id == user_id)
                .order_by(Conversation.last_message_at.desc().nullslast())
                .limit(limit)
            )
        else:
            # For workshop staff, get conversations where they are assigned
            query = (
                select(Conversation)
                .where(Conversation.workshop_id == user_id)
                .order_by(Conversation.last_message_at.desc().nullslast())
                .limit(limit)
            )

        result = await self.session.scalars(query)
        return list(result.all())

    async def get_unread_count(
        self,
        incident_id: int,
        user_id: int
    ) -> int:
        """
        Get unread message count for a user in an incident.
        
        Args:
            incident_id: ID of the incident
            user_id: ID of the user
            
        Returns:
            Number of unread messages
        """
        # Get incident to determine if user is client or workshop
        incident = await self.session.scalar(
            select(Incidente).where(Incidente.id == incident_id)
        )
        
        if not incident:
            return 0

        conversation = await self.session.scalar(
            select(Conversation).where(Conversation.incident_id == incident_id)
        )

        if not conversation:
            return 0

        if user_id == incident.client_id:
            return conversation.unread_count_client
        else:
            return conversation.unread_count_workshop

    async def delete_message(self, message_id: int, user_id: int) -> bool:
        """
        Delete a message (soft delete by marking as deleted).
        
        Args:
            message_id: ID of the message to delete
            user_id: ID of the user attempting to delete
            
        Returns:
            True if deleted successfully
            
        Raises:
            NotFoundError: If message not found
            ValidationError: If user is not the sender
        """
        message = await self.session.scalar(
            select(Message).where(Message.id == message_id)
        )

        if not message:
            raise NotFoundError(f"Message {message_id} not found")

        if message.sender_id != user_id:
            raise ValidationError("You can only delete your own messages")

        # Soft delete by updating message content
        message.message = "[Mensaje eliminado]"
        message.message_type = "deleted"
        message.updated_at = datetime.utcnow()

        await self.session.commit()

        logger.info(f"Message {message_id} deleted by user {user_id}")
        return True

    async def get_conversation_statistics(
        self,
        incident_id: int
    ) -> dict:
        """
        Get statistics for a conversation.
        
        Args:
            incident_id: ID of the incident
            
        Returns:
            Dictionary with conversation statistics
        """
        # Count total messages
        total_messages = await self.session.scalar(
            select(func.count(Message.id))
            .where(Message.incident_id == incident_id)
        )

        # Count unread messages
        unread_messages = await self.session.scalar(
            select(func.count(Message.id))
            .where(
                and_(
                    Message.incident_id == incident_id,
                    Message.is_read == False
                )
            )
        )

        # Get first and last message times
        first_message = await self.session.scalar(
            select(Message)
            .where(Message.incident_id == incident_id)
            .order_by(Message.created_at.asc())
            .limit(1)
        )

        last_message = await self.session.scalar(
            select(Message)
            .where(Message.incident_id == incident_id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )

        return {
            "total_messages": total_messages or 0,
            "unread_messages": unread_messages or 0,
            "first_message_at": first_message.created_at if first_message else None,
            "last_message_at": last_message.created_at if last_message else None
        }

    async def _send_chat_push_notification(
        self,
        incident: Incidente,
        sender_id: int,
        sender_name: str,
        message_text: str
    ) -> None:
        """
        Send push notification for new chat message.
        
        Args:
            incident: Incident object
            sender_id: ID of message sender
            sender_name: Name of sender
            message_text: Content of message
        """
        try:
            # Determine recipients based on sender
            recipient_ids = []
            
            if sender_id == incident.client_id:
                # Message from client, notify workshop and/or technician
                if incident.tecnico_id:
                    # If technician is assigned, notify the technician
                    recipient_ids.append(incident.tecnico_id)
                if incident.taller_id:
                    # Also notify workshop owner
                    recipient_ids.append(incident.taller_id)
            elif sender_id == incident.tecnico_id:
                # Message from technician, notify BOTH client AND workshop
                recipient_ids.append(incident.client_id)
                if incident.taller_id and incident.taller_id != sender_id:
                    recipient_ids.append(incident.taller_id)
            elif sender_id == incident.taller_id:
                # Message from workshop, notify client and technician
                recipient_ids.append(incident.client_id)
                if incident.tecnico_id:
                    recipient_ids.append(incident.tecnico_id)
            else:
                # Unknown sender, try to notify all parties
                recipient_ids.append(incident.client_id)
                if incident.taller_id and incident.taller_id != sender_id:
                    recipient_ids.append(incident.taller_id)
                if incident.tecnico_id and incident.tecnico_id != sender_id:
                    recipient_ids.append(incident.tecnico_id)

            # Remove duplicates and sender
            recipient_ids = list(set(recipient_ids))
            if sender_id in recipient_ids:
                recipient_ids.remove(sender_id)

            if not recipient_ids:
                logger.warning(f"Could not determine recipients for chat notification in incident {incident.id}")
                return

            # Truncate message for notification
            preview = message_text[:100] + "..." if len(message_text) > 100 else message_text

            # Send push notification
            from ..push_notifications.services import PushNotificationData
            
            notification_data = PushNotificationData(
                title=f"💬 Nuevo mensaje de {sender_name}",
                body=preview,
                data={
                    "type": "chat_message",
                    "incident_id": str(incident.id),
                    "sender_id": str(sender_id),
                    "sender_name": sender_name,
                    "click_action": f"/incidents/{incident.id}/chat"  # For mobile apps
                },
                click_action=None  # Set to None for web push
            )
            
            # Send push notification to all recipients
            for recipient_id in recipient_ids:
                await self.push_service.send_to_user(
                    user_id=recipient_id,
                    notification_data=notification_data,
                    save_to_db=True
                )
                logger.info(f"Push notification sent to user {recipient_id} for chat message in incident {incident.id}")

        except Exception as e:
            # Don't fail message sending if push notification fails
            logger.error(f"Error sending chat push notification: {str(e)}")

    async def _emit_new_message_event(
        self,
        message: Message,
        sender_name: str,
        sender_role: Optional[str],
        incident_id: int
    ) -> None:
        """
        Emit WebSocket event for new chat message.
        This allows real-time chat updates without polling.
        
        Args:
            message: Message object
            sender_name: Name of sender
            sender_role: Role of sender (client, workshop, technician)
            incident_id: ID of the incident
        """
        try:
            # Build event payload
            event_data = {
                "id": message.id,
                "incident_id": message.incident_id,
                "sender_id": message.sender_id,
                "sender_name": sender_name,
                "sender_role": sender_role,
                "message": message.message,
                "message_type": message.message_type,
                "is_read": message.is_read,
                "read_at": message.read_at.isoformat() if message.read_at else None,
                "created_at": message.created_at.isoformat(),
                "updated_at": message.updated_at.isoformat() if message.updated_at else None,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Broadcast to all users in the incident room
            await manager.broadcast_to_incident(
                incident_id=incident_id,
                message={
                    "type": "new_chat_message",
                    "data": event_data
                },
                exclude_user=message.sender_id  # Don't send back to sender
            )
            
            logger.info(
                f"WebSocket event emitted: new message {message.id} in incident {incident_id}"
            )
            
        except Exception as e:
            logger.error(f"Error emitting WebSocket chat message event: {str(e)}", exc_info=True)
            # Don't fail message sending if WebSocket fails

