"""
Tests para RegistrationService.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.service import RegistrationService
from app.modules.auth.schemas import (
    ClientRegistrationRequest,
    WorkshopRegistrationRequest,
    TechnicianRegistrationRequest,
    AdministratorRegistrationRequest,
)
from app.models.client import Client
from app.models.workshop import Workshop
from app.models.technician import Technician
from app.models.administrator import Administrator
from app.core.exceptions import ValidationException


@pytest.fixture
def mock_db():
    """Mock de sesión de base de datos."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def registration_service(mock_db):
    """Fixture del servicio de registro."""
    return RegistrationService(mock_db)


@pytest.mark.asyncio
class TestRegistrationService:
    """Tests para RegistrationService."""

    async def test_register_client_success(self, registration_service, mock_db):
        """Test de registro exitoso de cliente."""
        # Arrange
        request = ClientRegistrationRequest(
            email="client@test.com",
            password="SecurePass123!",
            first_name="John",
            last_name="Doe",
            phone="+1234567890"
        )
        
        mock_user_repo = AsyncMock()
        mock_user_repo.find_by_email.return_value = None
        mock_user_repo.create.return_value = Client(
            id=1,
            email=request.email,
            first_name=request.first_name,
            last_name=request.last_name,
            phone=request.phone,
            is_active=True
        )
        
        with patch.object(registration_service, '_user_repo', mock_user_repo):
            with patch('app.modules.users.service.hash_password', return_value="hashed_password"):
                with patch('app.modules.users.service.create_token_pair', return_value={"access_token": "token", "refresh_token": "refresh"}):
                    # Act
                    result = await registration_service.register_client(request)
                    
                    # Assert
                    assert result["user"]["email"] == request.email
                    assert "access_token" in result
                    assert "refresh_token" in result
                    mock_user_repo.find_by_email.assert_called_once_with(request.email)
                    mock_user_repo.create.assert_called_once()

    async def test_register_client_duplicate_email(self, registration_service, mock_db):
        """Test de registro con email duplicado."""
        # Arrange
        request = ClientRegistrationRequest(
            email="existing@test.com",
            password="SecurePass123!",
            first_name="John",
            last_name="Doe",
            phone="+1234567890"
        )
        
        mock_user_repo = AsyncMock()
        mock_user_repo.find_by_email.return_value = Client(id=1, email=request.email)
        
        with patch.object(registration_service, '_user_repo', mock_user_repo):
            # Act & Assert
            with pytest.raises(ValidationException, match="Email already registered"):
                await registration_service.register_client(request)

    async def test_register_workshop_success(self, registration_service, mock_db):
        """Test de registro exitoso de taller."""
        # Arrange
        request = WorkshopRegistrationRequest(
            email="workshop@test.com",
            password="SecurePass123!",
            name="Test Workshop",
            phone="+1234567890",
            address="123 Main St"
        )
        
        mock_user_repo = AsyncMock()
        mock_user_repo.find_by_email.return_value = None
        mock_user_repo.create.return_value = Workshop(
            id=1,
            email=request.email,
            name=request.name,
            phone=request.phone,
            address=request.address,
            is_active=True
        )
        
        with patch.object(registration_service, '_user_repo', mock_user_repo):
            with patch('app.modules.users.service.hash_password', return_value="hashed_password"):
                with patch('app.modules.users.service.create_token_pair', return_value={"access_token": "token", "refresh_token": "refresh"}):
                    # Act
                    result = await registration_service.register_workshop(request)
                    
                    # Assert
                    assert result["user"]["email"] == request.email
                    assert result["user"]["name"] == request.name
                    assert "access_token" in result

    async def test_register_technician_success(self, registration_service, mock_db):
        """Test de registro exitoso de técnico."""
        # Arrange
        request = TechnicianRegistrationRequest(
            email="tech@test.com",
            password="SecurePass123!",
            first_name="Tech",
            last_name="User",
            phone="+1234567890",
            workshop_id=1
        )
        
        mock_user_repo = AsyncMock()
        mock_user_repo.find_by_email.return_value = None
        mock_user_repo.create.return_value = Technician(
            id=1,
            email=request.email,
            first_name=request.first_name,
            last_name=request.last_name,
            phone=request.phone,
            workshop_id=request.workshop_id,
            is_active=True
        )
        
        with patch.object(registration_service, '_user_repo', mock_user_repo):
            with patch('app.modules.users.service.hash_password', return_value="hashed_password"):
                with patch('app.modules.users.service.create_token_pair', return_value={"access_token": "token", "refresh_token": "refresh"}):
                    # Act
                    result = await registration_service.register_technician(request)
                    
                    # Assert
                    assert result["user"]["email"] == request.email
                    assert result["user"]["workshop_id"] == request.workshop_id

    async def test_register_administrator_success(self, registration_service, mock_db):
        """Test de registro exitoso de administrador."""
        # Arrange
        request = AdministratorRegistrationRequest(
            email="admin@test.com",
            password="SecurePass123!",
            first_name="Admin",
            last_name="User",
            phone="+1234567890"
        )
        
        mock_user_repo = AsyncMock()
        mock_user_repo.find_by_email.return_value = None
        mock_user_repo.create.return_value = Administrator(
            id=1,
            email=request.email,
            first_name=request.first_name,
            last_name=request.last_name,
            phone=request.phone,
            is_active=True
        )
        
        with patch.object(registration_service, '_user_repo', mock_user_repo):
            with patch('app.modules.users.service.hash_password', return_value="hashed_password"):
                with patch('app.modules.users.service.create_token_pair', return_value={"access_token": "token", "refresh_token": "refresh"}):
                    # Act
                    result = await registration_service.register_administrator(request)
                    
                    # Assert
                    assert result["user"]["email"] == request.email
                    assert "access_token" in result

    async def test_register_with_weak_password(self, registration_service, mock_db):
        """Test de registro con contraseña débil."""
        # Arrange
        request = ClientRegistrationRequest(
            email="client@test.com",
            password="weak",
            first_name="John",
            last_name="Doe",
            phone="+1234567890"
        )
        
        with patch('app.modules.users.service.validate_password_strength', side_effect=ValidationException("Password too weak")):
            # Act & Assert
            with pytest.raises(ValidationException, match="Password too weak"):
                await registration_service.register_client(request)

    async def test_register_sends_welcome_email(self, registration_service, mock_db):
        """Test que verifica el envío de email de bienvenida."""
        # Arrange
        request = ClientRegistrationRequest(
            email="client@test.com",
            password="SecurePass123!",
            first_name="John",
            last_name="Doe",
            phone="+1234567890"
        )
        
        mock_user_repo = AsyncMock()
        mock_user_repo.find_by_email.return_value = None
        mock_user_repo.create.return_value = Client(
            id=1,
            email=request.email,
            first_name=request.first_name,
            last_name=request.last_name,
            is_active=True
        )
        
        mock_email_service = AsyncMock()
        
        with patch.object(registration_service, '_user_repo', mock_user_repo):
            with patch('app.modules.users.service.hash_password', return_value="hashed_password"):
                with patch('app.modules.users.service.create_token_pair', return_value={"access_token": "token", "refresh_token": "refresh"}):
                    with patch('app.modules.users.service.send_welcome_email', mock_email_service):
                        # Act
                        await registration_service.register_client(request)
                        
                        # Assert
                        mock_email_service.assert_called_once()
