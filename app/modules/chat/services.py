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
from ...core.event_publisher import EventPublisher
from ...shared.schemas.events.chat import (
    ChatMessageSentEvent,
    ChatMessageReadEvent,
    ChatUserTypingEvent,
    ChatUserStoppedTypingEvent,
    ChatFileUploadedEvent
)
from ...models.message import Message
from ...models.conversation import Conversation
from ...models.incidente import Incidente
from ...models.user import User
from ...core.websocket import manager
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
        workshop_id: Optional[int] = None,
        *,
        force_new: bool = False,
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
        if not force_new:
            query = select(Conversation).where(Conversation.incident_id == incident_id)
            if workshop_id is not None:
                query = query.where(Conversation.workshop_id == workshop_id)
            conversation = await self.session.scalar(
                query.order_by(Conversation.created_at.desc(), Conversation.id.desc())
            )

            if conversation:
                return conversation

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

    async def get_active_conversation(
        self,
        incident: Incidente,
        *,
        create_if_missing: bool = False,
    ) -> Optional[Conversation]:
        """Return the active conversation for the incident's current workshop."""
        workshop_id = incident.taller_id
        if not workshop_id:
            return None

        conversation = await self.session.scalar(
            select(Conversation)
            .where(
                Conversation.incident_id == incident.id,
                Conversation.workshop_id == workshop_id,
            )
            .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        )

        if conversation or not create_if_missing:
            return conversation

        return await self.get_or_create_conversation(
            incident_id=incident.id,
            client_id=incident.client_id,
            workshop_id=workshop_id,
        )

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
            is_workshop_staff = (
                workshop_user is not None and incident.taller_id == sender_id
            )

        if not (is_client or is_workshop_staff or is_technician):
            raise ValidationError(
                "You are not authorized to send messages in this conversation. "
                "Only the client, assigned workshop staff, and assigned technician can participate."
            )

        # Get or create conversation
        conversation = await self.get_active_conversation(
            incident,
            create_if_missing=True,
        )
        if not conversation:
            raise ValidationError("No hay una conversación activa para este incidente")

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

        await self.session.flush()  # Flush to get message.id
        await self.session.refresh(message)

        sender = await self.session.scalar(
            select(User).where(User.id == sender_id)
        )
        sender_name = f"{sender.first_name} {sender.last_name}" if sender else "Unknown"
        sender_role = sender.user_type if sender else None

        chat_event = ChatMessageSentEvent(
            message_id=message.id,
            conversation_id=conversation.id,
            incident_id=incident_id,
            workshop_id=conversation.workshop_id,
            sender_id=sender_id,
            sender_name=sender_name,
            sender_role=sender_role or "system",
            content=message_text,
            message_type=message.message_type,
            click_action=f"/incidents/{incident_id}/chat",
        )
        await EventPublisher.publish(self.session, chat_event)

        await self.session.commit()

        # WebSocket delivery handled by OutboxProcessor (polls every 1s)
        # OUTBOX handles: WS delivery + FCM fallback + event_log tracking
        # Removed legacy manager.send_message_notification() to eliminate double-delivery

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
            "conversation_id": conversation.id,
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
        incident = await self.session.scalar(
            select(Incidente).where(Incidente.id == incident_id)
        )
        if not incident:
            raise NotFoundError(f"Incident {incident_id} not found")

        conversation = await self.get_active_conversation(incident)
        if not conversation:
            return []

        query = (
            select(Message, User)
            .join(User, Message.sender_id == User.id, isouter=True)
            .where(
                Message.incident_id == incident_id,
                Message.created_at >= conversation.created_at,
            )
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
                "conversation_id": conversation.id,
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

        conversation = await self.get_active_conversation(incident)
        if not conversation:
            return 0

        # Get unread messages before marking them as read (to publish events)
        unread_messages = await self.session.scalars(
            select(Message)
            .where(
                and_(
                    Message.incident_id == incident_id,
                    Message.created_at >= conversation.created_at,
                    Message.sender_id != user_id,
                    Message.is_read == False
                )
            )
        )
        unread_message_list = list(unread_messages.all())

        # Mark messages as read (messages sent by others, not by this user)
        read_at_time = datetime.utcnow()
        result = await self.session.execute(
            update(Message)
            .where(
                and_(
                    Message.incident_id == incident_id,
                    Message.created_at >= conversation.created_at,
                    Message.sender_id != user_id,
                    Message.is_read == False
                )
            )
            .values(
                is_read=True,
                read_at=read_at_time
            )
        )

        # Update conversation unread count
        if conversation:
            if user_id == incident.client_id:
                conversation.unread_count_client = 0
            else:
                conversation.unread_count_workshop = 0

        await self.session.commit()

        marked_count = result.rowcount
        logger.info(f"Marked {marked_count} messages as read for user {user_id} in incident {incident_id}")

        # Publish ChatMessageReadEvent for each message marked as read
        # This allows proper notification to senders
        if marked_count > 0:
            for message in unread_message_list:
                try:
                    read_event = ChatMessageReadEvent(
                        message_id=message.id,
                        conversation_id=conversation.id,
                        incident_id=incident_id,
                        sender_id=message.sender_id,
                        read_by=user_id,
                        read_at=read_at_time
                    )
                    await EventPublisher.publish(
                        self.session,
                        read_event,
                        send_immediate=True
                    )
                except Exception as e:
                    logger.error(f"Error publishing read event for message {message.id}: {str(e)}")
            
            await self.session.commit()

        return marked_count

    async def get_conversation(self, incident_id: int) -> Optional[Conversation]:
        """
        Get conversation for an incident.
        
        Args:
            incident_id: ID of the incident
            
        Returns:
            Conversation or None if not found
        """
        incident = await self.session.scalar(
            select(Incidente).where(Incidente.id == incident_id)
        )
        if not incident:
            return None
        return await self.get_active_conversation(incident)

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
        latest_conversation_ids = (
            select(func.max(Conversation.id).label("conversation_id"))
            .join(Incidente, Incidente.id == Conversation.incident_id)
        )

        if is_client:
            latest_conversation_ids = latest_conversation_ids.where(
                Conversation.client_id == user_id,
                Conversation.workshop_id == Incidente.taller_id,
            )
        else:
            latest_conversation_ids = latest_conversation_ids.where(
                Conversation.workshop_id == user_id,
                Incidente.taller_id == user_id,
            )

        latest_conversation_ids = latest_conversation_ids.group_by(
            Conversation.incident_id,
            Conversation.workshop_id,
        ).subquery()

        query = (
            select(Conversation)
            .join(
                latest_conversation_ids,
                Conversation.id == latest_conversation_ids.c.conversation_id,
            )
            .order_by(Conversation.last_message_at.desc().nullslast(), Conversation.id.desc())
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

        conversation = await self.get_active_conversation(incident)

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
        incident = await self.session.scalar(
            select(Incidente).where(Incidente.id == incident_id)
        )
        if not incident:
            return {
                "total_messages": 0,
                "unread_messages": 0,
                "first_message_at": None,
                "last_message_at": None
            }

        conversation = await self.get_active_conversation(incident)
        if not conversation:
            return {
                "total_messages": 0,
                "unread_messages": 0,
                "first_message_at": None,
                "last_message_at": None
            }

        total_messages = await self.session.scalar(
            select(func.count(Message.id))
            .where(
                Message.incident_id == incident_id,
                Message.created_at >= conversation.created_at,
            )
        )

        # Count unread messages
        unread_messages = await self.session.scalar(
            select(func.count(Message.id))
            .where(
                and_(
                    Message.incident_id == incident_id,
                    Message.created_at >= conversation.created_at,
                    Message.is_read == False
                )
            )
        )

        # Get first and last message times
        first_message = await self.session.scalar(
            select(Message)
            .where(
                Message.incident_id == incident_id,
                Message.created_at >= conversation.created_at,
            )
            .order_by(Message.created_at.asc())
            .limit(1)
        )

        last_message = await self.session.scalar(
            select(Message)
            .where(
                Message.incident_id == incident_id,
                Message.created_at >= conversation.created_at,
            )
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
            
            # ═══════════════════════════════════════════════════════════════════════
            # ✅ NOTIFICACIONES MANEJADAS POR OUTBOX PROCESSOR
            # El OutboxProcessor maneja todas las notificaciones de chat automáticamente
            # via EventPublisher → OutboxEvent → Delivery Strategies
            # NO enviar notificaciones duplicadas aquí
            # ═══════════════════════════════════════════════════════════════════════

        except Exception as e:
            # Don't fail message sending if push notification fails
            logger.error(f"Error in chat notification setup: {str(e)}")



    async def notify_user_typing(
        self,
        incident_id: int,
        user_id: int
    ) -> None:
        """
        Notify that a user is typing in a conversation.
        
        This is an ephemeral event (not persisted to DB).
        
        Args:
            incident_id: ID of the incident
            user_id: ID of the user who is typing
        """
        # Get user info
        user = await self.session.scalar(
            select(User).where(User.id == user_id)
        )
        
        if not user:
            raise NotFoundError(f"User {user_id} not found")

        incident = await self.session.scalar(
            select(Incidente).where(Incidente.id == incident_id)
        )
        if not incident:
            raise NotFoundError(f"Incident {incident_id} not found")

        conversation = await self.get_active_conversation(incident)
        if not conversation:
            raise ValidationError("No hay una conversación activa para este incidente")
        
        user_name = f"{user.first_name} {user.last_name}" if user.first_name else user.email
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ PUBLICAR EVENTO DE USUARIO ESCRIBIENDO (EFÍMERO - NO PERSISTE EN DB)
        # ═══════════════════════════════════════════════════════════════════════
        try:
            typing_event = ChatUserTypingEvent(
                incident_id=incident_id,
                conversation_id=conversation.id,
                user_id=user_id,
                user_name=user_name
            )
            
            # Publicar evento sin persistir en outbox (send_immediate=True, pero no commit)
            # Este evento es efímero y solo se envía via WebSocket
            await EventPublisher.publish(
                self.session,
                typing_event,
                commit=False,  # No persistir en DB
                send_immediate=True  # Solo WebSocket inmediato
            )
            
            logger.debug(
                f"User {user_id} is typing in incident {incident_id}",
                user_id=user_id,
                incident_id=incident_id
            )
            
        except Exception as e:
            logger.error(
                f"❌ Error publicando evento USER_TYPING: {str(e)}",
                exc_info=True
            )
        # ═══════════════════════════════════════════════════════════════════════

    async def notify_user_stopped_typing(
        self,
        incident_id: int,
        user_id: int
    ) -> None:
        """
        Notify that a user stopped typing in a conversation.
        
        This is an ephemeral event (not persisted to DB).
        
        Args:
            incident_id: ID of the incident
            user_id: ID of the user who stopped typing
        """
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ PUBLICAR EVENTO DE USUARIO DEJÓ DE ESCRIBIR (EFÍMERO - NO PERSISTE EN DB)
        # ═══════════════════════════════════════════════════════════════════════
        incident = await self.session.scalar(
            select(Incidente).where(Incidente.id == incident_id)
        )
        if not incident:
            raise NotFoundError(f"Incident {incident_id} not found")

        conversation = await self.get_active_conversation(incident)
        if not conversation:
            raise ValidationError("No hay una conversación activa para este incidente")

        try:
            stopped_typing_event = ChatUserStoppedTypingEvent(
                incident_id=incident_id,
                conversation_id=conversation.id,
                user_id=user_id
            )
            
            # Publicar evento sin persistir en outbox (send_immediate=True, pero no commit)
            # Este evento es efímero y solo se envía via WebSocket
            await EventPublisher.publish(
                self.session,
                stopped_typing_event,
                commit=False,  # No persistir en DB
                send_immediate=True  # Solo WebSocket inmediato
            )
            
            logger.debug(
                f"User {user_id} stopped typing in incident {incident_id}",
                user_id=user_id,
                incident_id=incident_id
            )
            
        except Exception as e:
            logger.error(
                f"❌ Error publicando evento USER_STOPPED_TYPING: {str(e)}",
                exc_info=True
            )
        # ═══════════════════════════════════════════════════════════════════════

    async def upload_file_to_chat(
        self,
        incident_id: int,
        sender_id: int,
        file_id: int,
        file_name: str,
        file_type: str,
        file_size: int,
        file_url: str
    ) -> Message:
        """
        Upload a file to a chat conversation.
        
        Args:
            incident_id: ID of the incident
            sender_id: ID of the user uploading the file
            file_id: ID of the uploaded file
            file_name: Name of the file
            file_type: MIME type of the file
            file_size: Size of the file in bytes
            file_url: URL to access the file
            
        Returns:
            Created message with file attachment
        """
        # Create message with file attachment
        message_text = f"📎 {file_name}"
        message = await self.send_message(
            incident_id=incident_id,
            sender_id=sender_id,
            message_text=message_text,
            message_type="file"
        )
        
        # ═══════════════════════════════════════════════════════════════════════
        # ✅ PUBLICAR EVENTO DE ARCHIVO SUBIDO
        # ═══════════════════════════════════════════════════════════════════════
        try:
            file_uploaded_event = ChatFileUploadedEvent(
                message_id=message["id"],
                conversation_id=message["conversation_id"],
                incident_id=incident_id,
                file_id=file_id,
                file_name=file_name,
                file_type=file_type,
                file_size=file_size,
                file_url=file_url
            )
            
            await EventPublisher.publish(self.session, file_uploaded_event)
            await self.session.commit()
            
            logger.info(
                f"✅ Evento FILE_UPLOADED publicado para incidente {incident_id}",
                file_name=file_name,
                file_size=file_size
            )
            
        except Exception as e:
            logger.error(
                f"❌ Error publicando evento FILE_UPLOADED: {str(e)}",
                exc_info=True
            )
        # ═══════════════════════════════════════════════════════════════════════
        
        return message

    async def mark_message_as_read(
        self,
        message_id: int,
        user_id: int
    ) -> Message:
        """
        Mark a specific message as read.
        
        Args:
            message_id: ID of the message
            user_id: ID of the user marking the message as read
            
        Returns:
            Updated message
            
        Raises:
            NotFoundError: If message not found
        """
        message = await self.session.scalar(
            select(Message).where(Message.id == message_id)
        )
        
        if not message:
            raise NotFoundError(f"Message {message_id} not found")
        
        # Don't mark own messages as read
        if message.sender_id == user_id:
            return message
        
        # Mark as read if not already
        if not message.is_read:
            message.is_read = True
            message.read_at = datetime.utcnow()

            incident = await self.session.scalar(
                select(Incidente).where(Incidente.id == message.incident_id)
            )
            conversation = await self.get_active_conversation(incident) if incident else None
            
            await self.session.commit()
            await self.session.refresh(message)
            
            # ═══════════════════════════════════════════════════════════════════════
            # ✅ PUBLICAR EVENTO DE MENSAJE LEÍDO
            # ═══════════════════════════════════════════════════════════════════════
            try:
                message_read_event = ChatMessageReadEvent(
                    message_id=message_id,
                    conversation_id=conversation.id if conversation else None,
                    incident_id=message.incident_id,
                    sender_id=message.sender_id,
                    read_by=user_id,
                    read_at=message.read_at
                )
                
                await EventPublisher.publish(
                    self.session,
                    message_read_event,
                    send_immediate=True
                )
                await self.session.commit()
                
                logger.info(
                    f"✅ Evento MESSAGE_READ publicado para mensaje {message_id}",
                    message_id=message_id,
                    read_by=user_id
                )
                
            except Exception as e:
                logger.error(
                    f"❌ Error publicando evento MESSAGE_READ: {str(e)}",
                    exc_info=True
                )
            # ═══════════════════════════════════════════════════════════════════════
        
        return message
