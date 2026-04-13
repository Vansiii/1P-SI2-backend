"""
Tests de integración para endpoints de tokens.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.refresh_token import RefreshToken
from app.core.security import hash_password, create_access_token


@pytest.mark.asyncio
class TestTokensEndpoints:
    """Tests de integración para endpoints de tokens."""

    async def test_refresh_token_success(self, client: AsyncClient, db_session: AsyncSession):
        """Test de renovación exitosa de token."""
        # Arrange - Crear usuario y refresh token
        user = Client(
            email="user@test.com",
            password_hash=hash_password("SecurePass123!"),
            first_name="John",
            last_name="Doe",
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        
        # Crear refresh token
        from app.core.security import create_refresh_token
        refresh_token_value, refresh_token_hash = create_refresh_token()
        
        refresh_token = RefreshToken(
            user_id=user.id,
            user_type="client",
            token_hash=refresh_token_hash,
            is_revoked=False
        )
        db_session.add(refresh_token)
        await db_session.commit()
        
        # Act
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token_value}
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_refresh_token_invalid(self, client: AsyncClient):
        """Test de renovación con token inválido."""
        # Act
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid_token"}
        )
        
        # Assert
        assert response.status_code == 401
        assert "Invalid refresh token" in response.json()["detail"]

    async def test_refresh_token_revoked(self, client: AsyncClient, db_session: AsyncSession):
        """Test de renovación con token revocado."""
        # Arrange
        user = Client(
            email="user@test.com",
            password_hash=hash_password("SecurePass123!"),
            first_name="John",
            last_name="Doe",
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        
        from app.core.security import create_refresh_token
        refresh_token_value, refresh_token_hash = create_refresh_token()
        
        refresh_token = RefreshToken(
            user_id=user.id,
            user_type="client",
            token_hash=refresh_token_hash,
            is_revoked=True  # Token revocado
        )
        db_session.add(refresh_token)
        await db_session.commit()
        
        # Act
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token_value}
        )
        
        # Assert
        assert response.status_code == 401
        assert "revoked" in response.json()["detail"].lower()

    async def test_revoke_all_tokens_success(self, client: AsyncClient, db_session: AsyncSession, auth_headers):
        """Test de revocación exitosa de todos los tokens."""
        # Act
        response = await client.post(
            "/api/v1/auth/revoke-all",
            headers=auth_headers
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "All sessions revoked successfully"

    async def test_revoke_all_tokens_unauthorized(self, client: AsyncClient):
        """Test de revocación sin autenticación."""
        # Act
        response = await client.post("/api/v1/auth/revoke-all")
        
        # Assert
        assert response.status_code == 401

    async def test_token_rotation_on_refresh(self, client: AsyncClient, db_session: AsyncSession):
        """Test que verifica la rotación de refresh tokens."""
        # Arrange
        user = Client(
            email="user@test.com",
            password_hash=hash_password("SecurePass123!"),
            first_name="John",
            last_name="Doe",
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        
        from app.core.security import create_refresh_token
        old_refresh_token_value, old_refresh_token_hash = create_refresh_token()
        
        refresh_token = RefreshToken(
            user_id=user.id,
            user_type="client",
            token_hash=old_refresh_token_hash,
            is_revoked=False
        )
        db_session.add(refresh_token)
        await db_session.commit()
        
        # Act - Primera renovación
        response1 = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh_token_value}
        )
        
        assert response1.status_code == 200
        new_refresh_token = response1.json()["refresh_token"]
        
        # Act - Intentar usar el token antiguo
        response2 = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh_token_value}
        )
        
        # Assert - El token antiguo debe estar revocado
        assert response2.status_code == 401
        
        # Act - Usar el nuevo token debe funcionar
        response3 = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": new_refresh_token}
        )
        
        assert response3.status_code == 200
