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
    incident_id: int = Field(..., description="ID of the incident")
    sender_id: int = Field(..., description="ID of the sender")
    sender_name: str = Field(..., description="Name of the sender")
    sender_role: str = Field(..., description="Role of the sender")
    content: str = Field(..., description="Message content")
    sent_at: datetime = Field(default_factory=datetime.utcnow)


class ChatMessageDeliveredEvent(BaseEvent):
    """Event emitted when a message is delivered to recipient."""
    
    event_type: Literal["chat.message_delivered"] = "chat.message_delivered"
    priority: EventPriority = Field(default=EventPriority.LOW)
    
    message_id: int = Field(..., description="ID of the message")
    delivered_to: int = Field(..., description="User ID who received it")
    delivered_at: datetime = Field(default_factory=datetime.utcnow)


class ChatMessageReadEvent(BaseEvent):
    """Event emitted when a message is read by recipient."""
    
    event_type: Literal["chat.message_read"] = "chat.message_read"
    priority: EventPriority = Field(default=EventPriority.LOW)
    
    message_id: int = Field(..., description="ID of the message")
    read_by: int = Field(..., description="User ID who read it")
    read_at: datetime = Field(default_factory=datetime.utcnow)


class ChatUserTypingEvent(BaseEvent):
    """Event emitted when a user starts typing."""
    
    event_type: Literal["chat.user_typing"] = "chat.user_typing"
    priority: EventPriority = Field(default=EventPriority.LOW)
    
    incident_id: int = Field(..., description="ID of the incident")
    user_id: int = Field(..., description="ID of the user typing")
    user_name: str = Field(..., description="Name of the user")


class ChatUserStoppedTypingEvent(BaseEvent):
    """Event emitted when a user stops typing."""
    
    event_type: Literal["chat.user_stopped_typing"] = "chat.user_stopped_typing"
    priority: EventPriority = Field(default=EventPriority.LOW)
    
    incident_id: int = Field(..., description="ID of the incident")
    user_id: int = Field(..., description="ID of the user")


class ChatFileUploadedEvent(BaseEvent):
    """Event emitted when a file is uploaded to chat."""
    
    event_type: Literal["chat.file_uploaded"] = "chat.file_uploaded"
    priority: EventPriority = Field(default=EventPriority.MEDIUM)
    
    message_id: int = Field(..., description="ID of the message")
    incident_id: int = Field(..., description="ID of the incident")
    file_id: int = Field(..., description="ID of the uploaded file")
    file_name: str = Field(..., description="Name of the file")
    file_type: str = Field(..., description="MIME type of the file")
    file_size: int = Field(..., description="Size in bytes")
    file_url: Optional[str] = Field(None, description="URL to access the file")
