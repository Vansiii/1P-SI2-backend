"""
Tests unitarios para PasswordResetRepository.
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.password.repository import PasswordResetRepository
from app.models.password_reset_token import PasswordResetToken
from app.models.client import Client
from app.core.security import hash_password


@pytest.fixture
async def password_reset_repository(db_session: AsyncSession):
    """Fixture para PasswordResetRepository."""
    return PasswordResetRepository(db_session)


@pytest.fixture
async def sample_client(db_session: AsyncSession):
    """Fixture para crear un cliente de prueba."""
    client = Client(
        email="password_test@example.com",
        password_hash=hash_password("TestPassword123!"),
        first_name="Password",
        last_name="Test",
        phone="+1234567890",
        is_active=True
    )
    db_session.add(client)
    await db_session.commit()
    await db_session.refresh(client)
    return client


class TestPasswordResetRepository:
    """Tests para PasswordResetRepository."""

    async def test_create_reset_token(
        self,
        password_reset_repository: PasswordResetRepository,
        sample_client: Client
    ):
        """Test crear token de reset."""
        token = "reset_token_123"
        expires_at = datetime.utcnow() + timedelta(hours=1)
        
        reset_token = await password_reset_repository.create_reset_token(
            user_id=sample_client.id,
            user_type="client",
            token=token,
            expires_at=expires_at
        )
        
        assert reset_token.id is not None
        assert reset_token.user_id == sample_client.id
        assert reset_token.user_type == "client"
        assert reset_token.token == token
        assert reset_token.expires_at == expires_at
        assert reset_token.is_used is False

    async def test_find_reset_token(
        self,
        password_reset_repository: PasswordResetRepository,
        sample_client: Client
    ):
        """Test buscar token de reset."""
        token = "unique_reset_token_456"
        expires_at = datetime.utcnow() + timedelta(hours=1)
        
        # Crear token
        await password_reset_repository.create_reset_token(
            user_id=sample_client.id,
            user_type="client",
            token=token,
            expires_at=expires_at
        )
        
        # Buscar token
        found_token = await password_reset_repository.find_reset_token(token)
        
        assert found_token is not None
        assert found_token.token == token
        assert found_token.user_id == sample_client.id
        assert found_token.is_used is False

    async def test_find_reset_token_not_found(
        self,
        password_reset_repository: PasswordResetRepository
    ):
        """Test buscar token inexistente."""
        found_token = await password_reset_repository.find_reset_token("nonexistent_token")
        assert found_token is None

    async def test_mark_token_as_used(
        self,
        password_reset_repository: PasswordResetRepository,
        sample_client: Client
    ):
        """Test marcar token como usado."""
        token = "token_to_use_789"
        expires_at = datetime.utcnow() + timedelta(hours=1)
        
        # Crear token
        reset_token = await password_reset_repository.create_reset_token(
            user_id=sample_client.id,
            user_type="client",
            token=token,
            expires_at=expires_at
        )
        
        # Marcar como usado
        await password_reset_repository.mark_token_as_used(reset_token.id)
        
        # Verificar que está usado
        used_token = await password_reset_repository.find_reset_token(token)
        assert used_token.is_used is True
        assert used_token.used_at is not None

    async def test_find_recent_reset_request(
        self,
        password_reset_repository: PasswordResetRepository,
        sample_client: Client
    ):
        """Test buscar solicitud reciente de reset."""
        # Crear token reciente
        token = "recent_token"
        expires_at = datetime.utcnow() + timedelta(hours=1)
        
        await password_reset_repository.create_reset_token(
            user_id=sample_client.id,
            user_type="client",
            token=token,
            expires_at=expires_at
        )
        
        # Buscar solicitud reciente (últimos 5 minutos)
        recent_token = await password_reset_repository.find_recent_reset_request(
            sample_client.id,
            "client",
            minutes=5
        )
        
        assert recent_token is not None
        assert recent_token.user_id == sample_client.id

    async def test_find_recent_reset_request_not_found(
        self,
        password_reset_repository: PasswordResetRepository,
        sample_client: Client
    ):
        """Test buscar solicitud reciente cuando no existe."""
        # Buscar sin haber creado ningún token
        recent_token = await password_reset_repository.find_recent_reset_request(
            sample_client.id,
            "client",
            minutes=5
        )
        
        assert recent_token is None

    async def test_delete_expired_tokens(
        self,
        password_reset_repository: PasswordResetRepository,
        sample_client: Client
    ):
        """Test eliminar tokens expirados."""
        # Crear token expirado
        expired_token = await password_reset_repository.create_reset_token(
            user_id=sample_client.id,
            user_type="client",
            token="expired_token",
            expires_at=datetime.utcnow() - timedelta(hours=2)
        )
        
        # Crear token válido
        valid_token = await password_reset_repository.create_reset_token(
            user_id=sample_client.id,
            user_type="client",
            token="valid_token",
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        
        # Eliminar expirados
        count = await password_reset_repository.delete_expired_tokens()
        
        assert count >= 1
        
        # Verificar que el válido sigue existiendo
        found_valid = await password_reset_repository.find_reset_token("valid_token")
        assert found_valid is not None
        
        # Verificar que el expirado fue eliminado
        found_expired = await password_reset_repository.find_reset_token("expired_token")
        assert found_expired is None

    async def test_invalidate_user_tokens(
        self,
        password_reset_repository: PasswordResetRepository,
        sample_client: Client
    ):
        """Test invalidar todos los tokens de un usuario."""
        # Crear múltiples tokens
        for i in range(3):
            await password_reset_repository.create_reset_token(
                user_id=sample_client.id,
                user_type="client",
                token=f"token_{i}",
                expires_at=datetime.utcnow() + timedelta(hours=1)
            )
        
        # Invalidar todos
        count = await password_reset_repository.invalidate_user_tokens(
            sample_client.id,
            "client"
        )
        
        assert count == 3
        
        # Verificar que todos están marcados como usados
        for i in range(3):
            token = await password_reset_repository.find_reset_token(f"token_{i}")
            assert token.is_used is True
