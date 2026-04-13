"""
Tests unitarios para PasswordService.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.password.service import (
    forgot_password,
    reset_password,
    change_password
)
from app.models.client import Client
from app.core.security import hash_password, verify_password


@pytest.fixture
async def sample_client(db_session: AsyncSession):
    """Fixture para crear un cliente de prueba."""
    client = Client(
        email="password_service_test@example.com",
        password_hash=hash_password("OldPassword123!"),
        first_name="PasswordService",
        last_name="Test",
        phone="+1234567890",
        is_active=True
    )
    db_session.add(client)
    await db_session.commit()
    await db_session.refresh(client)
    return client


class TestPasswordService:
    """Tests para PasswordService."""

    @patch('app.modules.password.service.send_password_reset_email')
    async def test_forgot_password_success(
        self,
        mock_send_email: AsyncMock,
        db_session: AsyncSession,
        sample_client: Client
    ):
        """Test solicitar recuperación de contraseña exitosamente."""
        mock_send_email.return_value = None
        
        response = await forgot_password(
            db=db_session,
            email=sample_client.email
        )
        
        assert response.message is not None
        assert "email" in response.message.lower()
        mock_send_email.assert_called_once()

    async def test_forgot_password_user_not_found(
        self,
        db_session: AsyncSession
    ):
        """Test solicitar recuperación con email inexistente."""
        # Por seguridad, no debe revelar que el usuario no existe
        response = await forgot_password(
            db=db_session,
            email="nonexistent@example.com"
        )
        
        assert response.message is not None

    async def test_forgot_password_rate_limit(
        self,
        db_session: AsyncSession,
        sample_client: Client
    ):
        """Test límite de solicitudes de recuperación."""
        from app.core.exceptions import ValidationException
        
        # Primera solicitud
        with patch('app.modules.password.service.send_password_reset_email'):
            await forgot_password(
                db=db_session,
                email=sample_client.email
            )
        
        # Segunda solicitud inmediata debe fallar
        with pytest.raises(ValidationException) as exc_info:
            await forgot_password(
                db=db_session,
                email=sample_client.email
            )
        
        assert "recently" in str(exc_info.value).lower()

    @patch('app.modules.password.service.send_password_changed_email')
    async def test_reset_password_success(
        self,
        mock_send_email: AsyncMock,
        db_session: AsyncSession,
        sample_client: Client
    ):
        """Test resetear contraseña exitosamente."""
        mock_send_email.return_value = None
        
        # Crear token de reset
        from app.modules.password.repository import PasswordResetRepository
        repository = PasswordResetRepository(db_session)
        
        reset_token = await repository.create_reset_token(
            user_id=sample_client.id,
            user_type="client",
            token="valid_reset_token_123",
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        
        # Resetear contraseña
        new_password = "NewPassword123!"
        response = await reset_password(
            db=db_session,
            token="valid_reset_token_123",
            new_password=new_password
        )
        
        assert response.message is not None
        mock_send_email.assert_called_once()
        
        # Verificar que la contraseña cambió
        await db_session.refresh(sample_client)
        assert verify_password(new_password, sample_client.password_hash)

    async def test_reset_password_invalid_token(
        self,
        db_session: AsyncSession
    ):
        """Test resetear contraseña con token inválido."""
        from app.core.exceptions import ValidationException
        
        with pytest.raises(ValidationException) as exc_info:
            await reset_password(
                db=db_session,
                token="invalid_token",
                new_password="NewPassword123!"
            )
        
        assert "invalid" in str(exc_info.value).lower()

    async def test_reset_password_expired_token(
        self,
        db_session: AsyncSession,
        sample_client: Client
    ):
        """Test resetear contraseña con token expirado."""
        from app.core.exceptions import ValidationException
        from app.modules.password.repository import PasswordResetRepository
        
        repository = PasswordResetRepository(db_session)
        
        # Crear token expirado
        await repository.create_reset_token(
            user_id=sample_client.id,
            user_type="client",
            token="expired_token_123",
            expires_at=datetime.utcnow() - timedelta(hours=1)
        )
        
        with pytest.raises(ValidationException) as exc_info:
            await reset_password(
                db=db_session,
                token="expired_token_123",
                new_password="NewPassword123!"
            )
        
        assert "expired" in str(exc_info.value).lower()

    async def test_reset_password_used_token(
        self,
        db_session: AsyncSession,
        sample_client: Client
    ):
        """Test resetear contraseña con token ya usado."""
        from app.core.exceptions import ValidationException
        from app.modules.password.repository import PasswordResetRepository
        
        repository = PasswordResetRepository(db_session)
        
        # Crear token y marcarlo como usado
        reset_token = await repository.create_reset_token(
            user_id=sample_client.id,
            user_type="client",
            token="used_token_123",
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        await repository.mark_token_as_used(reset_token.id)
        
        with pytest.raises(ValidationException) as exc_info:
            await reset_password(
                db=db_session,
                token="used_token_123",
                new_password="NewPassword123!"
            )
        
        assert "used" in str(exc_info.value).lower()

    @patch('app.modules.password.service.send_password_changed_email')
    async def test_change_password_success(
        self,
        mock_send_email: AsyncMock,
        db_session: AsyncSession,
        sample_client: Client
    ):
        """Test cambiar contraseña exitosamente."""
        mock_send_email.return_value = None
        
        old_password = "OldPassword123!"
        new_password = "NewPassword456!"
        
        response = await change_password(
            db=db_session,
            user_id=sample_client.id,
            user_type="client",
            current_password=old_password,
            new_password=new_password
        )
        
        assert response.message is not None
        mock_send_email.assert_called_once()
        
        # Verificar que la contraseña cambió
        await db_session.refresh(sample_client)
        assert verify_password(new_password, sample_client.password_hash)

    async def test_change_password_wrong_current(
        self,
        db_session: AsyncSession,
        sample_client: Client
    ):
        """Test cambiar contraseña con contraseña actual incorrecta."""
        from app.core.exceptions import ValidationException
        
        with pytest.raises(ValidationException) as exc_info:
            await change_password(
                db=db_session,
                user_id=sample_client.id,
                user_type="client",
                current_password="WrongPassword123!",
                new_password="NewPassword456!"
            )
        
        assert "incorrect" in str(exc_info.value).lower()

    async def test_change_password_same_as_current(
        self,
        db_session: AsyncSession,
        sample_client: Client
    ):
        """Test cambiar contraseña a la misma contraseña actual."""
        from app.core.exceptions import ValidationException
        
        old_password = "OldPassword123!"
        
        with pytest.raises(ValidationException) as exc_info:
            await change_password(
                db=db_session,
                user_id=sample_client.id,
                user_type="client",
                current_password=old_password,
                new_password=old_password
            )
        
        assert "different" in str(exc_info.value).lower()

    async def test_change_password_weak_password(
        self,
        db_session: AsyncSession,
        sample_client: Client
    ):
        """Test cambiar contraseña a una contraseña débil."""
        from app.core.exceptions import ValidationException
        
        with pytest.raises(ValidationException):
            await change_password(
                db=db_session,
                user_id=sample_client.id,
                user_type="client",
                current_password="OldPassword123!",
                new_password="weak"
            )
