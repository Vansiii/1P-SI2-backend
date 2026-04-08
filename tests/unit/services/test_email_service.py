"""
Tests para EmailService.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.notifications.service import EmailService, get_email_provider
from app.modules.notifications.providers import BrevoSMTPProvider, BrevoAPIProvider
from app.core.exceptions import ValidationException


@pytest.fixture
def email_service():
    """Fixture del servicio de email."""
    with patch('app.modules.notifications.service.get_email_provider') as mock_provider:
        mock_provider.return_value = AsyncMock()
        return EmailService()


@pytest.mark.asyncio
class TestEmailService:
    """Tests para EmailService."""

    async def test_send_welcome_email_success(self, email_service):
        """Test de envío exitoso de email de bienvenida."""
        # Arrange
        to_email = "user@test.com"
        user_name = "John Doe"
        user_type = "client"
        
        mock_provider = AsyncMock()
        mock_provider.send_email.return_value = True
        
        with patch.object(email_service, '_provider', mock_provider):
            # Act
            result = await email_service.send_welcome_email(to_email, user_name, user_type)
            
            # Assert
            assert result is True
            mock_provider.send_email.assert_called_once()
            call_args = mock_provider.send_email.call_args
            assert call_args[1]['to'] == to_email
            assert 'Welcome' in call_args[1]['subject']

    async def test_send_password_reset_email_success(self, email_service):
        """Test de envío exitoso de email de recuperación de contraseña."""
        # Arrange
        to_email = "user@test.com"
        reset_token = "abc123token"
        user_name = "John Doe"
        
        mock_provider = AsyncMock()
        mock_provider.send_email.return_value = True
        
        with patch.object(email_service, '_provider', mock_provider):
            # Act
            result = await email_service.send_password_reset_email(to_email, reset_token, user_name)
            
            # Assert
            assert result is True
            mock_provider.send_email.assert_called_once()
            call_args = mock_provider.send_email.call_args
            assert reset_token in call_args[1]['html']

    async def test_send_otp_email_success(self, email_service):
        """Test de envío exitoso de email con código OTP."""
        # Arrange
        to_email = "user@test.com"
        otp_code = "123456"
        user_name = "John Doe"
        
        mock_provider = AsyncMock()
        mock_provider.send_email.return_value = True
        
        with patch.object(email_service, '_provider', mock_provider):
            # Act
            result = await email_service.send_otp_email(to_email, otp_code, user_name)
            
            # Assert
            assert result is True
            mock_provider.send_email.assert_called_once()
            call_args = mock_provider.send_email.call_args
            assert otp_code in call_args[1]['html']

    async def test_send_password_changed_email_success(self, email_service):
        """Test de envío exitoso de email de cambio de contraseña."""
        # Arrange
        to_email = "user@test.com"
        user_name = "John Doe"
        
        mock_provider = AsyncMock()
        mock_provider.send_email.return_value = True
        
        with patch.object(email_service, '_provider', mock_provider):
            # Act
            result = await email_service.send_password_changed_email(to_email, user_name)
            
            # Assert
            assert result is True
            mock_provider.send_email.assert_called_once()

    async def test_send_account_unlocked_email_success(self, email_service):
        """Test de envío exitoso de email de desbloqueo de cuenta."""
        # Arrange
        to_email = "user@test.com"
        user_name = "John Doe"
        
        mock_provider = AsyncMock()
        mock_provider.send_email.return_value = True
        
        with patch.object(email_service, '_provider', mock_provider):
            # Act
            result = await email_service.send_account_unlocked_email(to_email, user_name)
            
            # Assert
            assert result is True
            mock_provider.send_email.assert_called_once()

    async def test_send_email_with_retry_on_failure(self, email_service):
        """Test de reintento en caso de fallo."""
        # Arrange
        to_email = "user@test.com"
        user_name = "John Doe"
        
        mock_provider = AsyncMock()
        # Primer intento falla, segundo intento exitoso
        mock_provider.send_email.side_effect = [Exception("Connection error"), True]
        
        with patch.object(email_service, '_provider', mock_provider):
            # Act
            result = await email_service.send_welcome_email(to_email, user_name, "client")
            
            # Assert
            assert result is True
            assert mock_provider.send_email.call_count == 2

    async def test_send_email_fails_after_max_retries(self, email_service):
        """Test de fallo después de máximo de reintentos."""
        # Arrange
        to_email = "user@test.com"
        user_name = "John Doe"
        
        mock_provider = AsyncMock()
        mock_provider.send_email.side_effect = Exception("Connection error")
        
        with patch.object(email_service, '_provider', mock_provider):
            # Act
            result = await email_service.send_welcome_email(to_email, user_name, "client")
            
            # Assert
            assert result is False
            assert mock_provider.send_email.call_count == 3  # 3 intentos

    async def test_send_email_with_invalid_email(self, email_service):
        """Test de envío con email inválido."""
        # Arrange
        to_email = "invalid-email"
        user_name = "John Doe"
        
        # Act & Assert
        with pytest.raises(ValidationException, match="Invalid email address"):
            await email_service.send_welcome_email(to_email, user_name, "client")

    async def test_get_email_provider_smtp(self):
        """Test de obtención de proveedor SMTP."""
        # Arrange
        with patch('app.modules.notifications.service.settings') as mock_settings:
            mock_settings.EMAIL_PROVIDER = "smtp"
            mock_settings.BREVO_SMTP_HOST = "smtp.example.com"
            mock_settings.BREVO_SMTP_PORT = 587
            mock_settings.BREVO_SMTP_USER = "user"
            mock_settings.BREVO_SMTP_PASSWORD = "pass"
            
            # Act
            provider = get_email_provider()
            
            # Assert
            assert isinstance(provider, BrevoSMTPProvider)

    async def test_get_email_provider_api(self):
        """Test de obtención de proveedor API."""
        # Arrange
        with patch('app.modules.notifications.service.settings') as mock_settings:
            mock_settings.EMAIL_PROVIDER = "api"
            mock_settings.BREVO_API_KEY = "api_key_123"
            
            # Act
            provider = get_email_provider()
            
            # Assert
            assert isinstance(provider, BrevoAPIProvider)

    async def test_email_templates_contain_required_fields(self, email_service):
        """Test que verifica que los templates contienen campos requeridos."""
        # Arrange
        mock_provider = AsyncMock()
        mock_provider.send_email.return_value = True
        
        with patch.object(email_service, '_provider', mock_provider):
            # Act
            await email_service.send_welcome_email("user@test.com", "John", "client")
            
            # Assert
            call_args = mock_provider.send_email.call_args[1]
            assert 'to' in call_args
            assert 'subject' in call_args
            assert 'html' in call_args
            assert 'text' in call_args

    async def test_send_email_logs_success(self, email_service):
        """Test que verifica el logging de envío exitoso."""
        # Arrange
        to_email = "user@test.com"
        user_name = "John Doe"
        
        mock_provider = AsyncMock()
        mock_provider.send_email.return_value = True
        
        with patch.object(email_service, '_provider', mock_provider):
            with patch('app.modules.notifications.service.logger') as mock_logger:
                # Act
                await email_service.send_welcome_email(to_email, user_name, "client")
                
                # Assert
                mock_logger.info.assert_called()

    async def test_send_email_logs_failure(self, email_service):
        """Test que verifica el logging de fallo de envío."""
        # Arrange
        to_email = "user@test.com"
        user_name = "John Doe"
        
        mock_provider = AsyncMock()
        mock_provider.send_email.side_effect = Exception("SMTP error")
        
        with patch.object(email_service, '_provider', mock_provider):
            with patch('app.modules.notifications.service.logger') as mock_logger:
                # Act
                await email_service.send_welcome_email(to_email, user_name, "client")
                
                # Assert
                mock_logger.error.assert_called()
