"""
Unit tests for WebSocket event emission helpers.

Tests verify:
- Standardized payload structure (type, data, timestamp, version)
- Error handling (WebSocket failures don't break operations)
- Helper functions: emit_to_user, emit_to_incident_room, emit_to_admins
- Event type constants
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from app.core.websocket_events import (
    _build_event_payload,
    emit_to_user,
    emit_to_incident_room,
    emit_to_admins,
    emit_to_all,
    emit_to_users,
    EventTypes,
    EVENT_VERSION
)


class TestBuildEventPayload:
    """Test standardized event payload structure."""
    
    def test_payload_structure(self):
        """Verify payload has required fields: type, data, timestamp, version."""
        event_type = "test_event"
        data = {"key": "value"}
        
        payload = _build_event_payload(event_type, data)
        
        assert "type" in payload
        assert "data" in payload
        assert "timestamp" in payload
        assert "version" in payload
        
        assert payload["type"] == event_type
        assert payload["data"] == data
        assert payload["version"] == EVENT_VERSION
    
    def test_timestamp_format(self):
        """Verify timestamp is ISO8601 format."""
        payload = _build_event_payload("test", {})
        
        # Should be parseable as ISO8601
        timestamp = datetime.fromisoformat(payload["timestamp"])
        assert isinstance(timestamp, datetime)
    
    def test_version_field(self):
        """Verify version field is included for future compatibility."""
        payload = _build_event_payload("test", {})
        
        assert payload["version"] == "1.0"


class TestEmitToUser:
    """Test personal message emission to specific user."""
    
    @pytest.mark.asyncio
    async def test_emit_to_user_success(self):
        """Verify emit_to_user sends message to specific user."""
        with patch('app.core.websocket_events.ws_manager') as mock_manager:
            mock_manager.send_personal_message = AsyncMock()
            
            user_id = 50
            event_type = "vehicle_created"
            data = {"vehicle_id": 123, "marca": "Toyota"}
            
            result = await emit_to_user(user_id, event_type, data)
            
            assert result is True
            mock_manager.send_personal_message.assert_called_once()
            
            # Verify payload structure
            call_args = mock_manager.send_personal_message.call_args
            assert call_args[0][0] == user_id
            payload = call_args[0][1]
            assert payload["type"] == event_type
            assert payload["data"] == data
    
    @pytest.mark.asyncio
    async def test_emit_to_user_failure_does_not_raise(self):
        """Verify WebSocket failure doesn't break main operation (REQ-18)."""
        with patch('app.core.websocket_events.ws_manager') as mock_manager:
            mock_manager.send_personal_message = AsyncMock(
                side_effect=Exception("WebSocket connection lost")
            )
            
            # Should not raise exception
            result = await emit_to_user(50, "test_event", {})
            
            # Should return False to indicate failure
            assert result is False


class TestEmitToIncidentRoom:
    """Test broadcast to incident room."""
    
    @pytest.mark.asyncio
    async def test_emit_to_incident_room_success(self):
        """Verify emit_to_incident_room broadcasts to all users in room."""
        with patch('app.core.websocket_events.ws_manager') as mock_manager:
            mock_manager.broadcast_to_incident = AsyncMock()
            
            incident_id = 40
            event_type = "evidence_uploaded"
            data = {"evidence_id": 789, "file_url": "https://..."}
            
            result = await emit_to_incident_room(incident_id, event_type, data)
            
            assert result is True
            mock_manager.broadcast_to_incident.assert_called_once()
            
            # Verify call arguments
            call_args = mock_manager.broadcast_to_incident.call_args
            assert call_args[0][0] == incident_id
            payload = call_args[0][1]
            assert payload["type"] == event_type
            assert payload["data"] == data
    
    @pytest.mark.asyncio
    async def test_emit_to_incident_room_with_exclude(self):
        """Verify exclude_user parameter works correctly."""
        with patch('app.core.websocket_events.ws_manager') as mock_manager:
            mock_manager.broadcast_to_incident = AsyncMock()
            
            incident_id = 40
            exclude_user = 50
            
            await emit_to_incident_room(
                incident_id, 
                "new_chat_message", 
                {"message": "Hello"},
                exclude_user=exclude_user
            )
            
            # Verify exclude_user is passed
            call_args = mock_manager.broadcast_to_incident.call_args
            assert call_args[0][2] == exclude_user
    
    @pytest.mark.asyncio
    async def test_emit_to_incident_room_failure_does_not_raise(self):
        """Verify WebSocket failure doesn't break main operation (REQ-18)."""
        with patch('app.core.websocket_events.ws_manager') as mock_manager:
            mock_manager.broadcast_to_incident = AsyncMock(
                side_effect=Exception("Broadcast failed")
            )
            
            # Should not raise exception
            result = await emit_to_incident_room(40, "test_event", {})
            
            # Should return False to indicate failure
            assert result is False


class TestEmitToAdmins:
    """Test broadcast to administrators."""
    
    @pytest.mark.asyncio
    async def test_emit_to_admins_success(self):
        """Verify emit_to_admins broadcasts to all admin users."""
        with patch('app.core.websocket_events.ws_manager') as mock_manager:
            mock_manager.broadcast_to_admins = AsyncMock()
            
            event_type = "audit_log_created"
            data = {"log_id": 456, "action": "user_login"}
            
            result = await emit_to_admins(event_type, data)
            
            assert result is True
            mock_manager.broadcast_to_admins.assert_called_once()
            
            # Verify payload
            call_args = mock_manager.broadcast_to_admins.call_args
            payload = call_args[0][0]
            assert payload["type"] == event_type
            assert payload["data"] == data
    
    @pytest.mark.asyncio
    async def test_emit_to_admins_failure_does_not_raise(self):
        """Verify WebSocket failure doesn't break main operation (REQ-18)."""
        with patch('app.core.websocket_events.ws_manager') as mock_manager:
            mock_manager.broadcast_to_admins = AsyncMock(
                side_effect=Exception("Admin broadcast failed")
            )
            
            # Should not raise exception
            result = await emit_to_admins("test_event", {})
            
            # Should return False to indicate failure
            assert result is False


class TestEmitToAll:
    """Test global broadcast to all users."""
    
    @pytest.mark.asyncio
    async def test_emit_to_all_success(self):
        """Verify emit_to_all broadcasts to all connected users."""
        with patch('app.core.websocket_events.ws_manager') as mock_manager:
            mock_manager.broadcast_to_all = AsyncMock()
            
            event_type = "system_maintenance"
            data = {"message": "System maintenance in 10 minutes"}
            
            result = await emit_to_all(event_type, data)
            
            assert result is True
            mock_manager.broadcast_to_all.assert_called_once()


class TestEmitToUsers:
    """Test emission to multiple specific users."""
    
    @pytest.mark.asyncio
    async def test_emit_to_users_success(self):
        """Verify emit_to_users sends to multiple users."""
        with patch('app.core.websocket_events.ws_manager') as mock_manager:
            mock_manager.send_personal_message = AsyncMock()
            
            user_ids = [50, 51, 52]
            event_type = "notification_created"
            data = {"notification_id": 123}
            
            results = await emit_to_users(user_ids, event_type, data)
            
            # Should call send_personal_message for each user
            assert mock_manager.send_personal_message.call_count == 3
            
            # All should succeed
            assert all(results.values())
            assert len(results) == 3
    
    @pytest.mark.asyncio
    async def test_emit_to_users_partial_failure(self):
        """Verify partial failures are tracked correctly."""
        with patch('app.core.websocket_events.ws_manager') as mock_manager:
            # First call succeeds, second fails, third succeeds
            mock_manager.send_personal_message = AsyncMock(
                side_effect=[None, Exception("Failed"), None]
            )
            
            user_ids = [50, 51, 52]
            results = await emit_to_users(user_ids, "test_event", {})
            
            # Should have results for all users
            assert len(results) == 3
            assert results[50] is True
            assert results[51] is False
            assert results[52] is True


class TestEventTypes:
    """Test event type constants (REQ-14)."""
    
    def test_event_naming_convention(self):
        """Verify event names follow {entity}_{action} pattern."""
        # Test a few key event types
        assert EventTypes.INCIDENT_CREATED == "incident_created"
        assert EventTypes.TECHNICIAN_ASSIGNED == "technician_assigned"
        assert EventTypes.VEHICLE_UPDATED == "vehicle_updated"
        assert EventTypes.WORKSHOP_VERIFIED == "workshop_verified"
    
    def test_event_names_use_snake_case(self):
        """Verify all event names use snake_case (REQ-14)."""
        # Get all event type constants
        event_types = [
            getattr(EventTypes, attr) 
            for attr in dir(EventTypes) 
            if not attr.startswith('_')
        ]
        
        for event_type in event_types:
            # Should be lowercase with underscores
            assert event_type == event_type.lower()
            assert ' ' not in event_type
            assert '-' not in event_type
    
    def test_event_names_use_past_tense(self):
        """Verify completed actions use past tense (REQ-14)."""
        # Test key completed action events
        assert EventTypes.INCIDENT_CREATED.endswith("created")
        assert EventTypes.TECHNICIAN_ASSIGNED.endswith("assigned")
        assert EventTypes.WORKSHOP_VERIFIED.endswith("verified")
        assert EventTypes.EVIDENCE_UPLOADED.endswith("uploaded")


class TestErrorHandling:
    """Test error handling and resilience (REQ-18)."""
    
    @pytest.mark.asyncio
    async def test_all_functions_handle_exceptions(self):
        """Verify all emit functions handle exceptions gracefully."""
        with patch('app.core.websocket_events.ws_manager') as mock_manager:
            # Make all WebSocket operations fail
            mock_manager.send_personal_message = AsyncMock(
                side_effect=Exception("Connection lost")
            )
            mock_manager.broadcast_to_incident = AsyncMock(
                side_effect=Exception("Broadcast failed")
            )
            mock_manager.broadcast_to_admins = AsyncMock(
                side_effect=Exception("Admin broadcast failed")
            )
            mock_manager.broadcast_to_all = AsyncMock(
                side_effect=Exception("Global broadcast failed")
            )
            
            # None of these should raise exceptions
            result1 = await emit_to_user(50, "test", {})
            result2 = await emit_to_incident_room(40, "test", {})
            result3 = await emit_to_admins("test", {})
            result4 = await emit_to_all("test", {})
            
            # All should return False to indicate failure
            assert result1 is False
            assert result2 is False
            assert result3 is False
            assert result4 is False


class TestRequirementCompliance:
    """Test compliance with specific requirements."""
    
    def test_req_14_naming_convention(self):
        """REQ-14: Event naming follows {entity}_{action} pattern."""
        # Verify key events follow the pattern
        assert "incident" in EventTypes.INCIDENT_CREATED
        assert "created" in EventTypes.INCIDENT_CREATED
        
        assert "technician" in EventTypes.TECHNICIAN_ASSIGNED
        assert "assigned" in EventTypes.TECHNICIAN_ASSIGNED
    
    def test_req_15_payload_structure(self):
        """REQ-15: Payload structure is { type, data, timestamp, version }."""
        payload = _build_event_payload("test_event", {"key": "value"})
        
        # Must have exactly these root-level fields
        required_fields = {"type", "data", "timestamp", "version"}
        assert set(payload.keys()) == required_fields
    
    @pytest.mark.asyncio
    async def test_req_18_error_handling(self):
        """REQ-18: WebSocket failures never break main operation."""
        with patch('app.core.websocket_events.ws_manager') as mock_manager:
            mock_manager.send_personal_message = AsyncMock(
                side_effect=Exception("Simulated failure")
            )
            
            # This should not raise an exception
            try:
                result = await emit_to_user(50, "test", {})
                # Should return False but not raise
                assert result is False
            except Exception:
                pytest.fail("emit_to_user raised an exception when it should have caught it")
