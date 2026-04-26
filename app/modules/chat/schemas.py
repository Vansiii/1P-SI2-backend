"""
Schemas for chat operations.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    """Schema for sending a message."""
    message: str = Field(..., min_length=1, max_length=5000, description="Message content")
    message_type: str = Field("text", description="Type of message: text, image, audio, system")


class MessageResponse(BaseModel):
    """Schema for message response."""
    id: int
    incident_id: int
    sender_id: int
    sender_name: Optional[str] = None
    sender_role: Optional[str] = None
    message: str
    message_type: str
    is_read: bool
    read_at: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class ConversationResponse(BaseModel):
    """Schema for conversation response."""
    id: int
    incident_id: int
    client_id: int
    workshop_id: Optional[int]
    last_message_at: Optional[datetime]
    unread_count_client: int
    unread_count_workshop: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class ConversationWithLastMessage(BaseModel):
    """Schema for conversation with last message."""
    conversation: ConversationResponse
    last_message: Optional[MessageResponse]
    unread_count: int


class MarkAsReadRequest(BaseModel):
    """Schema for marking messages as read."""
    pass  # No additional fields needed, user_id comes from auth


class ConversationStatistics(BaseModel):
    """Schema for conversation statistics."""
    total_messages: int
    unread_messages: int
    first_message_at: Optional[datetime]
    last_message_at: Optional[datetime]


class MessagesListResponse(BaseModel):
    """Schema for paginated messages list."""
    messages: list[MessageResponse]
    total: int
    has_more: bool
