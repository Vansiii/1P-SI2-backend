"""
WebSocket Event Emission Helpers

Standardized utilities for emitting WebSocket events across all modules.
Provides consistent payload structure with event_id for deduplication.
"""
from datetime import datetime, timezone
from uuid import uuid4
from typing import Dict, Any, Optional, List
from .websocket import manager as ws_manager
from .logging import get_logger

logger = get_logger(__name__)

EVENT_VERSION = "1.0"


def _build_event_payload(
    event_type: str,
    data: Dict[str, Any],
    *,
    event_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Build standardized event payload structure.

    All events MUST follow this structure for client-side deduplication.

    Args:
        event_type: Type of event (e.g., 'incident.created')
        data: Event-specific data
        event_id: Optional pre-defined event ID (used for outbox dedup consistency).
                  When omitted, a new UUID4 is generated.

    Returns:
        Standardized payload with event_type, event_id, payload, timestamp, and version
    """
    return {
        "event_type": event_type,
        "event_id": str(event_id) if event_id else str(uuid4()),
        "payload": data,
        "priority": data.get("priority", "medium"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
    
    Each recipient gets a unique event_id to prevent global dedup from
    silently dropping events for all but the first recipient.
    
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
    
    for user_id in user_ids:
        try:
            # Generate unique event_id per recipient so per-user dedup works correctly
            payload = _build_event_payload(event_type, data)
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
# STANDARD: dot notation (e.g. "incident.created")
# LEGACY: underscore notation kept for backward compatibility
class EventTypes:
    """Standard event type names following the dot-notation convention."""
    
    # ── Incident events ─────────────────────────────────────────────────────
    INCIDENT_CREATED = "incident.created"
    INCIDENT_ASSIGNED = "incident.assigned"
    INCIDENT_UPDATED = "incident.updated"
    INCIDENT_STATUS_CHANGED = "incident.status_changed"
    INCIDENT_RESOLVED = "incident.resolved"
    INCIDENT_CANCELLED = "incident.cancelled"
    INCIDENT_REASSIGNED = "incident.reassigned"
    INCIDENT_PHOTOS_UPLOADED = "incident.photos_uploaded"
    INCIDENT_NO_WORKSHOP_AVAILABLE = "incident.no_workshop_available"
    INCIDENT_SEARCHING_WORKSHOP = "incident.searching_workshop"
    
    # ── Assignment events ───────────────────────────────────────────────────
    INCIDENT_ASSIGNMENT_ACCEPTED = "incident.assignment_accepted"
    INCIDENT_ASSIGNMENT_REJECTED = "incident.assignment_rejected"
    INCIDENT_ASSIGNMENT_TIMEOUT = "incident.assignment_timeout"
    INCIDENT_REASSIGNMENT_STARTED = "incident.reassignment_started"
    ASSIGNMENT_ATTEMPT_CREATED = "assignment.attempt_created"
    
    # ── Technician / Tracking events ────────────────────────────────────────
    INCIDENT_TECHNICIAN_ON_WAY = "incident.technician_on_way"
    INCIDENT_TECHNICIAN_ARRIVED = "incident.technician_arrived"
    INCIDENT_WORK_STARTED = "incident.work_started"
    INCIDENT_WORK_COMPLETED = "incident.work_completed"
    TECHNICIAN_ONLINE_STATUS_CHANGED = "technician.online_status_changed"
    TECHNICIAN_STATUS_UPDATED = "technician.status_updated"
    TECHNICIAN_AVAILABILITY_CHANGED = "technician.availability_changed"
    TECHNICIAN_LOCATION_UPDATED = "technician.location_updated"
    
    # ── Tracking events ─────────────────────────────────────────────────────
    TRACKING_LOCATION_UPDATED = "tracking.location_updated"
    TRACKING_SESSION_STARTED = "tracking.session_started"
    TRACKING_SESSION_ENDED = "tracking.session_ended"
    TRACKING_ROUTE_UPDATED = "tracking.route_updated"
    TRACKING_PAUSED = "tracking.paused"
    TRACKING_RESUMED = "tracking.resumed"
    
    # ── Chat events ─────────────────────────────────────────────────────────
    CHAT_MESSAGE_SENT = "chat.message_sent"
    CHAT_MESSAGE_DELIVERED = "chat.message_delivered"
    CHAT_MESSAGE_READ = "chat.message_read"
    CHAT_USER_TYPING = "chat.user_typing"
    CHAT_USER_STOPPED_TYPING = "chat.user_stopped_typing"
    CHAT_FILE_UPLOADED = "chat.file_uploaded"
    CONVERSATION_UPDATED = "conversation.updated"
    UNREAD_COUNT_UPDATED = "unread.count_updated"
    
    # ── Notification events ─────────────────────────────────────────────────
    NOTIFICATION_RECEIVED = "notification.received"
    NOTIFICATION_READ = "notification.read"
    NOTIFICATION_BADGE_UPDATED = "notification.badge_updated"
    
    # ── Evidence events ─────────────────────────────────────────────────────
    EVIDENCE_IMAGE_UPLOADED = "evidence.image_uploaded"
    EVIDENCE_AUDIO_UPLOADED = "evidence.audio_uploaded"
    EVIDENCE_DELETED = "evidence.deleted"
    
    # ── Cancellation events ─────────────────────────────────────────────────
    CANCELLATION_REQUESTED = "cancellation.requested"
    CANCELLATION_APPROVED = "cancellation.approved"
    CANCELLATION_REJECTED = "cancellation.rejected"
    
    # ── Dashboard / Admin events ────────────────────────────────────────────
    DASHBOARD_METRICS_UPDATED = "dashboard.metrics_updated"
    DASHBOARD_INCIDENT_COUNT_CHANGED = "dashboard.incident_count_changed"
    DASHBOARD_ACTIVE_TECHNICIANS_CHANGED = "dashboard.active_technicians_changed"
    DASHBOARD_ALERT_TRIGGERED = "dashboard.alert_triggered"
    SYSTEM_ALERT_CREATED = "system.alert_created"
    INCIDENT_MONITORING_UPDATED = "incident.monitoring_updated"
    
    # ── Workshop events ─────────────────────────────────────────────────────
    WORKSHOP_AVAILABILITY_CHANGED = "workshop.availability_changed"
    WORKSHOP_VERIFIED = "workshop.verified"
    WORKSHOP_UPDATED = "workshop.updated"
    WORKSHOP_BALANCE_UPDATED = "workshop.balance_updated"
    WORKSHOP_REQUEST_RECEIVED = "workshop.request_received"
    
    # ── Vehicle events ──────────────────────────────────────────────────────
    VEHICLE_CREATED = "vehicle.created"
    VEHICLE_UPDATED = "vehicle.updated"
    VEHICLE_DELETED = "vehicle.deleted"
    VEHICLE_IMAGE_UPLOADED = "vehicle.image_uploaded"
    
    # ── Service events ──────────────────────────────────────────────────────
    SERVICE_STARTED = "service.started"
    SERVICE_PROGRESS_UPDATED = "service.progress_updated"
    SERVICE_COMPLETED = "service.completed"
    SERVICE_PAUSED = "service.paused"
    SERVICE_RESUMED = "service.resumed"

    # ── Cotizacion events (CU32) ────────────────────────────────────────────
    COTIZACION_SOLICITADA = "cotizacion.solicitada"
    COTIZACION_IA_COMPLETADA = "cotizacion.ia_completada"
    COTIZACION_RESPUESTA_RECIBIDA = "cotizacion.respuesta_recibida"
    COTIZACION_TALLER_SELECCIONADO = "cotizacion.taller_seleccionado"
    COTIZACION_TALLER_RECHAZADO = "cotizacion.taller_rechazado"
    COTIZACION_PAGO_INICIADO = "cotizacion.pago_iniciado"
    COTIZACION_PAGO_CONFIRMADO = "cotizacion.pago_confirmado"
    COTIZACION_CANCELADA = "cotizacion.cancelada"
    COTIZACION_COMPLETADA = "cotizacion.completada"
    
    # ── AI Analysis events ──────────────────────────────────────────────────
    INCIDENT_ANALYSIS_STARTED = "incident.analysis_started"
    INCIDENT_ANALYSIS_COMPLETED = "incident.analysis_completed"
    INCIDENT_ANALYSIS_FAILED = "incident.analysis_failed"
    INCIDENT_AI_PROCESSING = "incident.ai_processing"
    INCIDENT_AI_COMPLETED = "incident.ai_completed"
    INCIDENT_MARKED_AMBIGUOUS = "incident.marked_ambiguous"
    
    # ── Push / FCM events ───────────────────────────────────────────────────
    PUSH_SENT = "push.sent"
    PUSH_FAILED = "push.failed"
    
    # ── Audit events ────────────────────────────────────────────────────────
    AUDIT_LOG_CREATED = "audit.log_created"
    
    # ── User events ─────────────────────────────────────────────────────────
    USER_PROFILE_UPDATED = "user.profile_updated"
    USER_PASSWORD_CHANGED = "user.password_changed"
    USER_DEACTIVATED = "user.deactivated"
    USER_ROLE_CHANGED = "user.role_changed"
    TWO_FA_ENABLED = "2fa.enabled"
    
    # ── System events ───────────────────────────────────────────────────────
    SYSTEM_MAINTENANCE = "system.maintenance"
    EMERGENCY_ALERT = "emergency.alert"
    
    # ── Backward-compatible aliases (old underscore notation) ──────────────
    # These point to the new dot-notation values so existing callers don't break.
    # During migration, these should be gradually phased out.
    USER_TYPING = "chat.user_typing"
    USER_STOPPED_TYPING = "chat.user_stopped_typing"
    NEW_CHAT_MESSAGE = "chat.message_sent"
    MESSAGE_READ = "chat.message_read"
    MESSAGES_ALL_READ = "unread.count_updated"
    LOCATION_UPDATE = "tracking.location_updated"
    TRACKING_STARTED = "tracking.session_started"
    TRACKING_ENDED = "tracking.session_ended"
    NOTIFICATION_CREATED = "notification.received"
    NOTIFICATION_READ = "notification.read"
    NOTIFICATIONS_ALL_READ = "notification.badge_updated"
    NO_WORKSHOP_AVAILABLE = "incident.no_workshop_available"
    SERVICE_STARTED = "service.started"
    SERVICE_PROGRESS_UPDATED = "service.progress_updated"
    SERVICE_COMPLETED = "service.completed"
    SERVICE_PAUSED = "service.paused"
    SERVICE_RESUMED = "service.resumed"
    TECHNICIAN_ASSIGNED = "incident.technician_on_way"
    TECHNICIAN_ARRIVED = "incident.technician_arrived"
    TECHNICIAN_AVAILABILITY_CHANGED = "technician.availability_changed"
    TECHNICIAN_DUTY_STARTED = "tracking.session_started"
    TECHNICIAN_DUTY_ENDED = "tracking.session_ended"
    TECHNICIAN_UPDATED = "technician.status_updated"
    WORKSHOP_CREATED = "workshop.updated"
    WORKSHOP_VERIFIED = "workshop.verified"
    WORKSHOP_UPDATED = "workshop.updated"
    WORKSHOP_DEACTIVATED = "workshop.updated"
    WORKSHOP_BALANCE_UPDATED = "workshop.balance_updated"
    VEHICLE_CREATED = "vehicle.created"
    VEHICLE_UPDATED = "vehicle.updated"
    VEHICLE_DELETED = "vehicle.deleted"
    VEHICLE_IMAGE_UPLOADED = "vehicle.image_uploaded"
    EVIDENCE_UPLOADED = "evidence.image_uploaded"
    EVIDENCE_IMAGE_UPLOADED = "evidence.image_uploaded"
    EVIDENCE_AUDIO_UPLOADED = "evidence.audio_uploaded"
    EVIDENCE_DELETED = "evidence.deleted"
    DASHBOARD_UPDATED = "dashboard.metrics_updated"
    SYSTEM_ALERT_CREATED = "dashboard.alert_triggered"
    INCIDENT_MONITORING_UPDATED = "incident.monitoring_updated"
    CONVERSATION_UPDATED = "conversation.updated"
    UNREAD_COUNT_UPDATED = "unread.count_updated"
    PUSH_SENT = "push.sent"
    PUSH_FAILED = "push.failed"
    TRACKING_PAUSED = "tracking.paused"
    TRACKING_RESUMED = "tracking.resumed"
    TECHNICIAN_LOCATION_UPDATED = "technician.location_updated"
    AUDIT_LOG_CREATED = "audit.log_created"
    USER_PROFILE_UPDATED = "user.profile_updated"
    USER_PASSWORD_CHANGED = "user.password_changed"
    USER_DEACTIVATED = "user.deactivated"
    USER_ROLE_CHANGED = "user.role_changed"
    TWO_FA_ENABLED = "2fa.enabled"
    SYSTEM_MAINTENANCE = "system.maintenance"
    EMERGENCY_ALERT = "emergency.alert"
    ASSIGNMENT_CREATED = "chat.message_sent"
    ASSIGNMENT_ATTEMPT_CREATED = "assignment.attempt_created"
    ASSIGNMENT_ACCEPTED = "incident.assignment_accepted"
    ASSIGNMENT_REJECTED = "incident.assignment_rejected"
    ASSIGNMENT_TIMEOUT = "incident.assignment_timeout"
