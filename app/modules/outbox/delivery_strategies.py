"""
Delivery Strategies for Outbox Event Delivery.

This module implements the Strategy Pattern for delivering events to users
through different channels (WebSocket, FCM, or hybrid). It eliminates the
"assumed delivery" bug by ensuring all delivery attempts are verified.

Key Components:
- DeliveryStrategy: Abstract interface for delivery mechanisms
- DeliveryResult: Data structure for delivery outcomes
- WebSocketDeliveryStrategy: WebSocket-only delivery
- PushNotificationStrategy: FCM-only delivery
- HybridDeliveryStrategy: Combined WebSocket + FCM delivery
- DeliveryStrategyFactory: Strategy selection based on event type
- NotificationFormatter: Title and body extraction from events
- StrategyConfig: Centralized strategy configuration
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from enum import Enum
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.websocket import ConnectionManager
from ...core.logging import get_logger
from ...models.user import User
from .notification_filter import NotificationFilter, DeliveryMode

logger = get_logger(__name__)


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class DeliveryResult:
    """
    Result of a delivery attempt.
    
    Attributes:
        success: Whether delivery succeeded
        channel: Delivery channel used (e.g., "websocket", "push", "websocket+push")
        reason: Failure reason if success is False
    
    Examples:
        >>> DeliveryResult(success=True, channel="websocket")
        >>> DeliveryResult(success=False, reason="user_offline")
    """
    success: bool
    channel: Optional[str] = None
    reason: Optional[str] = None
    
    def __post_init__(self):
        """Validate that success=True has channel, success=False has reason."""
        if self.success and not self.channel:
            raise ValueError("Successful delivery must specify channel")
        if not self.success and not self.reason:
            raise ValueError("Failed delivery must specify reason")


class StrategyType(Enum):
    """Types of delivery strategies available."""
    WEBSOCKET = "websocket"
    PUSH = "push"
    HYBRID = "hybrid"


# ============================================================================
# Abstract Interface
# ============================================================================

class DeliveryStrategy(ABC):
    """
    Abstract base class for event delivery strategies.
    
    Implementations must define how to deliver events to users
    through specific channels (WebSocket, FCM, etc.).
    
    The Strategy Pattern allows:
    - Easy addition of new delivery mechanisms
    - Independent testing of each strategy
    - Runtime selection of delivery behavior
    - Separation of concerns
    """
    
    @abstractmethod
    async def deliver(
        self,
        session: AsyncSession,
        user_id: int,
        event_data: dict
    ) -> DeliveryResult:
        """
        Deliver an event to a specific user.
        
        Args:
            session: Database session for queries
            user_id: Target user ID
            event_data: Event payload to deliver
            
        Returns:
            DeliveryResult indicating success/failure and channel used
            
        Raises:
            Should not raise exceptions - catch and return failure result
        """
        pass


# ============================================================================
# Notification Formatter
# ============================================================================

class NotificationFormatter:
    """
    Utility class for extracting notification titles and bodies from events.
    
    Provides consistent, professional notification formatting across all delivery strategies.
    """
    
    TITLE_MAP = {
        # Incident lifecycle
        "incident.created": "Solicitud recibida",
        "incident.assigned": "Taller asignado",
        "incident.assignment_accepted": "Solicitud aceptada",
        "incident.assignment_rejected": "Buscando alternativa",
        "incident.assignment_timeout": "Reasignando servicio",
        "incident.status_changed": "Estado actualizado",
        "incident.reassigned": "Servicio reasignado",
        "incident.updated": "Servicio actualizado",
        "incident.photos_uploaded": "Fotos recibidas",
        "incident.reassignment_started": "Reasignando servicio",
        
        # Technician actions
        "incident.technician_on_way": "Tecnico en camino",
        "incident.technician_arrived": "Tecnico en sitio",
        "incident.work_started": "Servicio iniciado",
        "incident.work_completed": "Servicio completado",
        "technician.availability_changed": "Disponibilidad actualizada",
        "technician.online_status_changed": "Estado de tecnico",
        
        # AI Analysis
        "incident.analysis_started": "Analizando solicitud",
        "incident.analysis_completed": "Analisis completado",
        "incident.analysis_failed": "Analisis no disponible",
        
        # Search and reassignment
        "incident.searching_workshop": "Buscando taller",
        "incident.no_workshop_available": "Sin talleres disponibles",
        
        # Cancellation
        "incident.cancelled": "Servicio cancelado",
        "cancellation.requested": "Cancelacion solicitada",
        "cancellation.approved": "Cancelacion aprobada",
        "cancellation.rejected": "Cancelacion rechazada",
        
        # Communication
        "chat.message_sent": "Nuevo mensaje",
        "chat.message_delivered": "Mensaje entregado",
        
        # Evidence
        "evidence.image_uploaded": "Imagen recibida",
        "evidence.audio_uploaded": "Audio recibido",
        "evidence.deleted": "Evidencia eliminada",
        
        # Notifications
        "notification.received": "Notificacion",
        "notification.general": "Notificacion",
        
        # Workshop
        "workshop.availability_changed": "Taller actualizado",
        "workshop.verified": "Taller verificado",
        "workshop.updated": "Taller actualizado",
        "workshop.balance_updated": "Balance actualizado",
        
        # Vehicle
        "vehicle.created": "Vehiculo registrado",
        "vehicle.updated": "Vehiculo actualizado",
        
        # Service
        "service.started": "Servicio iniciado",
        "service.completed": "Servicio completado",
        "service.paused": "Servicio pausado",
        "service.resumed": "Servicio reanudado",
        
        # Tracking
        "tracking.session_started": "Seguimiento iniciado",
        "tracking.session_ended": "Seguimiento finalizado",
        "tracking.location_updated": "Ubicacion actualizada",
        
        # Dashboard (admin only)
        "dashboard.metrics_updated": "Metricas actualizadas",
        "dashboard.alert_triggered": "Alerta del sistema",
        
        # User
        "user.profile_updated": "Perfil actualizado",
        "user.password_changed": "Contrasena cambiada",
        
        # Audit (admin only)
        "audit.log_created": "Actividad registrada",
    }
    
    @staticmethod
    def get_title(
        event_type: str,
        recipient_type: str = "unknown",
        event_data: Optional[dict] = None,
    ) -> str:
        if event_type == "incident.assigned":
            if recipient_type == "workshop":
                return "Nueva solicitud"
            if recipient_type == "admin":
                return "Incidente asignado"

        if event_type == "incident.reassigned":
            if recipient_type == "workshop":
                return "Solicitud reasignada"
            if recipient_type == "admin":
                return "Incidente reasignado"

        if event_type == "incident.assignment_timeout":
            if recipient_type == "workshop":
                return "Solicitud vencida"
            if recipient_type == "admin":
                return "Tiempo de asignación agotado"

        if event_type == "incident.assignment_rejected" and recipient_type in {"workshop", "admin"}:
            return "Solicitud rechazada"

        return NotificationFormatter.TITLE_MAP.get(event_type, NotificationFormatter._fallback_title(event_type))
    
    @staticmethod
    def _fallback_title(event_type: str) -> str:
        parts = event_type.split(".", 1)
        if len(parts) == 2:
            domain, action = parts
            return f"{domain.title()} - {action.replace('_', ' ').title()}"
        return "MecanicoYa"
    
    @staticmethod
    def get_body(event_data: dict, recipient_type: str = "unknown") -> str:
        event_type = event_data.get("event_type", "")
        incident_id = event_data.get("incident_id", "")
        assignment_mode = event_data.get("assignment_mode")
        workshop_name = event_data.get("workshop_name") or event_data.get("new_workshop_name")
        technician_name = event_data.get("technician_name")

        if event_type == "incident.assignment_rejected" and assignment_mode == "manual":
            if recipient_type == "admin":
                return (
                    f"El taller rechazó la solicitud #{incident_id}. "
                    "El cliente puede elegir otro taller."
                )
            if recipient_type == "workshop":
                return f"Rechazaste la solicitud #{incident_id}."
            return (
                f"El taller rechazó tu solicitud #{incident_id}. "
                "Puedes elegir otro taller."
            )

        if event_type == "incident.assignment_timeout" and assignment_mode == "manual":
            if recipient_type == "admin":
                return (
                    f"El taller no respondió la solicitud #{incident_id}. "
                    "El cliente puede elegir otro taller."
                )
            if recipient_type == "workshop":
                return f"La solicitud #{incident_id} venció por falta de respuesta."
            return (
                f"El taller no respondió a tu solicitud #{incident_id}. "
                "Puedes elegir otro taller."
            )

        if event_type == "incident.assigned":
            if recipient_type == "workshop":
                return f"Recibiste la solicitud #{incident_id}."
            if recipient_type == "admin":
                return (
                    f"La solicitud #{incident_id} fue asignada a {workshop_name}."
                    if workshop_name
                    else f"La solicitud #{incident_id} fue asignada a un taller."
                )

        if event_type == "incident.assignment_accepted":
            if recipient_type == "workshop":
                return (
                    f"Aceptaste la solicitud #{incident_id} con {technician_name}."
                    if technician_name
                    else f"Aceptaste la solicitud #{incident_id}."
                )
            if recipient_type == "admin":
                return f"El taller aceptó la solicitud #{incident_id}."

        if event_type == "incident.reassigned":
            if recipient_type == "workshop":
                return f"La solicitud #{incident_id} fue reasignada."
            if recipient_type == "admin":
                return (
                    f"La solicitud #{incident_id} fue reasignada a {workshop_name}."
                    if workshop_name
                    else f"La solicitud #{incident_id} fue reasignada."
                )
        
        body_templates = {
            "incident.created": f"Tu solicitud #{incident_id} esta siendo procesada",
            "incident.assigned": f"Hemos asignado un taller para tu solicitud #{incident_id}",
            "incident.assignment_accepted": f"El taller ha aceptado tu solicitud #{incident_id}",
            "incident.assignment_rejected": f"Buscando alternativa para tu solicitud #{incident_id}",
            "incident.assignment_timeout": f"Reasignando tu solicitud #{incident_id}",
            "incident.status_changed": f"Tu solicitud #{incident_id} ahora esta en '{event_data.get('new_status', 'actualizado')}'",
            "incident.reassigned": f"Tu solicitud #{incident_id} ha sido reasignada",
            "incident.updated": f"Tu solicitud #{incident_id} ha sido actualizada",
            "incident.photos_uploaded": f"Se recibieron fotos para tu solicitud #{incident_id}",
            "incident.reassignment_started": f"Buscando un nuevo taller para tu solicitud #{incident_id}",
            
            "incident.technician_on_way": "El tecnico se dirige a tu ubicacion",
            "incident.technician_arrived": "El tecnico ha llegado al lugar",
            "incident.work_started": "El servicio ha iniciado",
            "incident.work_completed": "El servicio ha sido completado",
            "technician.availability_changed": "La disponibilidad del tecnico ha cambiado",
            "technician.online_status_changed": "El estado de conexion del tecnico ha cambiado",
            
            "incident.analysis_started": "Estamos analizando tu solicitud con IA",
            "incident.analysis_completed": "El analisis de tu solicitud esta listo",
            "incident.analysis_failed": "No se pudo completar el analisis automatico",
            
            "incident.searching_workshop": "Buscando el mejor taller disponible",
            "incident.no_workshop_available": "No hay talleres disponibles en este momento",
            
            "incident.cancelled": f"La solicitud #{incident_id} ha sido cancelada",
            "cancellation.requested": f"Se ha solicitado cancelar el servicio #{incident_id}",
            "cancellation.approved": f"La cancelacion del servicio #{incident_id} fue aprobada",
            "cancellation.rejected": f"La cancelacion del servicio #{incident_id} fue rechazada",
            
            "chat.message_delivered": f"Mensaje entregado para el servicio #{incident_id}",
            
            "evidence.image_uploaded": f"Nueva imagen para el servicio #{incident_id}",
            "evidence.audio_uploaded": f"Nuevo audio para el servicio #{incident_id}",
            "evidence.deleted": f"Se elimino evidencia del servicio #{incident_id}",
            
            "notification.received": event_data.get("body", event_data.get("message", "Tienes una notificacion")),
            "notification.general": event_data.get("body", event_data.get("message", "Tienes una notificacion")),
            
            "workshop.availability_changed": "La disponibilidad del taller ha cambiado",
            "workshop.verified": "El taller ha sido verificado",
            "workshop.updated": "La informacion del taller ha sido actualizada",
            "workshop.balance_updated": "El balance del taller ha sido actualizado",
            
            "vehicle.created": "Vehiculo registrado exitosamente",
            "vehicle.updated": "La informacion del vehiculo ha sido actualizada",
            
            "service.started": "El servicio ha iniciado",
            "service.completed": "El servicio ha sido completado",
            "service.paused": "El servicio ha sido pausado",
            "service.resumed": "El servicio ha sido reanudado",
            
            "tracking.session_started": "El seguimiento GPS ha iniciado",
            "tracking.session_ended": "El seguimiento GPS ha finalizado",
            "tracking.location_updated": "La ubicacion ha sido actualizada",
            
            "dashboard.metrics_updated": "Las metricas del panel se han actualizado",
            "dashboard.alert_triggered": event_data.get("message", "Se ha activado una alerta del sistema"),
            
            "user.profile_updated": "Tu perfil ha sido actualizado",
            "user.password_changed": "Tu contrasena ha sido cambiada",
            
            "audit.log_created": "Se ha registrado actividad en el sistema",
        }
        
        if event_type in body_templates:
            return body_templates[event_type]
        
        if event_type == "chat.message_sent":
            content = event_data.get("content", "Tienes un nuevo mensaje")
            return content[:100]
        
        if "message" in event_data:
            return str(event_data["message"])[:100]
        elif "description" in event_data:
            return str(event_data["description"])[:100]
        elif "content" in event_data:
            return str(event_data["content"])[:100]
        else:
            return NotificationFormatter._fallback_body(event_type)
    
    @staticmethod
    def _fallback_body(event_type: str) -> str:
        parts = event_type.split(".", 1)
        if len(parts) == 2:
            domain, action = parts
            return f"{domain.title()}: {action.replace('_', ' ').title()}"
        return ""


# ============================================================================
# Strategy Configuration
# ============================================================================

class StrategyConfig:
    """
    Centralized configuration for strategy selection.
    
    Defines which events use which delivery strategies.
    Aligned with NotificationFilter classifications to prevent push spam.
    """
    
    # Critical events that require hybrid delivery (WebSocket + FCM)
    # These events are delivered via BOTH channels regardless of online status
    # Aligned with NotificationFilter.CRITICAL_EVENTS
    CRITICAL_EVENTS = {
        "incident.created",
        "incident.assigned",
        "incident.assignment_accepted",
        "incident.assignment_rejected",
        "incident.technician_arrived",
        "incident.work_completed",
        "incident.cancelled",
        "incident.no_workshop_available",
        "incident.assignment_timeout",
        "cancellation.requested",
        "cancellation.approved",
        "cancellation.rejected",
        "chat.message_sent",
    }
    
    # Events where push is always sent even if user is online via WebSocket
    # (Maximum importance: user might have the screen off or app in background)
    ALWAYS_PUSH_EVENTS = {
        "incident.assigned",
        "incident.assignment_accepted",
        "incident.assignment_rejected",
        "incident.no_workshop_available",
        "incident.assignment_timeout",
        "incident.cancelled",
        "chat.message_sent",
    }
    
    # Event type prefixes
    CHAT_EVENTS_PREFIX = "chat."
    NOTIFICATION_EVENTS_PREFIX = "notification."
    
    @staticmethod
    def get_strategy_type(event_type: str) -> StrategyType:
        """
        Determine which strategy to use for an event type.
        
        Rules (aligned with NotificationFilter):
        - Critical events → HYBRID (WS + push fallback)
        - Chat events → HYBRID (real-time + persistent)
        - Notification events → PUSH (persistent only)
        - Default → WEBSOCKET (no push unless critical — prevents push spam)
        
        Args:
            event_type: Event type string
            
        Returns:
            StrategyType enum value
        """
        # Chat receipts are transport-level realtime updates.
        # They must not create push notifications.
        if event_type in {"chat.message_delivered", "chat.message_read"}:
            return StrategyType.WEBSOCKET

        # Critical events need both channels
        if event_type in StrategyConfig.CRITICAL_EVENTS:
            return StrategyType.HYBRID
        
        # Chat events need real-time + persistent
        if event_type.startswith(StrategyConfig.CHAT_EVENTS_PREFIX):
            return StrategyType.HYBRID
        
        # Notification events only need persistent
        if event_type.startswith(StrategyConfig.NOTIFICATION_EVENTS_PREFIX):
            return StrategyType.PUSH
        
        # Default to WebSocket only — no push unless explicitly classified as critical.
        # This prevents push spam for informative/technical/silent events that
        # should only be delivered via WebSocket.
        return StrategyType.WEBSOCKET



# ============================================================================
# Strategy Implementations
# ============================================================================

class WebSocketDeliveryStrategy(DeliveryStrategy):
    """
    Delivers events via WebSocket connections.
    
    Only succeeds if user is currently connected to WebSocket.
    Does not attempt any fallback mechanisms.
    
    Use Cases:
    - Real-time updates for connected users
    - Low-latency event delivery
    - Events that don't need persistence
    """
    
    def __init__(self, ws_manager: ConnectionManager):
        """
        Initialize WebSocket delivery strategy.
        
        Args:
            ws_manager: WebSocket connection manager
        """
        self.ws_manager = ws_manager
    
    async def deliver(
        self,
        session: AsyncSession,
        user_id: int,
        event_data: dict
    ) -> DeliveryResult:
        """
        Deliver event via WebSocket.
        
        Args:
            session: Database session (unused for WebSocket)
            user_id: Target user ID
            event_data: Event payload
            
        Returns:
            DeliveryResult with success status and channel
        """
        # Check if user is connected
        if not self.ws_manager.is_user_connected(user_id):
            logger.debug(f"User {user_id} not connected to WebSocket")
            return DeliveryResult(
                success=False,
                reason="user_offline"
            )
        
        try:
            # Send event via WebSocket
            await self.ws_manager.send_to_user(user_id, event_data)
            
            logger.info(
                f"📡 Delivered event {event_data.get('event_type')} "
                f"to user {user_id} via WebSocket"
            )
            
            return DeliveryResult(
                success=True,
                channel="websocket"
            )
            
        except Exception as e:
            logger.warning(
                f"WebSocket delivery failed for user {user_id}: {str(e)}"
            )
            return DeliveryResult(
                success=False,
                reason=f"websocket_error: {str(e)}"
            )


class PushNotificationStrategy(DeliveryStrategy):
    """
    Delivers events via Firebase Cloud Messaging (FCM).
    
    Converts event data into user-friendly push notifications
    and sends them to all registered devices for the user.
    
    Use Cases:
    - Notifications for offline users
    - Persistent notifications
    - Multi-device delivery
    """
    
    def __init__(self):
        """Initialize push notification strategy."""
        self.formatter = NotificationFormatter()
    
    async def deliver(
        self,
        session: AsyncSession,
        user_id: int,
        event_data: dict
    ) -> DeliveryResult:
        """
        Deliver event via FCM push notification.
        
        Args:
            session: Database session for PushNotificationService
            user_id: Target user ID
            event_data: Event payload
            
        Returns:
            DeliveryResult with success status and channel
        """
        # Import here to avoid circular dependency
        from ...modules.push_notifications.services import (
            PushNotificationService,
            PushNotificationData
        )
        
        try:
            # Initialize push service
            push_service = PushNotificationService(session)
            
            if not push_service.is_enabled():
                logger.debug("Push notifications are disabled")
                return DeliveryResult(
                    success=False,
                    reason="push_disabled"
                )
            
            # Extract event type
            event_type = event_data.get("event_type", "")

            user_result = await session.execute(
                select(User.user_type).where(User.id == user_id).limit(1)
            )
            recipient_type = (user_result.scalar_one_or_none() or "unknown").strip().lower()

            if event_type == "chat.message_sent":
                incident_id = event_data.get("incident_id")
                if incident_id and not event_data.get("click_action"):
                    if recipient_type == "workshop":
                        event_data["click_action"] = f"/workshop/incidents/{incident_id}"
                    elif recipient_type == "admin":
                        event_data["click_action"] = f"/admin/incident/{incident_id}"
                    else:
                        event_data["click_action"] = f"/incidents/{incident_id}"
                event_data.setdefault("type", "chat_message")

            # Format notification
            title = self.formatter.get_title(event_type, recipient_type, event_data)
            body = self.formatter.get_body(event_data, recipient_type)
            
            # Create notification data
            notification_data = PushNotificationData(
                title=title,
                body=body,
                data=event_data
            )
            
            # Send push notification
            success = await push_service.send_to_user(
                user_id=user_id,
                notification_data=notification_data,
                save_to_db=True
            )
            
            if success:
                logger.info(
                    f"📱 Delivered event {event_type} "
                    f"to user {user_id} via FCM: {title}"
                )
                return DeliveryResult(
                    success=True,
                    channel="push"
                )
            else:
                logger.warning(
                    f"FCM delivery failed for user {user_id}: "
                    f"no registered tokens or send failed"
                )
                return DeliveryResult(
                    success=False,
                    reason="no_tokens_or_send_failed"
                )
                
        except Exception as e:
            logger.error(
                f"Push notification delivery failed for user {user_id}: {str(e)}",
                exc_info=True
            )
            return DeliveryResult(
                success=False,
                reason=f"push_error: {str(e)}"
            )


class HybridDeliveryStrategy(DeliveryStrategy):
    """
    Delivers events via WebSocket and conditionally via FCM.
    
    Smart delivery logic:
    - Try WebSocket delivery first
    - If WebSocket succeeds → no push needed (avoids duplicate notifications)
    - If WebSocket fails → fall back to FCM push (user is offline/unreachable)
    
    Use Cases:
    - Critical incident lifecycle events
    - Chat messages (real-time + persistent)
    - Events requiring guaranteed delivery
    """
    
    def __init__(self, ws_manager: ConnectionManager):
        """
        Initialize hybrid delivery strategy.
        
        Args:
            ws_manager: WebSocket connection manager
        """
        self.ws_manager = ws_manager
        self.ws_strategy = WebSocketDeliveryStrategy(ws_manager)
        self.push_strategy = PushNotificationStrategy()
    
    async def deliver(
        self,
        session: AsyncSession,
        user_id: int,
        event_data: dict
    ) -> DeliveryResult:
        """
        Deliver event via WebSocket and conditionally via FCM.
        
        Smart deduplication: push is only sent when WebSocket delivery fails
        (user is offline or unreachable).
        
        Args:
            session: Database session
            user_id: Target user ID
            event_data: Event payload
            
        Returns:
            DeliveryResult with combined success status and channels
        """
        event_type = event_data.get("event_type", "")
        channels = []
        
        # Determine if this event type is in the always-push category (for logging)
        always_push = event_type in StrategyConfig.ALWAYS_PUSH_EVENTS
        
        # Attempt WebSocket delivery
        ws_result = await self.ws_strategy.deliver(session, user_id, event_data)
        if ws_result.success:
            channels.append("websocket")
            logger.debug(f"WebSocket delivery succeeded for user {user_id}")
        else:
            logger.debug(
                f"WebSocket delivery failed for user {user_id}: {ws_result.reason}"
            )
        
        # Decide whether to send push notification:
        # - Always-push events: send push even if WS succeeded (critical visibility)
        # - Other events: push only when WS failed (fallback mode)
        should_push = always_push or not ws_result.success
        
        if should_push:
            push_result = await self.push_strategy.deliver(session, user_id, event_data)
            if push_result.success:
                channels.append("push")
                logger.debug(f"FCM delivery succeeded for user {user_id}")
            else:
                logger.debug(
                    f"FCM delivery skipped/failed for user {user_id}: {push_result.reason}"
                )
        else:
            logger.debug(
                f"FCM push skipped for user {user_id} — already notified via WebSocket "
                f"(event: {event_type}). Push only used as fallback when WS fails."
            )
        
        # Success if at least one channel worked
        if channels:
            channel_str = "+".join(channels)
            logger.info(
                f"✅ Hybrid delivery succeeded for user {user_id} "
                f"via {channel_str} (event: {event_type}, always_push={always_push})"
            )
            return DeliveryResult(
                success=True,
                channel=channel_str
            )
        else:
            logger.warning(
                f"❌ Hybrid delivery failed for user {user_id}: "
                f"all channels failed (event: {event_type})"
            )
            return DeliveryResult(
                success=False,
                reason="all_channels_failed"
            )


# ============================================================================
# Strategy Factory
# ============================================================================

class DeliveryStrategyFactory:
    """
    Factory for creating delivery strategy instances.
    
    Selects the appropriate strategy based on event type
    using centralized configuration.
    
    Benefits:
    - Single point of configuration
    - Strategy instance reuse (performance)
    - Easy to add new strategies
    - Runtime strategy selection
    """
    
    def __init__(self, ws_manager: ConnectionManager):
        """
        Initialize factory with dependencies.
        
        Args:
            ws_manager: WebSocket connection manager
        """
        self.ws_manager = ws_manager
        
        # Strategy instances (reused for efficiency)
        self._websocket_strategy = WebSocketDeliveryStrategy(ws_manager)
        self._push_strategy = PushNotificationStrategy()
        self._hybrid_strategy = HybridDeliveryStrategy(ws_manager)
    
    def get_strategy(self, event_type: str, user_type: str = "unknown") -> DeliveryStrategy:
        """
        Get appropriate delivery strategy for event type.
        
        Args:
            event_type: Type of event to deliver
            
        Returns:
            DeliveryStrategy instance
        """
        delivery_mode = NotificationFilter.get_delivery_mode(event_type, user_type)

        if delivery_mode == DeliveryMode.WEBSOCKET_ONLY:
            return self._websocket_strategy
        if delivery_mode == DeliveryMode.PUSH_ONLY:
            return self._push_strategy
        if delivery_mode == DeliveryMode.SILENT:
            return self._websocket_strategy

        strategy_type = StrategyConfig.get_strategy_type(event_type)
        
        if strategy_type == StrategyType.WEBSOCKET:
            return self._websocket_strategy
        elif strategy_type == StrategyType.PUSH:
            return self._push_strategy
        elif strategy_type == StrategyType.HYBRID:
            return self._hybrid_strategy
        else:
            # Default to hybrid for safety
            logger.warning(
                f"Unknown strategy type {strategy_type} for event {event_type}, "
                f"defaulting to hybrid"
            )
            return self._hybrid_strategy
