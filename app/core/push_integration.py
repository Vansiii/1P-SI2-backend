"""
Push Notification Integration with WebSocket Events

Automatically sends push notifications when users are offline or not connected to WebSocket.
"""
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from .websocket import manager as ws_manager
from .logging import get_logger
from ..modules.push_notifications.services import PushNotificationService, PushNotificationData

logger = get_logger(__name__)


async def send_notification_with_fallback(
    session: AsyncSession,
    user_id: int,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    force_push: bool = False
) -> bool:
    """
    Send notification via WebSocket if user is connected, otherwise via push notification.
    
    Args:
        session: Database session
        user_id: ID of the user
        title: Notification title
        body: Notification body
        data: Additional data
        force_push: Force push notification even if user is connected
        
    Returns:
        True if notification was sent successfully
    """
    try:
        # Check if user is connected to WebSocket
        is_connected = ws_manager.is_user_connected(user_id)
        
        if is_connected and not force_push:
            logger.debug(f"User {user_id} is connected, skipping push notification")
            return True
        
        # User is offline or force_push is True, send push notification
        push_service = PushNotificationService(session)
        
        if not push_service.is_enabled():
            logger.debug("Push notifications are disabled")
            return False
        
        notification_data = PushNotificationData(
            title=title,
            body=body,
            data=data or {}
        )
        
        success = await push_service.send_to_user(
            user_id=user_id,
            notification_data=notification_data,
            save_to_db=True
        )
        
        if success:
            logger.info(f"Push notification sent to offline user {user_id}: {title}")
        else:
            logger.warning(f"Failed to send push notification to user {user_id}")
        
        return success
        
    except Exception as e:
        logger.error(f"Error in send_notification_with_fallback: {str(e)}")
        return False


async def notify_incident_assigned(
    session: AsyncSession,
    user_id: int,
    incident_id: int,
    workshop_name: str
) -> bool:
    """
    Notify user that an incident has been assigned to a workshop.
    
    Args:
        session: Database session
        user_id: ID of the user (client)
        incident_id: ID of the incident
        workshop_name: Name of the workshop
        
    Returns:
        True if notification was sent successfully
    """
    return await send_notification_with_fallback(
        session=session,
        user_id=user_id,
        title="🔧 Taller Asignado",
        body=f"Tu solicitud ha sido asignada a {workshop_name}",
        data={
            "type": "incident_assigned",
            "incident_id": str(incident_id),
            "click_action": f"/incidents/{incident_id}"
        }
    )


async def notify_technician_assigned(
    session: AsyncSession,
    user_id: int,
    incident_id: int,
    technician_name: str
) -> bool:
    """
    Notify user that a technician has been assigned.
    
    Args:
        session: Database session
        user_id: ID of the user (client)
        incident_id: ID of the incident
        technician_name: Name of the technician
        
    Returns:
        True if notification was sent successfully
    """
    return await send_notification_with_fallback(
        session=session,
        user_id=user_id,
        title="👨‍🔧 Técnico Asignado",
        body=f"{technician_name} está en camino",
        data={
            "type": "technician_assigned",
            "incident_id": str(incident_id),
            "click_action": f"/incidents/{incident_id}"
        }
    )


async def notify_technician_arrived(
    session: AsyncSession,
    user_id: int,
    incident_id: int,
    technician_name: str
) -> bool:
    """
    Notify user that technician has arrived.
    
    Args:
        session: Database session
        user_id: ID of the user (client)
        incident_id: ID of the incident
        technician_name: Name of the technician
        
    Returns:
        True if notification was sent successfully
    """
    return await send_notification_with_fallback(
        session=session,
        user_id=user_id,
        title="📍 Técnico en Sitio",
        body=f"{technician_name} ha llegado a tu ubicación",
        data={
            "type": "technician_arrived",
            "incident_id": str(incident_id),
            "click_action": f"/incidents/{incident_id}"
        }
    )


async def notify_service_completed(
    session: AsyncSession,
    user_id: int,
    incident_id: int
) -> bool:
    """
    Notify user that service has been completed.
    
    Args:
        session: Database session
        user_id: ID of the user (client)
        incident_id: ID of the incident
        
    Returns:
        True if notification was sent successfully
    """
    return await send_notification_with_fallback(
        session=session,
        user_id=user_id,
        title="✅ Servicio Completado",
        body="El servicio ha sido completado exitosamente",
        data={
            "type": "service_completed",
            "incident_id": str(incident_id),
            "click_action": f"/incidents/{incident_id}"
        }
    )


async def notify_new_message(
    session: AsyncSession,
    user_id: int,
    incident_id: int,
    sender_name: str,
    message_preview: str
) -> bool:
    """
    Notify user of a new chat message.
    
    Args:
        session: Database session
        user_id: ID of the user (recipient)
        incident_id: ID of the incident
        sender_name: Name of the message sender
        message_preview: Preview of the message (first 50 chars)
        
    Returns:
        True if notification was sent successfully
    """
    preview = message_preview[:50] + "..." if len(message_preview) > 50 else message_preview
    
    return await send_notification_with_fallback(
        session=session,
        user_id=user_id,
        title=f"💬 {sender_name}",
        body=preview,
        data={
            "type": "new_message",
            "incident_id": str(incident_id),
            "click_action": f"/incidents/{incident_id}/chat"
        }
    )


async def notify_incident_status_changed(
    session: AsyncSession,
    user_id: int,
    incident_id: int,
    new_status: str,
    status_label: str
) -> bool:
    """
    Notify user of incident status change.
    
    Args:
        session: Database session
        user_id: ID of the user
        incident_id: ID of the incident
        new_status: New status code
        status_label: Human-readable status label
        
    Returns:
        True if notification was sent successfully
    """
    return await send_notification_with_fallback(
        session=session,
        user_id=user_id,
        title="📋 Estado Actualizado",
        body=f"Tu solicitud ahora está: {status_label}",
        data={
            "type": "incident_status_changed",
            "incident_id": str(incident_id),
            "new_status": new_status,
            "click_action": f"/incidents/{incident_id}"
        }
    )


async def notify_new_incident_to_workshop(
    session: AsyncSession,
    workshop_id: int,
    incident_id: int,
    category: str,
    priority: str
) -> bool:
    """
    Notify workshop of a new incident assignment.
    
    Args:
        session: Database session
        workshop_id: ID of the workshop
        incident_id: ID of the incident
        category: Incident category
        priority: Incident priority
        
    Returns:
        True if notification was sent successfully
    """
    return await send_notification_with_fallback(
        session=session,
        user_id=workshop_id,
        title="🆕 Nueva Solicitud",
        body=f"Incidente {category} - Prioridad: {priority}",
        data={
            "type": "new_incident_assignment",
            "incident_id": str(incident_id),
            "click_action": f"/incidents/{incident_id}"
        },
        force_push=True  # Always send push to workshops for new incidents
    )
