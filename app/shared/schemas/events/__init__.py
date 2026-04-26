"""
Event schemas for real-time communication.

This package contains Pydantic schemas for all events emitted via WebSocket and FCM.
All events inherit from BaseEvent and include validation, versioning, and metadata.
"""

from .base import BaseEvent, EventPriority
from .incident import (
    IncidentCreatedEvent,
    IncidentPhotosUploadedEvent,
    IncidentAssignedEvent,
    IncidentAssignmentAcceptedEvent,
    IncidentAssignmentRejectedEvent,
    IncidentAssignmentTimeoutEvent,
    IncidentStatusChangedEvent,
    IncidentTechnicianOnWayEvent,
    IncidentTechnicianArrivedEvent,
    IncidentWorkStartedEvent,
    IncidentWorkCompletedEvent,
    IncidentCancelledEvent,
    IncidentUpdatedEvent,
    IncidentAnalysisStartedEvent,
    IncidentAnalysisCompletedEvent,
    IncidentAnalysisFailedEvent,
    IncidentAnalysisSlowEvent,
    IncidentAnalysisTimeoutEvent,
)
from .chat import (
    ChatMessageSentEvent,
    ChatMessageDeliveredEvent,
    ChatMessageReadEvent,
    ChatUserTypingEvent,
    ChatUserStoppedTypingEvent,
    ChatFileUploadedEvent,
)
from .tracking import (
    TrackingLocationUpdatedEvent,
    TrackingSessionStartedEvent,
    TrackingSessionEndedEvent,
    TrackingRouteUpdatedEvent,
)
from .notification import (
    NotificationReceivedEvent,
    NotificationReadEvent,
    NotificationBadgeUpdatedEvent,
)
from .dashboard import (
    DashboardMetricsUpdatedEvent,
    DashboardIncidentCountChangedEvent,
    DashboardActiveTechniciansChangedEvent,
    DashboardAlertTriggeredEvent,
)
from .cancellation import (
    CancellationRequestedEvent,
    CancellationApprovedEvent,
    CancellationRejectedEvent,
)
from .audit import (
    AuditCriticalActionEvent,
    AuditSuspiciousActivityEvent,
    AuditSecurityBreachEvent,
)
from .evidence import (
    EvidenceUploadedEvent,
    EvidenceImageUploadedEvent,
    EvidenceAudioUploadedEvent,
    EvidenceDeletedEvent,
)

__all__ = [
    # Base
    "BaseEvent",
    "EventPriority",
    # Incident events
    "IncidentCreatedEvent",
    "IncidentPhotosUploadedEvent",
    "IncidentAssignedEvent",
    "IncidentAssignmentAcceptedEvent",
    "IncidentAssignmentRejectedEvent",
    "IncidentAssignmentTimeoutEvent",
    "IncidentStatusChangedEvent",
    "IncidentTechnicianOnWayEvent",
    "IncidentTechnicianArrivedEvent",
    "IncidentWorkStartedEvent",
    "IncidentWorkCompletedEvent",
    "IncidentCancelledEvent",
    "IncidentUpdatedEvent",
    "IncidentAnalysisStartedEvent",
    "IncidentAnalysisCompletedEvent",
    "IncidentAnalysisFailedEvent",
    "IncidentAnalysisSlowEvent",
    "IncidentAnalysisTimeoutEvent",
    # Chat events
    "ChatMessageSentEvent",
    "ChatMessageDeliveredEvent",
    "ChatMessageReadEvent",
    "ChatUserTypingEvent",
    "ChatUserStoppedTypingEvent",
    "ChatFileUploadedEvent",
    # Tracking events
    "TrackingLocationUpdatedEvent",
    "TrackingSessionStartedEvent",
    "TrackingSessionEndedEvent",
    "TrackingRouteUpdatedEvent",
    # Notification events
    "NotificationReceivedEvent",
    "NotificationReadEvent",
    "NotificationBadgeUpdatedEvent",
    # Dashboard events
    "DashboardMetricsUpdatedEvent",
    "DashboardIncidentCountChangedEvent",
    "DashboardActiveTechniciansChangedEvent",
    "DashboardAlertTriggeredEvent",
    # Cancellation events
    "CancellationRequestedEvent",
    "CancellationApprovedEvent",
    "CancellationRejectedEvent",
    # Audit events
    "AuditCriticalActionEvent",
    "AuditSuspiciousActivityEvent",
    "AuditSecurityBreachEvent",
    # Evidence events
    "EvidenceUploadedEvent",
    "EvidenceImageUploadedEvent",
    "EvidenceAudioUploadedEvent",
    "EvidenceDeletedEvent",
]
