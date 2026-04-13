"""
Integration test for welcome email functionality.
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.modules.auth.services import RegistrationService
from app.modules.auth.schemas import ClientRegistrationRequest
from app.core.constants import UserType


@pytest.mark.asyncio
class TestWelcomeEmailIntegration:
    """Test welcome email is sent during registration."""
    
    async def test_register_client_sends_welcome_email(self, db_session):
        """Test that registering a client sends a welcome email."""
        # Arrange
        registration_service = RegistrationService(db_session)
        
        request = ClientRegistrationRequest(
            email="newclient@test.com",
            password="SecurePass123!",
            direccion="Calle Test 123",
            ci="12345678",
            fecha_nacimiento="1990-01-01"
        )
        
        # Mock the notification service to verify it's called
        with patch('app.modules.auth.services.NotificationService') as mock_notification_class:
            mock_notification_instance = AsyncMock()
            mock_notification_instance.send_welcome_email = AsyncMock(return_value=True)
            mock_notification_class.return_value = mock_notification_instance
            
            # Act
            client, token_response = await registration_service.register_client(request)
            
            # Assert
            assert client is not None
            assert client.email == "newclient@test.com"
            assert client.user_type == UserType.CLIENT
            
            # Verify welcome email was sent
            mock_notification_instance.send_welcome_email.assert_called_once()
            call_args = mock_notification_instance.send_welcome_email.call_args
            
            assert call_args.kwargs['to_email'] == "newclient@test.com"
            assert call_args.kwargs['user_type'] == "Cliente"
            assert 'user_name' in call_args.kwargs
    
    async def test_register_client_continues_if_email_fails(self, db_session):
        """Test that registration succeeds even if welcome email fails."""
        # Arrange
        registration_service = RegistrationService(db_session)
        
        request = ClientRegistrationRequest(
            email="anotherclient@test.com",
            password="SecurePass123!",
            direccion="Calle Test 456",
            ci="87654321",
            fecha_nacimiento="1995-05-15"
        )
        
        # Mock the notification service to raise an exception
        with patch('app.modules.auth.services.NotificationService') as mock_notification_class:
            mock_notification_instance = AsyncMock()
            mock_notification_instance.send_welcome_email = AsyncMock(
                side_effect=Exception("Email service unavailable")
            )
            mock_notification_class.return_value = mock_notification_instance
            
            # Act - should not raise exception
            client, token_response = await registration_service.register_client(request)
            
            # Assert - registration should succeed
            assert client is not None
            assert client.email == "anotherclient@test.com"
            assert token_response.access_token is not None
            
            # Verify email was attempted
            mock_notification_instance.send_welcome_email.assert_called_once()
