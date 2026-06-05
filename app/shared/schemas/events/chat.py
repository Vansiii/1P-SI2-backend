"""Chat event schemas for real-time messaging."""

from datetime import datetime
from typing import Optional, Literal

from pydantic import Field

from .base import BaseEvent, EventPriority


class ChatMessageSentEvent(BaseEvent):
    """Event emitted when a chat message is sent."""
    
    event_type: Literal["chat.message_sent"] = "chat.message_sent"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    message_id: int = Field(..., description="ID of the message")
    conversation_id: int = Field(..., description="ID of the conversation")
    incident_id: int = Field(..., description="ID of the incident")
    workshop_id: Optional[int] = Field(default=None, description="Assigned workshop for this conversation")
    sender_id: int = Field(..., description="ID of the sender")
    sender_name: str = Field(..., description="Name of the sender")
    sender_role: str = Field(..., description="Role of the sender")
    content: str = Field(..., description="Message content")
    message_type: str = Field(default="text", description="Message type")
    type: str = Field(default="chat_message", description="Notification type alias")
    click_action: Optional[str] = Field(
        default=None,
        description="Client route to open when the notification is tapped",
    )
    sent_at: datetime = Field(default_factory=datetime.utcnow)


class ChatMessageDeliveredEvent(BaseEvent):
    """Event emitted when a message is delivered to recipient."""
    
    event_type: Literal["chat.message_delivered"] = "chat.message_delivered"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    message_id: int = Field(..., description="ID of the message")
    conversation_id: Optional[int] = Field(
        default=None,
        description="ID of the conversation (optional for backward compatibility)"
    )
    incident_id: Optional[int] = Field(
        default=None,
        description="ID of the incident (optional for backward compatibility)"
    )
    sender_id: Optional[int] = Field(
        default=None,
        description="Original sender user ID (receipt target)"
    )
    delivered_to: int = Field(..., description="User ID who received it")
    delivered_at: datetime = Field(default_factory=datetime.utcnow)


class ChatMessageReadEvent(BaseEvent):
    """Event emitted when a message is read by recipient."""
    
    event_type: Literal["chat.message_read"] = "chat.message_read"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    message_id: int = Field(..., description="ID of the message")
    conversation_id: Optional[int] = Field(
        default=None,
        description="ID of the conversation (optional for backward compatibility)"
    )
    incident_id: Optional[int] = Field(
        default=None,
        description="ID of the incident (optional for backward compatibility)"
    )
    sender_id: Optional[int] = Field(
        default=None,
        description="Original sender user ID (receipt target)"
    )
    read_by: int = Field(..., description="User ID who read it")
    read_at: datetime = Field(default_factory=datetime.utcnow)


class ChatUserTypingEvent(BaseEvent):
    """Event emitted when a user starts typing."""
    
    event_type: Literal["chat.user_typing"] = "chat.user_typing"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    incident_id: int = Field(..., description="ID of the incident")
    conversation_id: int = Field(..., description="ID of the active conversation")
    user_id: int = Field(..., description="ID of the user typing")
    user_name: str = Field(..., description="Name of the user")


class ChatUserStoppedTypingEvent(BaseEvent):
    """Event emitted when a user stops typing."""
    
    event_type: Literal["chat.user_stopped_typing"] = "chat.user_stopped_typing"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    incident_id: int = Field(..., description="ID of the incident")
    conversation_id: int = Field(..., description="ID of the active conversation")
    user_id: int = Field(..., description="ID of the user")


class ChatFileUploadedEvent(BaseEvent):
    """Event emitted when a file is uploaded to chat."""
    
    event_type: Literal["chat.file_uploaded"] = "chat.file_uploaded"
    priority: EventPriority = Field(default=EventPriority.MEDIUM)
    
    message_id: int = Field(..., description="ID of the message")
    conversation_id: int = Field(..., description="ID of the conversation")
    incident_id: int = Field(..., description="ID of the incident")
    file_id: int = Field(..., description="ID of the uploaded file")
    file_name: str = Field(..., description="Name of the file")
    file_type: str = Field(..., description="MIME type of the file")
    file_size: int = Field(..., description="Size in bytes")
    file_url: Optional[str] = Field(None, description="URL to access the file")
