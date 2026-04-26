"""
Unit tests for Outbox Delivery Strategies.

Tests the Strategy Pattern implementation for event delivery
through WebSocket, FCM, and hybrid channels.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from app.modules.outbox.delivery_strategies import (
    DeliveryResult,
    DeliveryStrategy,
    StrategyType,
    NotificationFormatter,
    StrategyConfig,
    WebSocketDeliveryStrategy,
    PushNotificationStrategy,
    HybridDeliveryStrategy,
    DeliveryStrategyFactory,
)


# ============================================================================
# DeliveryResult Tests
# ============================================================================

def test_delivery_result_success_requires_channel():
    """Test that successful delivery must specify channel."""
    with pytest.raises(ValueError, match="must specify channel"):
        DeliveryResult(success=True)


def test_delivery_result_failure_requires_reason():
    """Test that failed delivery must specify reason."""
    with pytest.raises(ValueError, match="must specify reason"):
        DeliveryResult(success=False)


def test_delivery_result_success_valid():
    """Test valid successful delivery result."""
    result = DeliveryResult(success=True, channel="websocket")
    assert result.success is True
    assert result.channel == "websocket"
    assert result.reason is None


def test_delivery_result_failure_valid():
    """Test valid failed delivery result."""
    result = DeliveryResult(success=False, reason="user_offline")
    assert result.success is False
    assert result.reason == "user_offline"
    assert result.channel is None


# ============================================================================
# NotificationFormatter Tests
# ============================================================================

def test_notification_formatter_known_event_types():
    """Test formatter returns correct titles for known event types."""
    assert NotificationFormatter.get_title("incident.created") == "Solicitud recibida"
    assert NotificationFormatter.get_title("incident.assigned") == "Taller asignado"
    assert NotificationFormatter.get_title("incident.technician_arrived") == "Técnico en sitio"
    assert NotificationFormatter.get_title("chat.message_sent") == "Nuevo mensaje"


def test_notification_formatter_unknown_event_type():
    """Test formatter returns default title for unknown event types."""
    assert NotificationFormatter.get_title("unknown.event") == "Actualización"


def test_notification_formatter_body_from_message_field():
    """Test formatter extracts body from 'message' field."""
    event_data = {"message": "Test message"}
    body = NotificationFormatter.get_body(event_data)
    assert body == "Test message"


def test_notification_formatter_body_from_content_field():
    """Test formatter extracts body from 'content' field."""
    event_data = {"content": "Test content"}
    body = NotificationFormatter.get_body(event_data)
    assert body == "Test content"


def test_notification_formatter_body_truncation():
    """Test formatter truncates body to 100 characters."""
    long_message = "a" * 150
    event_data = {"message": long_message}
    body = NotificationFormatter.get_body(event_data)
    assert len(body) == 100
    assert body.endswith("...")


def test_notification_formatter_body_contextual():
    """Test formatter generates contextual body for incident events."""
    event_data = {
        "event_type": "incident.created",
        "incident_id": 123
    }
    body = NotificationFormatter.get_body(event_data)
    assert "123" in body
    assert "solicitud" in body.lower()


# ============================================================================
# StrategyConfig Tests
# ============================================================================

def test_strategy_config_critical_events():
    """Test critical events return HYBRID strategy."""
    critical_events = [
        "incident.created",
        "incident.assigned",
        "incident.technician_arrived",
        "incident.work_completed",
    ]
    for event_type in critical_events:
        assert StrategyConfig.get_strategy_type(event_type) == StrategyType.HYBRID


def test_strategy_config_chat_events():
    """Test chat events return HYBRID strategy."""
    assert StrategyConfig.get_strategy_type("chat.message_sent") == StrategyType.HYBRID
    assert StrategyConfig.get_strategy_type("chat.message_read") == StrategyType.HYBRID


def test_strategy_config_notification_events():
    """Test notification events return PUSH strategy."""
    assert StrategyConfig.get_strategy_type("notification.general") == StrategyType.PUSH
    assert StrategyConfig.get_strategy_type("notification.reminder") == StrategyType.PUSH


def test_strategy_config_unknown_events():
    """Test unknown events default to HYBRID strategy."""
    assert StrategyConfig.get_strategy_type("unknown.event") == StrategyType.HYBRID


# ============================================================================
# WebSocketDeliveryStrategy Tests
# ============================================================================

@pytest.mark.asyncio
async def test_websocket_delivery_user_offline():
    """Test WebSocket delivery when user is offline."""
    # Arrange
    ws_manager = Mock()
    ws_manager.is_user_connected.return_value = False
    strategy = WebSocketDeliveryStrategy(ws_manager)
    
    # Act
    result = await strategy.deliver(
        session=Mock(),
        user_id=123,
        event_data={"event_type": "test.event"}
    )
    
    # Assert
    assert result.success is False
    assert result.reason == "user_offline"
    assert result.channel is None
    ws_manager.is_user_connected.assert_called_once_with(123)


@pytest.mark.asyncio
async def test_websocket_delivery_success():
    """Test successful WebSocket delivery."""
    # Arrange
    ws_manager = Mock()
    ws_manager.is_user_connected.return_value = True
    ws_manager.send_to_user = AsyncMock()
    strategy = WebSocketDeliveryStrategy(ws_manager)
    
    event_data = {"event_type": "test.event", "data": "test"}
    
    # Act
    result = await strategy.deliver(
        session=Mock(),
        user_id=123,
        event_data=event_data
    )
    
    # Assert
    assert result.success is True
    assert result.channel == "websocket"
    ws_manager.send_to_user.assert_called_once_with(123, event_data)


@pytest.mark.asyncio
async def test_websocket_delivery_exception():
    """Test WebSocket delivery when send raises exception."""
    # Arrange
    ws_manager = Mock()
    ws_manager.is_user_connected.return_value = True
    ws_manager.send_to_user = AsyncMock(side_effect=Exception("Connection lost"))
    strategy = WebSocketDeliveryStrategy(ws_manager)
    
    # Act
    result = await strategy.deliver(
        session=Mock(),
        user_id=123,
        event_data={"event_type": "test.event"}
    )
    
    # Assert
    assert result.success is False
    assert "Connection lost" in result.reason


@pytest.mark.asyncio
async def test_websocket_delivery_preserves_data():
    """Test WebSocket delivery preserves complete event data."""
    # Arrange
    ws_manager = Mock()
    ws_manager.is_user_connected.return_value = True
    ws_manager.send_to_user = AsyncMock()
    strategy = WebSocketDeliveryStrategy(ws_manager)
    
    event_data = {
        "event_type": "incident.created",
        "incident_id": 456,
        "client_id": 789,
        "metadata": {"key": "value"}
    }
    
    # Act
    await strategy.deliver(
        session=Mock(),
        user_id=123,
        event_data=event_data
    )
    
    # Assert
    sent_data = ws_manager.send_to_user.call_args[0][1]
    assert sent_data == event_data
    assert sent_data["incident_id"] == 456
    assert sent_data["metadata"]["key"] == "value"


# ============================================================================
# PushNotificationStrategy Tests
# ============================================================================

@pytest.mark.asyncio
async def test_push_delivery_success():
    """Test successful FCM push delivery."""
    # Arrange
    strategy = PushNotificationStrategy()
    session = AsyncMock()
    
    # Mock PushNotificationService
    with patch('app.modules.push_notifications.services.PushNotificationService') as MockService:
        mock_service = MockService.return_value
        mock_service.is_enabled.return_value = True
        mock_service.send_to_user = AsyncMock(return_value=True)
        
        event_data = {
            "event_type": "incident.created",
            "incident_id": 456
        }
        
        # Act
        result = await strategy.deliver(
            session=session,
            user_id=123,
            event_data=event_data
        )
        
        # Assert
        assert result.success is True
        assert result.channel == "push"
        mock_service.send_to_user.assert_called_once()


@pytest.mark.asyncio
async def test_push_delivery_disabled():
    """Test push delivery when service is disabled."""
    # Arrange
    strategy = PushNotificationStrategy()
    session = AsyncMock()
    
    with patch('app.modules.push_notifications.services.PushNotificationService') as MockService:
        mock_service = MockService.return_value
        mock_service.is_enabled.return_value = False
        
        # Act
        result = await strategy.deliver(
            session=session,
            user_id=123,
            event_data={"event_type": "test.event"}
        )
        
        # Assert
        assert result.success is False
        assert result.reason == "push_disabled"


@pytest.mark.asyncio
async def test_push_delivery_no_tokens():
    """Test push delivery when user has no registered tokens."""
    # Arrange
    strategy = PushNotificationStrategy()
    session = AsyncMock()
    
    with patch('app.modules.push_notifications.services.PushNotificationService') as MockService:
        mock_service = MockService.return_value
        mock_service.is_enabled.return_value = True
        mock_service.send_to_user = AsyncMock(return_value=False)
        
        # Act
        result = await strategy.deliver(
            session=session,
            user_id=123,
            event_data={"event_type": "test.event"}
        )
        
        # Assert
        assert result.success is False
        assert result.reason == "no_tokens_or_send_failed"


@pytest.mark.asyncio
async def test_push_delivery_title_body_extraction():
    """Test push delivery extracts correct title and body."""
    # Arrange
    strategy = PushNotificationStrategy()
    session = AsyncMock()
    
    with patch('app.modules.push_notifications.services.PushNotificationService') as MockService:
        mock_service = MockService.return_value
        mock_service.is_enabled.return_value = True
        mock_service.send_to_user = AsyncMock(return_value=True)
        
        event_data = {
            "event_type": "incident.created",
            "incident_id": 456,
            "message": "Nueva solicitud de asistencia"
        }
        
        # Act
        await strategy.deliver(
            session=session,
            user_id=123,
            event_data=event_data
        )
        
        # Assert
        call_args = mock_service.send_to_user.call_args
        notification_data = call_args[1]["notification_data"]
        
        assert notification_data.title == "Solicitud recibida"
        assert notification_data.body == "Nueva solicitud de asistencia"
        assert notification_data.data == event_data


# ============================================================================
# HybridDeliveryStrategy Tests
# ============================================================================

@pytest.mark.asyncio
async def test_hybrid_delivery_both_succeed():
    """Test hybrid delivery when both channels succeed."""
    # Arrange
    ws_manager = Mock()
    strategy = HybridDeliveryStrategy(ws_manager)
    
    # Mock both strategies to succeed
    strategy.ws_strategy.deliver = AsyncMock(
        return_value=DeliveryResult(success=True, channel="websocket")
    )
    strategy.push_strategy.deliver = AsyncMock(
        return_value=DeliveryResult(success=True, channel="push")
    )
    
    # Act
    result = await strategy.deliver(
        session=Mock(),
        user_id=123,
        event_data={"event_type": "test.event"}
    )
    
    # Assert
    assert result.success is True
    assert result.channel == "websocket+push"


@pytest.mark.asyncio
async def test_hybrid_delivery_websocket_fails_push_succeeds():
    """Test hybrid delivery when WebSocket fails but FCM succeeds."""
    # Arrange
    ws_manager = Mock()
    strategy = HybridDeliveryStrategy(ws_manager)
    
    strategy.ws_strategy.deliver = AsyncMock(
        return_value=DeliveryResult(success=False, reason="user_offline")
    )
    strategy.push_strategy.deliver = AsyncMock(
        return_value=DeliveryResult(success=True, channel="push")
    )
    
    # Act
    result = await strategy.deliver(
        session=Mock(),
        user_id=123,
        event_data={"event_type": "test.event"}
    )
    
    # Assert
    assert result.success is True
    assert result.channel == "push"


@pytest.mark.asyncio
async def test_hybrid_delivery_websocket_succeeds_push_fails():
    """Test hybrid delivery when WebSocket succeeds but FCM fails."""
    # Arrange
    ws_manager = Mock()
    strategy = HybridDeliveryStrategy(ws_manager)
    
    strategy.ws_strategy.deliver = AsyncMock(
        return_value=DeliveryResult(success=True, channel="websocket")
    )
    strategy.push_strategy.deliver = AsyncMock(
        return_value=DeliveryResult(success=False, reason="no_tokens")
    )
    
    # Act
    result = await strategy.deliver(
        session=Mock(),
        user_id=123,
        event_data={"event_type": "test.event"}
    )
    
    # Assert
    assert result.success is True
    assert result.channel == "websocket"


@pytest.mark.asyncio
async def test_hybrid_delivery_both_fail():
    """Test hybrid delivery when both channels fail."""
    # Arrange
    ws_manager = Mock()
    strategy = HybridDeliveryStrategy(ws_manager)
    
    strategy.ws_strategy.deliver = AsyncMock(
        return_value=DeliveryResult(success=False, reason="user_offline")
    )
    strategy.push_strategy.deliver = AsyncMock(
        return_value=DeliveryResult(success=False, reason="no_tokens")
    )
    
    # Act
    result = await strategy.deliver(
        session=Mock(),
        user_id=123,
        event_data={"event_type": "test.event"}
    )
    
    # Assert
    assert result.success is False
    assert result.reason == "all_channels_failed"


# ============================================================================
# DeliveryStrategyFactory Tests
# ============================================================================

def test_factory_critical_events_return_hybrid():
    """Test factory returns hybrid strategy for critical events."""
    ws_manager = Mock()
    factory = DeliveryStrategyFactory(ws_manager)
    
    critical_events = [
        "incident.created",
        "incident.assigned",
        "incident.technician_arrived",
        "incident.work_completed",
    ]
    
    for event_type in critical_events:
        strategy = factory.get_strategy(event_type)
        assert isinstance(strategy, HybridDeliveryStrategy)


def test_factory_chat_events_return_hybrid():
    """Test factory returns hybrid strategy for chat events."""
    ws_manager = Mock()
    factory = DeliveryStrategyFactory(ws_manager)
    
    strategy = factory.get_strategy("chat.message_sent")
    assert isinstance(strategy, HybridDeliveryStrategy)


def test_factory_notification_events_return_push():
    """Test factory returns push strategy for notification events."""
    ws_manager = Mock()
    factory = DeliveryStrategyFactory(ws_manager)
    
    strategy = factory.get_strategy("notification.received")
    assert isinstance(strategy, PushNotificationStrategy)


def test_factory_unknown_event_returns_hybrid():
    """Test factory returns hybrid strategy for unknown events."""
    ws_manager = Mock()
    factory = DeliveryStrategyFactory(ws_manager)
    
    strategy = factory.get_strategy("unknown.event.type")
    assert isinstance(strategy, HybridDeliveryStrategy)


def test_factory_never_returns_none():
    """Test factory always returns a strategy instance (never None)."""
    ws_manager = Mock()
    factory = DeliveryStrategyFactory(ws_manager)
    
    test_events = [
        "incident.created",
        "chat.message_sent",
        "notification.general",
        "unknown.event",
        "",
    ]
    
    for event_type in test_events:
        strategy = factory.get_strategy(event_type)
        assert strategy is not None
        assert isinstance(strategy, DeliveryStrategy)


def test_factory_reuses_strategy_instances():
    """Test factory reuses strategy instances for efficiency."""
    ws_manager = Mock()
    factory = DeliveryStrategyFactory(ws_manager)
    
    # Get same strategy type multiple times
    strategy1 = factory.get_strategy("incident.created")
    strategy2 = factory.get_strategy("incident.assigned")
    
    # Should be the same instance (both are HYBRID)
    assert strategy1 is strategy2
