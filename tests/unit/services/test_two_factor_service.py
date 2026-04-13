"""
Tests para TwoFactorService.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.two_factor.service import TwoFactorService
from app.modules.two_factor.schemas import (
    Enable2FARequest,
    Verify2FARequest,
    Disable2FARequest,
    Resend2FARequest
)
from app.models.two_factor_auth import TwoFactorAuth
from app.core.exceptions import ValidationException, AuthenticationException


@pytest.fixture
def mock_db():
    """Mock de sesión de base de datos."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def two_factor_service(mock_db):
    """Fixture del servicio de 2FA."""
    return TwoFactorService(mock_db)


@pytest.mark.asyncio
class TestTwoFactorService:
    """Tests para TwoFactorService."""

    async def test_enable_2fa_success(self, two_factor_service, mock_db):
        """Test de habilitación exitosa de 2FA."""
        # Arrange
        user_id = 1
        user_type = "client"
        email = "user@test.com"
        
        mock_2fa_repo = AsyncMock()
        mock_2fa_repo.find_by_user.return_value = None
        mock_2fa_repo.create.return_value = TwoFactorAuth(
            id=1,
            user_id=user_id,
            user_type=user_type,
            otp_code_hash="hashed_otp",
            otp_expires_at=datetime.utcnow() + timedelta(minutes=5),
            is_enabled=False,
            is_verified=False
        )
        
        mock_email_service = AsyncMock()
        
        with patch.object(two_factor_service, '_2fa_repo', mock_2fa_repo):
            with patch('app.modules.two_factor.service.generate_otp', return_value=("123456", "hashed_otp")):
                with patch('app.modules.two_factor.service.send_otp_email', mock_email_service):
                    # Act
                    result = await two_factor_service.enable_2fa(user_id, user_type, email)
                    
                    # Assert
                    assert result["message"] == "2FA code sent to your email"
                    assert result["expires_in_minutes"] == 5
                    mock_2fa_repo.create.assert_called_once()
                    mock_email_service.assert_called_once()

    async def test_enable_2fa_already_enabled(self, two_factor_service, mock_db):
        """Test de habilitación cuando 2FA ya está habilitado."""
        # Arrange
        user_id = 1
        user_type = "client"
        email = "user@test.com"
        
        mock_2fa_repo = AsyncMock()
        mock_2fa_repo.find_by_user.return_value = TwoFactorAuth(
            id=1,
            user_id=user_id,
            user_type=user_type,
            is_enabled=True,
            is_verified=True
        )
        
        with patch.object(two_factor_service, '_2fa_repo', mock_2fa_repo):
            # Act & Assert
            with pytest.raises(ValidationException, match="2FA is already enabled"):
                await two_factor_service.enable_2fa(user_id, user_type, email)

    async def test_verify_otp_success(self, two_factor_service, mock_db):
        """Test de verificación exitosa de OTP."""
        # Arrange
        user_id = 1
        user_type = "client"
        otp_code = "123456"
        
        mock_2fa_repo = AsyncMock()
        mock_2fa_repo.find_by_user.return_value = TwoFactorAuth(
            id=1,
            user_id=user_id,
            user_type=user_type,
            otp_code_hash="hashed_otp",
            otp_expires_at=datetime.utcnow() + timedelta(minutes=5),
            verification_attempts=0,
            is_enabled=False,
            is_verified=False
        )
        mock_2fa_repo.update.return_value = TwoFactorAuth(
            id=1,
            user_id=user_id,
            user_type=user_type,
            is_enabled=True,
            is_verified=True
        )
        
        with patch.object(two_factor_service, '_2fa_repo', mock_2fa_repo):
            with patch('app.modules.two_factor.service.verify_otp', return_value=True):
                # Act
                result = await two_factor_service.verify_otp(user_id, user_type, otp_code)
                
                # Assert
                assert result["message"] == "2FA enabled successfully"
                assert result["enabled"] is True
                mock_2fa_repo.update.assert_called_once()

    async def test_verify_otp_expired(self, two_factor_service, mock_db):
        """Test de verificación con OTP expirado."""
        # Arrange
        user_id = 1
        user_type = "client"
        otp_code = "123456"
        
        mock_2fa_repo = AsyncMock()
        mock_2fa_repo.find_by_user.return_value = TwoFactorAuth(
            id=1,
            user_id=user_id,
            user_type=user_type,
            otp_code_hash="hashed_otp",
            otp_expires_at=datetime.utcnow() - timedelta(minutes=1),  # Expirado
            verification_attempts=0
        )
        
        with patch.object(two_factor_service, '_2fa_repo', mock_2fa_repo):
            # Act & Assert
            with pytest.raises(ValidationException, match="OTP code has expired"):
                await two_factor_service.verify_otp(user_id, user_type, otp_code)

    async def test_verify_otp_invalid_code(self, two_factor_service, mock_db):
        """Test de verificación con código inválido."""
        # Arrange
        user_id = 1
        user_type = "client"
        otp_code = "wrong_code"
        
        mock_2fa_repo = AsyncMock()
        mock_2fa_repo.find_by_user.return_value = TwoFactorAuth(
            id=1,
            user_id=user_id,
            user_type=user_type,
            otp_code_hash="hashed_otp",
            otp_expires_at=datetime.utcnow() + timedelta(minutes=5),
            verification_attempts=0
        )
        mock_2fa_repo.update.return_value = TwoFactorAuth(
            id=1,
            verification_attempts=1
        )
        
        with patch.object(two_factor_service, '_2fa_repo', mock_2fa_repo):
            with patch('app.modules.two_factor.service.verify_otp', return_value=False):
                # Act & Assert
                with pytest.raises(ValidationException, match="Invalid OTP code"):
                    await two_factor_service.verify_otp(user_id, user_type, otp_code)

    async def test_verify_otp_max_attempts_exceeded(self, two_factor_service, mock_db):
        """Test de verificación con intentos máximos excedidos."""
        # Arrange
        user_id = 1
        user_type = "client"
        otp_code = "123456"
        
        mock_2fa_repo = AsyncMock()
        mock_2fa_repo.find_by_user.return_value = TwoFactorAuth(
            id=1,
            user_id=user_id,
            user_type=user_type,
            otp_code_hash="hashed_otp",
            otp_expires_at=datetime.utcnow() + timedelta(minutes=5),
            verification_attempts=3  # Máximo alcanzado
        )
        
        with patch.object(two_factor_service, '_2fa_repo', mock_2fa_repo):
            # Act & Assert
            with pytest.raises(ValidationException, match="Maximum verification attempts exceeded"):
                await two_factor_service.verify_otp(user_id, user_type, otp_code)

    async def test_disable_2fa_success(self, two_factor_service, mock_db):
        """Test de deshabilitación exitosa de 2FA."""
        # Arrange
        user_id = 1
        user_type = "client"
        password = "correct_password"
        password_hash = "hashed_password"
        
        mock_2fa_repo = AsyncMock()
        mock_2fa_repo.find_by_user.return_value = TwoFactorAuth(
            id=1,
            user_id=user_id,
            user_type=user_type,
            is_enabled=True,
            is_verified=True
        )
        mock_2fa_repo.update.return_value = TwoFactorAuth(
            id=1,
            is_enabled=False,
            is_verified=False
        )
        
        with patch.object(two_factor_service, '_2fa_repo', mock_2fa_repo):
            with patch('app.modules.two_factor.service.verify_password', return_value=True):
                # Act
                result = await two_factor_service.disable_2fa(user_id, user_type, password, password_hash)
                
                # Assert
                assert result["message"] == "2FA disabled successfully"
                assert result["enabled"] is False
                mock_2fa_repo.update.assert_called_once()

    async def test_disable_2fa_wrong_password(self, two_factor_service, mock_db):
        """Test de deshabilitación con contraseña incorrecta."""
        # Arrange
        user_id = 1
        user_type = "client"
        password = "wrong_password"
        password_hash = "hashed_password"
        
        mock_2fa_repo = AsyncMock()
        mock_2fa_repo.find_by_user.return_value = TwoFactorAuth(
            id=1,
            user_id=user_id,
            user_type=user_type,
            is_enabled=True
        )
        
        with patch.object(two_factor_service, '_2fa_repo', mock_2fa_repo):
            with patch('app.modules.two_factor.service.verify_password', return_value=False):
                # Act & Assert
                with pytest.raises(AuthenticationException, match="Invalid password"):
                    await two_factor_service.disable_2fa(user_id, user_type, password, password_hash)

    async def test_resend_otp_success(self, two_factor_service, mock_db):
        """Test de reenvío exitoso de OTP."""
        # Arrange
        user_id = 1
        user_type = "client"
        email = "user@test.com"
        
        mock_2fa_repo = AsyncMock()
        mock_2fa_repo.find_by_user.return_value = TwoFactorAuth(
            id=1,
            user_id=user_id,
            user_type=user_type,
            otp_sent_at=datetime.utcnow() - timedelta(minutes=2),  # Hace 2 minutos
            is_enabled=False
        )
        mock_2fa_repo.update.return_value = TwoFactorAuth(
            id=1,
            otp_code_hash="new_hashed_otp",
            otp_expires_at=datetime.utcnow() + timedelta(minutes=5)
        )
        
        mock_email_service = AsyncMock()
        
        with patch.object(two_factor_service, '_2fa_repo', mock_2fa_repo):
            with patch('app.modules.two_factor.service.generate_otp', return_value=("654321", "new_hashed_otp")):
                with patch('app.modules.two_factor.service.send_otp_email', mock_email_service):
                    # Act
                    result = await two_factor_service.resend_otp(user_id, user_type, email)
                    
                    # Assert
                    assert result["message"] == "New 2FA code sent to your email"
                    mock_2fa_repo.update.assert_called_once()
                    mock_email_service.assert_called_once()

    async def test_resend_otp_too_soon(self, two_factor_service, mock_db):
        """Test de reenvío demasiado pronto."""
        # Arrange
        user_id = 1
        user_type = "client"
        email = "user@test.com"
        
        mock_2fa_repo = AsyncMock()
        mock_2fa_repo.find_by_user.return_value = TwoFactorAuth(
            id=1,
            user_id=user_id,
            user_type=user_type,
            otp_sent_at=datetime.utcnow() - timedelta(seconds=30),  # Hace 30 segundos
            is_enabled=False
        )
        
        with patch.object(two_factor_service, '_2fa_repo', mock_2fa_repo):
            # Act & Assert
            with pytest.raises(ValidationException, match="Please wait before requesting a new code"):
                await two_factor_service.resend_otp(user_id, user_type, email)
