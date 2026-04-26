"""
Outbox module for processing events from the outbox pattern.

This module contains the OutboxProcessor that continuously processes
pending events from the outbox_events table and delivers them via
WebSocket and FCM.
"""

from .processor import OutboxProcessor
from .service import OutboxService

__all__ = [
    "OutboxProcessor",
    "OutboxService",
]
