"""Notification event schemas for real-time notifications."""

from datetime import datetime
from typing import Any, Dict, Optional, Literal

from pydantic import Field

from .base import BaseEvent, EventPriority


class NotificationReceivedEvent(BaseEvent):
    """Event emitted when a user receives a notification."""
    
    event_type: Literal["notification.received"] = "notification.received"
    priority: EventPriority = Field(default=EventPriority.HIGH)
    
    notification_id: int = Field(..., description="ID of the notification")
    user_id: int = Field(..., description="ID of the recipient user")
    notification_type: str = Field(..., description="Type of notification")
    title: str = Field(..., description="Notification title")
    body: str = Field(..., description="Notification body")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional data payload")
    action_url: Optional[str] = Field(None, description="Deep link URL")
    icon: Optional[str] = Field(None, description="Icon URL")


class NotificationReadEvent(BaseEvent):
    """Event emitted when a notification is marked as read."""
    
    event_type: Literal["notification.read"] = "notification.read"
    priority: EventPriority = Field(default=EventPriority.LOW)
    
    notification_id: int = Field(..., description="ID of the notification")
    user_id: int = Field(..., description="ID of the user")
    read_at: datetime = Field(default_factory=datetime.utcnow)


class NotificationBadgeUpdatedEvent(BaseEvent):
    """Event emitted when notification badge count changes."""
    
    event_type: Literal["notification.badge_updated"] = "notification.badge_updated"
    priority: EventPriority = Field(default=EventPriority.MEDIUM)
    
    user_id: int = Field(..., description="ID of the user")
    unread_count: int = Field(..., description="Number of unread notifications")
