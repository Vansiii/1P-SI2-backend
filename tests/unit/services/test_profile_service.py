"""
Tests para ProfileService.
"""
import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.service import ProfileService
from app.modules.auth.schemas import UpdateProfileRequest, DeleteAccountRequest
from app.models.client import Client
from app.models.workshop import Workshop
from app.core.exceptions import ValidationException, AuthenticationException


@pytest.fixture
def mock_db():
    """Mock de sesión de base de datos."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def profile_service(mock_db):
    """Fixture del servicio de perfil."""
    return ProfileService(mock_db)


@pytest.mark.asyncio
class TestProfileService:
    """Tests para ProfileService."""

    async def test_get_profile_client(self, profile_service, mock_db):
        """Test de obtención de perfil de cliente."""
        # Arrange
        user = Client(
            id=1,
            email="client@test.com",
            first_name="John",
            last_name="Doe",
            phone="+1234567890",
            is_active=True
        )
        
        # Act
        result = await profile_service.get_profile(user, "client")
        
        # Assert
        assert result["email"] == user.email
        assert result["first_name"] == user.first_name
        assert result["user_type"] == "client"

    async def test_get_profile_workshop(self, profile_service, mock_db):
        """Test de obtención de perfil de taller."""
        # Arrange
        user = Workshop(
            id=1,
            email="workshop@test.com",
            name="Test Workshop",
            phone="+1234567890",
            address="123 Main St",
            is_active=True
        )
        
        # Act
        result = await profile_service.get_profile(user, "workshop")
        
        # Assert
        assert result["email"] == user.email
        assert result["name"] == user.name
        assert result["user_type"] == "workshop"

    async def test_update_profile_success(self, profile_service, mock_db):
        """Test de actualización exitosa de perfil."""
        # Arrange
        user = Client(
            id=1,
            email="client@test.com",
            first_name="John",
            last_name="Doe",
            is_active=True
        )
        
        request = UpdateProfileRequest(
            first_name="Jane",
            last_name="Smith",
            phone="+9876543210"
        )
        
        mock_user_repo = AsyncMock()
        mock_user_repo.update.return_value = Client(
            id=1,
            email=user.email,
            first_name=request.first_name,
            last_name=request.last_name,
            phone=request.phone,
            is_active=True
        )
        
        with patch.object(profile_service, '_user_repo', mock_user_repo):
            # Act
            result = await profile_service.update_profile(user, request, "client")
            
            # Assert
            assert result["first_name"] == request.first_name
            assert result["last_name"] == request.last_name
            assert result["phone"] == request.phone
            mock_user_repo.update.assert_called_once()

    async def test_update_profile_email_not_allowed(self, profile_service, mock_db):
        """Test que verifica que no se puede cambiar el email."""
        # Arrange
        user = Client(id=1, email="client@test.com", is_active=True)
        request = UpdateProfileRequest(email="newemail@test.com")
        
        # Act & Assert
        with pytest.raises(ValidationException, match="Email cannot be changed"):
            await profile_service.update_profile(user, request, "client")

    async def test_delete_account_success(self, profile_service, mock_db):
        """Test de eliminación exitosa de cuenta."""
        # Arrange
        user = Client(
            id=1,
            email="client@test.com",
            password_hash="hashed_password",
            is_active=True
        )
        
        request = DeleteAccountRequest(password="correct_password")
        
        mock_user_repo = AsyncMock()
        mock_user_repo.update.return_value = user
        
        with patch.object(profile_service, '_user_repo', mock_user_repo):
            with patch('app.modules.users.service.verify_password', return_value=True):
                with patch('app.modules.users.service.revoke_all_user_tokens', new_callable=AsyncMock):
                    # Act
                    result = await profile_service.delete_account(user, request, "client")
                    
                    # Assert
                    assert result["message"] == "Account deleted successfully"
                    mock_user_repo.update.assert_called_once()

    async def test_delete_account_wrong_password(self, profile_service, mock_db):
        """Test de eliminación con contraseña incorrecta."""
        # Arrange
        user = Client(
            id=1,
            email="client@test.com",
            password_hash="hashed_password",
            is_active=True
        )
        
        request = DeleteAccountRequest(password="wrong_password")
        
        with patch('app.modules.users.service.verify_password', return_value=False):
            # Act & Assert
            with pytest.raises(AuthenticationException, match="Invalid password"):
                await profile_service.delete_account(user, request, "client")

    async def test_delete_account_sends_confirmation_email(self, profile_service, mock_db):
        """Test que verifica el envío de email de confirmación."""
        # Arrange
        user = Client(
            id=1,
            email="client@test.com",
            password_hash="hashed_password",
            is_active=True
        )
        
        request = DeleteAccountRequest(password="correct_password")
        
        mock_user_repo = AsyncMock()
        mock_user_repo.update.return_value = user
        mock_email_service = AsyncMock()
        
        with patch.object(profile_service, '_user_repo', mock_user_repo):
            with patch('app.modules.users.service.verify_password', return_value=True):
                with patch('app.modules.users.service.revoke_all_user_tokens', new_callable=AsyncMock):
                    with patch('app.modules.users.service.send_account_deletion_email', mock_email_service):
                        # Act
                        await profile_service.delete_account(user, request, "client")
                        
                        # Assert
                        mock_email_service.assert_called_once()

    async def test_update_profile_with_2fa_info(self, profile_service, mock_db):
        """Test que incluye información de 2FA en el perfil."""
        # Arrange
        user = Client(
            id=1,
            email="client@test.com",
            first_name="John",
            last_name="Doe",
            is_active=True
        )
        
        mock_2fa_repo = AsyncMock()
        mock_2fa_repo.get_2fa_status.return_value = {"enabled": True, "verified": True}
        
        with patch.object(profile_service, '_2fa_repo', mock_2fa_repo):
            # Act
            result = await profile_service.get_profile(user, "client")
            
            # Assert
            assert "two_factor_enabled" in result
