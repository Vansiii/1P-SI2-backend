"""
WebSocket Event Emission Helpers

Standardized utilities for emitting WebSocket events across all modules.
Provides consistent payload structure and error handling.
"""
from datetime import datetime
from typing import Dict, Any, Optional, List
from .websocket import manager as ws_manager
from .logging import get_logger

logger = get_logger(__name__)

# Event version for future compatibility
EVENT_VERSION = "1.0"


def _build_event_payload(event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build standardized event payload structure.
    
    Args:
        event_type: Type of event (e.g., 'incident_created', 'technician_assigned')
        data: Event-specific data
        
    Returns:
        Standardized payload with type, data, timestamp, and version
    """
    return {
        "type": event_type,
        "data": data,
        "timestamp": datetime.utcnow().isoformat(),
        "version": EVENT_VERSION
    }


async def emit_to_user(
    user_id: int,
    event_type: str,
    data: Dict[str, Any]
) -> bool:
    """
    Emit WebSocket event to a specific user.
    
    Args:
        user_id: ID of the user to send the event to
        event_type: Type of event (e.g., 'vehicle_created')
        data: Event-specific data
        
    Returns:
        True if emission succeeded, False otherwise
        
    Example:
        await emit_to_user(
            user_id=50,
            event_type="vehicle_created",
            data={
                "vehicle_id": 123,
                "marca": "Toyota",
                "modelo": "Corolla"
            }
        )
    """
    try:
        payload = _build_event_payload(event_type, data)
        await ws_manager.send_personal_message(user_id, payload)
        logger.debug(f"WebSocket event '{event_type}' sent to user {user_id}")
        return True
    except Exception as e:
        logger.error(
            f"Failed to emit WebSocket event '{event_type}' to user {user_id}: {str(e)}",
            exc_info=True
        )
        return False


async def emit_to_incident_room(
    incident_id: int,
    event_type: str,
    data: Dict[str, Any],
    exclude_user: Optional[int] = None
) -> bool:
    """
    Emit WebSocket event to all users in an incident room.
    
    Args:
        incident_id: ID of the incident room
        event_type: Type of event (e.g., 'new_chat_message', 'location_update')
        data: Event-specific data
        exclude_user: Optional user ID to exclude from broadcast (e.g., message sender)
        
    Returns:
        True if emission succeeded, False otherwise
        
    Example:
        await emit_to_incident_room(
            incident_id=40,
            event_type="evidence_uploaded",
            data={
                "evidence_id": 789,
                "evidence_type": "image",
                "file_url": "https://..."
            }
        )
    """
    try:
        payload = _build_event_payload(event_type, data)
        await ws_manager.broadcast_to_incident(incident_id, payload, exclude_user)
        logger.debug(
            f"WebSocket event '{event_type}' broadcast to incident {incident_id} "
            f"(excluded user: {exclude_user})"
        )
        return True
    except Exception as e:
        logger.error(
            f"Failed to emit WebSocket event '{event_type}' to incident {incident_id}: {str(e)}",
            exc_info=True
        )
        return False


async def emit_to_admins(
    event_type: str,
    data: Dict[str, Any]
) -> bool:
    """
    Emit WebSocket event to all connected administrators.
    
    Args:
        event_type: Type of event (e.g., 'audit_log_created', 'workshop_verified')
        data: Event-specific data
        
    Returns:
        True if emission succeeded, False otherwise
        
    Example:
        await emit_to_admins(
            event_type="audit_log_created",
            data={
                "log_id": 456,
                "action": "user_login",
                "user_id": 50
            }
        )
    """
    try:
        payload = _build_event_payload(event_type, data)
        await ws_manager.broadcast_to_admins(payload)
        logger.debug(f"WebSocket event '{event_type}' broadcast to all admins")
        return True
    except Exception as e:
        logger.error(
            f"Failed to emit WebSocket event '{event_type}' to admins: {str(e)}",
            exc_info=True
        )
        return False


async def emit_to_all(
    event_type: str,
    data: Dict[str, Any]
) -> bool:
    """
    Emit WebSocket event to all connected users (global broadcast).
    Use sparingly - only for system-wide announcements.
    
    Args:
        event_type: Type of event (e.g., 'system_maintenance', 'emergency_alert')
        data: Event-specific data
        
    Returns:
        True if emission succeeded, False otherwise
        
    Example:
        await emit_to_all(
            event_type="system_maintenance",
            data={
                "message": "System will be down for maintenance in 10 minutes",
                "scheduled_at": "2026-04-20T22:00:00Z"
            }
        )
    """
    try:
        payload = _build_event_payload(event_type, data)
        await ws_manager.broadcast_to_all(payload)
        logger.info(f"WebSocket event '{event_type}' broadcast to all users")
        return True
    except Exception as e:
        logger.error(
            f"Failed to emit WebSocket event '{event_type}' to all users: {str(e)}",
            exc_info=True
        )
        return False


async def emit_to_users(
    user_ids: List[int],
    event_type: str,
    data: Dict[str, Any]
) -> Dict[int, bool]:
    """
    Emit WebSocket event to multiple specific users.
    
    Args:
        user_ids: List of user IDs to send the event to
        event_type: Type of event
        data: Event-specific data
        
    Returns:
        Dictionary mapping user_id to success status
        
    Example:
        results = await emit_to_users(
            user_ids=[50, 51, 52],
            event_type="notification_created",
            data={"notification_id": 123, "title": "New message"}
        )
    """
    results = {}
    payload = _build_event_payload(event_type, data)
    
    for user_id in user_ids:
        try:
            await ws_manager.send_personal_message(user_id, payload)
            results[user_id] = True
            logger.debug(f"WebSocket event '{event_type}' sent to user {user_id}")
        except Exception as e:
            results[user_id] = False
            logger.error(
                f"Failed to emit WebSocket event '{event_type}' to user {user_id}: {str(e)}"
            )
    
    return results


# Event type constants for consistency
class EventTypes:
    """Standard event type names following the {entity}_{action} convention."""
    
    # Incident events
    INCIDENT_CREATED = "incident_created"
    INCIDENT_ASSIGNED = "incident_assigned"
    INCIDENT_UPDATED = "incident_updated"
    INCIDENT_STATUS_CHANGED = "incident_status_changed"
    INCIDENT_RESOLVED = "incident_resolved"
    INCIDENT_CANCELLED = "incident_cancelled"
    
    # Technician events
    TECHNICIAN_ASSIGNED = "technician_assigned"
    TECHNICIAN_ARRIVED = "technician_arrived"
    TECHNICIAN_AVAILABILITY_CHANGED = "technician_availability_changed"
    TECHNICIAN_DUTY_STARTED = "technician_duty_started"
    TECHNICIAN_DUTY_ENDED = "technician_duty_ended"
    TECHNICIAN_UPDATED = "technician_updated"
    
    # Location tracking events
    LOCATION_UPDATE = "location_update"
    TRACKING_STARTED = "tracking_started"
    TRACKING_ENDED = "tracking_ended"
    
    # Workshop events
    WORKSHOP_CREATED = "workshop_created"
    WORKSHOP_AVAILABILITY_CHANGED = "workshop_availability_changed"
    WORKSHOP_VERIFIED = "workshop_verified"
    WORKSHOP_UPDATED = "workshop_updated"
    WORKSHOP_DEACTIVATED = "workshop_deactivated"
    WORKSHOP_BALANCE_UPDATED = "workshop_balance_updated"
    
    # Vehicle events
    VEHICLE_CREATED = "vehicle_created"
    VEHICLE_UPDATED = "vehicle_updated"
    VEHICLE_DELETED = "vehicle_deleted"
    VEHICLE_IMAGE_UPLOADED = "vehicle_image_uploaded"
    
    # Evidence events
    EVIDENCE_UPLOADED = "evidence_uploaded"
    EVIDENCE_IMAGE_UPLOADED = "evidence_image_uploaded"
    EVIDENCE_AUDIO_UPLOADED = "evidence_audio_uploaded"
    EVIDENCE_DELETED = "evidence_deleted"
    
    # Notification events
    NOTIFICATION_CREATED = "notification_created"
    NOTIFICATION_READ = "notification_read"
    NOTIFICATIONS_ALL_READ = "notifications_all_read"
    
    # Chat events
    NEW_CHAT_MESSAGE = "new_chat_message"
    USER_TYPING = "user_typing"
    USER_STOPPED_TYPING = "user_stopped_typing"
    MESSAGE_READ = "message_read"
    MESSAGES_ALL_READ = "messages_all_read"
    
    # Assignment events
    ASSIGNMENT_ATTEMPT_CREATED = "assignment_attempt_created"
    ASSIGNMENT_ACCEPTED = "assignment_accepted"
    ASSIGNMENT_REJECTED = "assignment_rejected"
    ASSIGNMENT_TIMEOUT = "assignment_timeout"
    
    # Service events
    SERVICE_STARTED = "service_started"
    SERVICE_PROGRESS_UPDATED = "service_progress_updated"
    SERVICE_COMPLETED = "service_completed"
    SERVICE_PAUSED = "service_paused"
    SERVICE_RESUMED = "service_resumed"
    
    # Audit events
    AUDIT_LOG_CREATED = "audit_log_created"
    
    # User events
    USER_PROFILE_UPDATED = "user_profile_updated"
    USER_PASSWORD_CHANGED = "user_password_changed"
    USER_DEACTIVATED = "user_deactivated"
    USER_ROLE_CHANGED = "user_role_changed"
    TWO_FA_ENABLED = "2fa_enabled"
    
    # System events
    SYSTEM_MAINTENANCE = "system_maintenance"
    EMERGENCY_ALERT = "emergency_alert"
