"""
Integration tests for OutboxProcessor with Delivery Strategies.

Tests the integration between OutboxProcessor and the delivery strategies,
ensuring proper strategy selection, logging, and retry logic.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime
from app.modules.outbox.processor import OutboxProcessor
from app.modules.outbox.delivery_strategies import (
    DeliveryResult,
    HybridDeliveryStrategy,
    PushNotificationStrategy,
)
from app.models.outbox_event import OutboxEvent, EventPriority


# ============================================================================
# OutboxProcessor Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_outbox_processor_uses_correct_strategy():
    """Test OutboxProcessor selects correct strategy for event types."""
    # Arrange
    ws_manager = Mock()
    processor = OutboxProcessor(ws_manager)
    
    # Test critical event uses hybrid strategy
    strategy = processor.strategy_factory.get_strategy("incident.created")
    assert isinstance(strategy, HybridDeliveryStrategy)
    
    # Test notification event uses push strategy
    strategy = processor.strategy_factory.get_strategy("notification.general")
    assert isinstance(strategy, PushNotificationStrategy)


@pytest.mark.asyncio
async def test_deliver_to_user_uses_strategy():
    """Test _deliver_to_user method uses delivery strategies."""
    # Arrange
    ws_manager = Mock()
    processor = OutboxProcessor(ws_manager)
    session = AsyncMock()
    
    outbox_event = OutboxEvent(
        event_id="test-123",
        event_type="incident.created",
        payload='{"incident_id": 456}',
        priority=EventPriority.HIGH,
        processed=False
    )
    
    event_data = {"event_type": "incident.created", "incident_id": 456}
    
    # Mock strategy to return success
    mock_strategy = Mock()
    mock_strategy.deliver = AsyncMock(
        return_value=DeliveryResult(success=True, channel="websocket")
    )
    processor.strategy_factory.get_strategy = Mock(return_value=mock_strategy)
    
    # Mock _log_delivery
    processor._log_delivery = AsyncMock()
    
    # Act
    result = await processor._deliver_to_user(
        session=session,
        outbox_event=outbox_event,
        user_id=123,
        event_data=event_data
    )
    
    # Assert
    assert result is True
    mock_strategy.deliver.assert_called_once_with(session, 123, event_data)
    processor._log_delivery.assert_called_once()


@pytest.mark.asyncio
async def test_deliver_to_user_logs_on_success():
    """Test _deliver_to_user logs delivery on success."""
    # Arrange
    ws_manager = Mock()
    processor = OutboxProcessor(ws_manager)
    session = AsyncMock()
    
    outbox_event = OutboxEvent(
        event_id="test-123",
        event_type="incident.created",
        payload='{"incident_id": 456}',
        priority=EventPriority.HIGH,
        processed=False
    )
    
    event_data = {"event_type": "incident.created", "incident_id": 456}
    
    # Mock strategy to return success
    mock_strategy = Mock()
    mock_strategy.deliver = AsyncMock(
        return_value=DeliveryResult(success=True, channel="websocket+push")
    )
    processor.strategy_factory.get_strategy = Mock(return_value=mock_strategy)
    
    # Mock _log_delivery
    processor._log_delivery = AsyncMock()
    
    # Act
    await processor._deliver_to_user(
        session=session,
        outbox_event=outbox_event,
        user_id=123,
        event_data=event_data
    )
    
    # Assert
    processor._log_delivery.assert_called_once_with(
        session,
        outbox_event,
        123,
        "websocket+push"
    )


@pytest.mark.asyncio
async def test_deliver_to_user_no_log_on_failure():
    """Test _deliver_to_user does NOT log delivery on failure."""
    # Arrange
    ws_manager = Mock()
    processor = OutboxProcessor(ws_manager)
    session = AsyncMock()
    
    outbox_event = OutboxEvent(
        event_id="test-123",
        event_type="incident.created",
        payload='{"incident_id": 456}',
        priority=EventPriority.HIGH,
        processed=False
    )
    
    event_data = {"event_type": "incident.created", "incident_id": 456}
    
    # Mock strategy to return failure
    mock_strategy = Mock()
    mock_strategy.deliver = AsyncMock(
        return_value=DeliveryResult(success=False, reason="all_channels_failed")
    )
    processor.strategy_factory.get_strategy = Mock(return_value=mock_strategy)
    
    # Mock _log_delivery
    processor._log_delivery = AsyncMock()
    
    # Act
    result = await processor._deliver_to_user(
        session=session,
        outbox_event=outbox_event,
        user_id=123,
        event_data=event_data
    )
    
    # Assert
    assert result is False
    processor._log_delivery.assert_not_called()


@pytest.mark.asyncio
async def test_deliver_to_user_returns_boolean():
    """Test _deliver_to_user returns boolean success status."""
    # Arrange
    ws_manager = Mock()
    processor = OutboxProcessor(ws_manager)
    session = AsyncMock()
    
    outbox_event = OutboxEvent(
        event_id="test-123",
        event_type="incident.created",
        payload='{"incident_id": 456}',
        priority=EventPriority.HIGH,
        processed=False
    )
    
    event_data = {"event_type": "incident.created", "incident_id": 456}
    
    # Mock _log_delivery
    processor._log_delivery = AsyncMock()
    
    # Test success case
    mock_strategy = Mock()
    mock_strategy.deliver = AsyncMock(
        return_value=DeliveryResult(success=True, channel="websocket")
    )
    processor.strategy_factory.get_strategy = Mock(return_value=mock_strategy)
    
    result = await processor._deliver_to_user(
        session=session,
        outbox_event=outbox_event,
        user_id=123,
        event_data=event_data
    )
    assert result is True
    
    # Test failure case
    mock_strategy.deliver = AsyncMock(
        return_value=DeliveryResult(success=False, reason="user_offline")
    )
    
    result = await processor._deliver_to_user(
        session=session,
        outbox_event=outbox_event,
        user_id=123,
        event_data=event_data
    )
    assert result is False


@pytest.mark.asyncio
async def test_deliver_to_user_publishes_message_delivered_event():
    """Test _deliver_to_user publishes chat.message_delivered for chat events."""
    # Arrange
    ws_manager = Mock()
    processor = OutboxProcessor(ws_manager)
    session = AsyncMock()
    
    outbox_event = OutboxEvent(
        event_id="test-123",
        event_type="chat.message_sent",
        payload='{"message_id": 789}',
        priority=EventPriority.MEDIUM,
        processed=False
    )
    
    event_data = {
        "event_type": "chat.message_sent",
        "message_id": 789
    }
    
    # Mock strategy to return success
    mock_strategy = Mock()
    mock_strategy.deliver = AsyncMock(
        return_value=DeliveryResult(success=True, channel="websocket")
    )
    processor.strategy_factory.get_strategy = Mock(return_value=mock_strategy)
    
    # Mock methods
    processor._log_delivery = AsyncMock()
    processor._publish_message_delivered_event = AsyncMock()
    
    # Act
    await processor._deliver_to_user(
        session=session,
        outbox_event=outbox_event,
        user_id=123,
        event_data=event_data
    )
    
    # Assert
    processor._publish_message_delivered_event.assert_called_once_with(
        session,
        event_data,
        123,
        "websocket"  # delivered_via channel
    )


@pytest.mark.asyncio
async def test_no_assumed_delivery_logic_remains():
    """
    CRITICAL TEST: Verify no "assumed delivery" logic remains.
    
    This test ensures that the OutboxProcessor never logs delivery
    without verifying success from the delivery strategy.
    """
    # Arrange
    ws_manager = Mock()
    processor = OutboxProcessor(ws_manager)
    session = AsyncMock()
    
    outbox_event = OutboxEvent(
        event_id="test-123",
        event_type="incident.created",
        payload='{"incident_id": 456}',
        priority=EventPriority.HIGH,
        processed=False
    )
    
    event_data = {"event_type": "incident.created", "incident_id": 456}
    
    # Mock strategy to return failure
    mock_strategy = Mock()
    mock_strategy.deliver = AsyncMock(
        return_value=DeliveryResult(success=False, reason="all_channels_failed")
    )
    processor.strategy_factory.get_strategy = Mock(return_value=mock_strategy)
    
    # Mock _log_delivery to track calls
    processor._log_delivery = AsyncMock()
    
    # Act
    result = await processor._deliver_to_user(
        session=session,
        outbox_event=outbox_event,
        user_id=123,
        event_data=event_data
    )
    
    # Assert: MUST NOT log delivery when strategy reports failure
    assert result is False
    processor._log_delivery.assert_not_called()
    
    # This is the critical assertion: no delivery log = no assumed delivery


@pytest.mark.asyncio
async def test_strategy_factory_initialized_with_ws_manager():
    """Test OutboxProcessor initializes strategy factory with ws_manager."""
    # Arrange
    ws_manager = Mock()
    
    # Act
    processor = OutboxProcessor(ws_manager)
    
    # Assert
    assert processor.strategy_factory is not None
    assert processor.strategy_factory.ws_manager is ws_manager
