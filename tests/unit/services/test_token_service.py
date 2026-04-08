"""
Tests unitarios para TokenService.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tokens.service import (
    create_token_pair,
    rotate_refresh_token,
    revoke_refresh_token,
    revoke_all_user_tokens,
    cleanup_expired_tokens
)
from app.modules.tokens.repository import TokenRepository
from app.models.client import Client
from app.core.security import hash_password, create_refresh_token, verify_refresh_token_hash


@pytest.fixture
async def sample_client(db_session: AsyncSession):
    """Fixture para crear un cliente de prueba."""
    client = Client(
        email="token_service_test@example.com",
        password_hash=hash_password("TestPassword123!"),
        first_name="TokenService",
        last_name="Test",
        phone="+1234567890",
        is_active=True
    )
    db_session.add(client)
    await db_session.commit()
    await db_session.refresh(client)
    return client


class TestTokenService:
    """Tests para TokenService."""

    async def test_create_token_pair(
        self,
        db_session: AsyncSession,
        sample_client: Client
    ):
        """Test crear par de tokens (access + refresh)."""
        token_pair = await create_token_pair(
            db=db_session,
            user_id=sample_client.id,
            user_type="client"
        )
        
        assert token_pair.access_token is not None
        assert token_pair.refresh_token is not None
        assert token_pair.token_type == "bearer"
        assert token_pair.expires_in > 0

    async def test_rotate_refresh_token_success(
        self,
        db_session: AsyncSession,
        sample_client: Client
    ):
        """Test rotar refresh token exitosamente."""
        # Crear token inicial
        initial_pair = await create_token_pair(
            db=db_session,
            user_id=sample_client.id,
            user_type="client"
        )
        
        # Rotar token
        new_pair = await rotate_refresh_token(
            db=db_session,
            refresh_token=initial_pair.refresh_token
        )
        
        assert new_pair.access_token is not None
        assert new_pair.refresh_token is not None
        assert new_pair.refresh_token != initial_pair.refresh_token

    async def test_rotate_refresh_token_invalid(
        self,
        db_session: AsyncSession
    ):
        """Test rotar refresh token inválido."""
        from app.core.exceptions import AuthenticationException
        
        with pytest.raises(AuthenticationException):
            await rotate_refresh_token(
                db=db_session,
                refresh_token="invalid_token_123"
            )

    async def test_revoke_refresh_token(
        self,
        db_session: AsyncSession,
        sample_client: Client
    ):
        """Test revocar refresh token."""
        # Crear token
        token_pair = await create_token_pair(
            db=db_session,
            user_id=sample_client.id,
            user_type="client"
        )
        
        # Revocar
        await revoke_refresh_token(
            db=db_session,
            refresh_token=token_pair.refresh_token
        )
        
        # Intentar rotar el token revocado debe fallar
        from app.core.exceptions import AuthenticationException
        
        with pytest.raises(AuthenticationException):
            await rotate_refresh_token(
                db=db_session,
                refresh_token=token_pair.refresh_token
            )

    async def test_revoke_all_user_tokens(
        self,
        db_session: AsyncSession,
        sample_client: Client
    ):
        """Test revocar todos los tokens de un usuario."""
        # Crear múltiples tokens
        tokens = []
        for _ in range(3):
            token_pair = await create_token_pair(
                db=db_session,
                user_id=sample_client.id,
                user_type="client"
            )
            tokens.append(token_pair.refresh_token)
        
        # Revocar todos
        count = await revoke_all_user_tokens(
            db=db_session,
            user_id=sample_client.id,
            user_type="client"
        )
        
        assert count == 3
        
        # Verificar que todos están revocados
        from app.core.exceptions import AuthenticationException
        
        for token in tokens:
            with pytest.raises(AuthenticationException):
                await rotate_refresh_token(
                    db=db_session,
                    refresh_token=token
                )

    async def test_cleanup_expired_tokens(
        self,
        db_session: AsyncSession,
        sample_client: Client
    ):
        """Test limpiar tokens expirados."""
        repository = TokenRepository(db_session)
        
        # Crear token expirado
        expired_hash = "expired_token_hash"
        await repository.create_refresh_token(
            user_id=sample_client.id,
            user_type="client",
            token_hash=expired_hash,
            expires_at=datetime.utcnow() - timedelta(days=1)
        )
        
        # Crear token válido
        valid_pair = await create_token_pair(
            db=db_session,
            user_id=sample_client.id,
            user_type="client"
        )
        
        # Limpiar expirados
        count = await cleanup_expired_tokens(db_session)
        
        assert count >= 1
        
        # Verificar que el válido sigue funcionando
        new_pair = await rotate_refresh_token(
            db=db_session,
            refresh_token=valid_pair.refresh_token
        )
        assert new_pair.access_token is not None
