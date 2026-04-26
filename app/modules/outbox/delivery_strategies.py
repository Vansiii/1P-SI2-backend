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
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.websocket import ConnectionManager
from ...core.logging import get_logger

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
    
    # Map event types to user-friendly, professional titles
    TITLE_MAP = {
        # Incident lifecycle - Professional and clear
        "incident.created": "Solicitud recibida",
        "incident.assigned": "Taller asignado",
        "incident.assignment_accepted": "Solicitud aceptada",
        "incident.assignment_rejected": "Buscando alternativa",
        "incident.assignment_timeout": "Reasignando servicio",
        "incident.status_changed": "Estado actualizado",
        
        # Technician actions - Clear and informative
        "incident.technician_on_way": "Técnico en camino",
        "incident.technician_arrived": "Técnico en sitio",
        "incident.work_started": "Servicio iniciado",
        "incident.work_completed": "Servicio completado",
        
        # Search and reassignment - Transparent
        "incident.searching_workshop": "Buscando taller",
        "incident.no_workshop_available": "Sin talleres disponibles",
        "incident.reassignment_started": "Reasignando servicio",
        
        # Cancellation - Direct
        "incident.cancelled": "Servicio cancelado",
        
        # Communication - Simple
        "chat.message_sent": "Nuevo mensaje",
        "notification.general": "Notificación",
    }
    
    @staticmethod
    def get_title(event_type: str) -> str:
        """
        Get notification title for an event type.
        
        Args:
            event_type: Event type (e.g., "incident.created")
            
        Returns:
            User-friendly, professional title string
        """
        return NotificationFormatter.TITLE_MAP.get(event_type, "Actualización")
    
    @staticmethod
    def get_body(event_data: dict) -> str:
        """
        Extract professional notification body from event data.
        
        Provides context-aware, user-friendly messages.
        
        Args:
            event_data: Event payload dictionary
            
        Returns:
            Notification body string (max 100 characters)
        """
        event_type = event_data.get("event_type", "")
        incident_id = event_data.get("incident_id", "")
        
        # Professional, context-aware messages by event type
        body_templates = {
            "incident.created": f"Tu solicitud #{incident_id} está siendo procesada",
            "incident.assigned": f"Hemos asignado un taller para tu solicitud #{incident_id}",
            "incident.assignment_accepted": f"El taller ha aceptado tu solicitud #{incident_id}",
            "incident.assignment_rejected": f"Buscando alternativa para tu solicitud #{incident_id}",
            "incident.assignment_timeout": f"Reasignando tu solicitud #{incident_id}",
            
            "incident.technician_on_way": "El técnico se dirige a tu ubicación",
            "incident.technician_arrived": "El técnico ha llegado al lugar",
            "incident.work_started": "El servicio ha iniciado",
            "incident.work_completed": "El servicio ha sido completado",
            
            "incident.searching_workshop": "Buscando el mejor taller disponible",
            "incident.no_workshop_available": "No hay talleres disponibles en este momento",
            "incident.reassignment_started": "Buscando un nuevo taller para tu solicitud",
            
            "incident.cancelled": f"La solicitud #{incident_id} ha sido cancelada",
        }
        
        # Return template if exists
        if event_type in body_templates:
            return body_templates[event_type]
        
        # For chat messages, use content
        if event_type == "chat.message_sent":
            content = event_data.get("content", "Tienes un nuevo mensaje")
            return content[:100]
        
        # Fallback: try to extract meaningful message from event data
        if "message" in event_data:
            return str(event_data["message"])[:100]
        elif "description" in event_data:
            return str(event_data["description"])[:100]
        elif "content" in event_data:
            return str(event_data["content"])[:100]
        else:
            return "Tienes una actualización"


# ============================================================================
# Strategy Configuration
# ============================================================================

class StrategyConfig:
    """
    Centralized configuration for strategy selection.
    
    Defines which events use which delivery strategies.
    """
    
    # Critical events that require hybrid delivery (WebSocket + FCM)
    CRITICAL_EVENTS = {
        "incident.created",
        "incident.assigned",
        "incident.technician_arrived",
        "incident.work_completed",
    }
    
    # Event type prefixes
    CHAT_EVENTS_PREFIX = "chat."
    NOTIFICATION_EVENTS_PREFIX = "notification."
    
    @staticmethod
    def get_strategy_type(event_type: str) -> StrategyType:
        """
        Determine which strategy to use for an event type.
        
        Rules:
        - Critical events (incident lifecycle) → HYBRID
        - Chat events → HYBRID (real-time + persistent)
        - Notification events → PUSH (persistent only)
        - Default → HYBRID (safest option)
        
        Args:
            event_type: Event type string
            
        Returns:
            StrategyType enum value
        """
        # Critical events need both channels
        if event_type in StrategyConfig.CRITICAL_EVENTS:
            return StrategyType.HYBRID
        
        # Chat events need real-time + persistent
        if event_type.startswith(StrategyConfig.CHAT_EVENTS_PREFIX):
            return StrategyType.HYBRID
        
        # Notification events only need persistent
        if event_type.startswith(StrategyConfig.NOTIFICATION_EVENTS_PREFIX):
            return StrategyType.PUSH
        
        # Default to hybrid for safety
        return StrategyType.HYBRID



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
            
            # Format notification
            title = self.formatter.get_title(event_type)
            body = self.formatter.get_body(event_data)
            
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
    Delivers events via both WebSocket and FCM.
    
    Attempts WebSocket delivery first, then always attempts FCM
    regardless of WebSocket result. This ensures:
    - Users with multiple devices receive notifications on all devices
    - Unstable WebSocket connections have FCM as backup
    - Maximum reliability for critical events
    
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
        self.ws_strategy = WebSocketDeliveryStrategy(ws_manager)
        self.push_strategy = PushNotificationStrategy()
    
    async def deliver(
        self,
        session: AsyncSession,
        user_id: int,
        event_data: dict
    ) -> DeliveryResult:
        """
        Deliver event via both WebSocket and FCM.
        
        Args:
            session: Database session
            user_id: Target user ID
            event_data: Event payload
            
        Returns:
            DeliveryResult with combined success status and channels
        """
        event_type = event_data.get("event_type", "")
        channels = []
        
        # Attempt WebSocket delivery
        ws_result = await self.ws_strategy.deliver(session, user_id, event_data)
        if ws_result.success:
            channels.append("websocket")
            logger.debug(f"WebSocket delivery succeeded for user {user_id}")
        else:
            logger.debug(
                f"WebSocket delivery failed for user {user_id}: {ws_result.reason}"
            )
        
        # Always attempt FCM delivery (even if WebSocket succeeded)
        # This ensures users with multiple devices get notifications on all devices
        push_result = await self.push_strategy.deliver(session, user_id, event_data)
        if push_result.success:
            channels.append("push")
            logger.debug(f"FCM delivery succeeded for user {user_id}")
        else:
            logger.debug(
                f"FCM delivery failed for user {user_id}: {push_result.reason}"
            )
        
        # Success if at least one channel worked
        if channels:
            channel_str = "+".join(channels)
            logger.info(
                f"✅ Hybrid delivery succeeded for user {user_id} "
                f"via {channel_str} (event: {event_type})"
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
    
    def get_strategy(self, event_type: str) -> DeliveryStrategy:
        """
        Get appropriate delivery strategy for event type.
        
        Args:
            event_type: Type of event to deliver
            
        Returns:
            DeliveryStrategy instance
        """
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
