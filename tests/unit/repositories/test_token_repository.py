"""
Tests unitarios para TokenRepository.
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tokens.repository import TokenRepository
from app.models.refresh_token import RefreshToken
from app.models.revoked_token import RevokedToken
from app.models.client import Client
from app.core.security import hash_password


@pytest.fixture
async def token_repository(db_session: AsyncSession):
    """Fixture para TokenRepository."""
    return TokenRepository(db_session)


@pytest.fixture
async def sample_client(db_session: AsyncSession):
    """Fixture para crear un cliente de prueba."""
    client = Client(
        email="token_test@example.com",
        password_hash=hash_password("TestPassword123!"),
        first_name="Token",
        last_name="Test",
        phone="+1234567890",
        is_active=True
    )
    db_session.add(client)
    await db_session.commit()
    await db_session.refresh(client)
    return client


class TestTokenRepository:
    """Tests para TokenRepository."""

    async def test_create_refresh_token(
        self,
        token_repository: TokenRepository,
        sample_client: Client
    ):
        """Test crear refresh token."""
        token_hash = "test_token_hash_123"
        expires_at = datetime.utcnow() + timedelta(days=7)
        
        refresh_token = await token_repository.create_refresh_token(
            user_id=sample_client.id,
            user_type="client",
            token_hash=token_hash,
            expires_at=expires_at
        )
        
        assert refresh_token.id is not None
        assert refresh_token.user_id == sample_client.id
        assert refresh_token.user_type == "client"
        assert refresh_token.token_hash == token_hash
        assert refresh_token.expires_at == expires_at
        assert refresh_token.is_revoked is False

    async def test_find_refresh_token_by_hash(
        self,
        token_repository: TokenRepository,
        sample_client: Client
    ):
        """Test buscar refresh token por hash."""
        token_hash = "unique_token_hash_456"
        expires_at = datetime.utcnow() + timedelta(days=7)
        
        # Crear token
        await token_repository.create_refresh_token(
            user_id=sample_client.id,
            user_type="client",
            token_hash=token_hash,
            expires_at=expires_at
        )
        
        # Buscar token
        found_token = await token_repository.find_refresh_token_by_hash(token_hash)
        
        assert found_token is not None
        assert found_token.token_hash == token_hash
        assert found_token.user_id == sample_client.id

    async def test_find_refresh_token_by_hash_not_found(
        self,
        token_repository: TokenRepository
    ):
        """Test buscar refresh token inexistente."""
        found_token = await token_repository.find_refresh_token_by_hash("nonexistent_hash")
        assert found_token is None

    async def test_revoke_refresh_token(
        self,
        token_repository: TokenRepository,
        sample_client: Client
    ):
        """Test revocar refresh token."""
        token_hash = "token_to_revoke_789"
        expires_at = datetime.utcnow() + timedelta(days=7)
        
        # Crear token
        refresh_token = await token_repository.create_refresh_token(
            user_id=sample_client.id,
            user_type="client",
            token_hash=token_hash,
            expires_at=expires_at
        )
        
        # Revocar token
        await token_repository.revoke_refresh_token(refresh_token.id)
        
        # Verificar que está revocado
        revoked_token = await token_repository.find_refresh_token_by_hash(token_hash)
        assert revoked_token.is_revoked is True

    async def test_revoke_all_user_tokens(
        self,
        token_repository: TokenRepository,
        sample_client: Client
    ):
        """Test revocar todos los tokens de un usuario."""
        # Crear múltiples tokens
        for i in range(3):
            await token_repository.create_refresh_token(
                user_id=sample_client.id,
                user_type="client",
                token_hash=f"token_hash_{i}",
                expires_at=datetime.utcnow() + timedelta(days=7)
            )
        
        # Revocar todos
        count = await token_repository.revoke_all_user_tokens(
            sample_client.id,
            "client"
        )
        
        assert count == 3

    async def test_delete_expired_tokens(
        self,
        token_repository: TokenRepository,
        sample_client: Client
    ):
        """Test eliminar tokens expirados."""
        # Crear token expirado
        expired_token = await token_repository.create_refresh_token(
            user_id=sample_client.id,
            user_type="client",
            token_hash="expired_token",
            expires_at=datetime.utcnow() - timedelta(days=1)
        )
        
        # Crear token válido
        valid_token = await token_repository.create_refresh_token(
            user_id=sample_client.id,
            user_type="client",
            token_hash="valid_token",
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
        
        # Eliminar expirados
        count = await token_repository.delete_expired_tokens()
        
        assert count >= 1
        
        # Verificar que el válido sigue existiendo
        found_valid = await token_repository.find_refresh_token_by_hash("valid_token")
        assert found_valid is not None

    async def test_is_token_revoked(
        self,
        token_repository: TokenRepository,
        db_session: AsyncSession
    ):
        """Test verificar si un access token está revocado."""
        jti = "test_jti_123"
        
        # Token no revocado
        is_revoked = await token_repository.is_token_revoked(jti)
        assert is_revoked is False
        
        # Revocar token
        revoked_token = RevokedToken(
            jti=jti,
            revoked_at=datetime.utcnow()
        )
        db_session.add(revoked_token)
        await db_session.commit()
        
        # Verificar que está revocado
        is_revoked = await token_repository.is_token_revoked(jti)
        assert is_revoked is True

    async def test_revoke_access_token(
        self,
        token_repository: TokenRepository
    ):
        """Test revocar access token."""
        jti = "access_token_jti_456"
        
        await token_repository.revoke_access_token(jti)
        
        # Verificar que está revocado
        is_revoked = await token_repository.is_token_revoked(jti)
        assert is_revoked is True

    async def test_cleanup_old_revoked_tokens(
        self,
        token_repository: TokenRepository,
        db_session: AsyncSession
    ):
        """Test limpiar tokens revocados antiguos."""
        # Crear token revocado antiguo
        old_token = RevokedToken(
            jti="old_jti",
            revoked_at=datetime.utcnow() - timedelta(days=31)
        )
        db_session.add(old_token)
        
        # Crear token revocado reciente
        recent_token = RevokedToken(
            jti="recent_jti",
            revoked_at=datetime.utcnow() - timedelta(days=1)
        )
        db_session.add(recent_token)
        await db_session.commit()
        
        # Limpiar tokens antiguos (>30 días)
        count = await token_repository.cleanup_old_revoked_tokens(days=30)
        
        assert count >= 1
        
        # Verificar que el reciente sigue existiendo
        is_revoked = await token_repository.is_token_revoked("recent_jti")
        assert is_revoked is True
