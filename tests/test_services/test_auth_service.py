"""
Tests for authentication service.
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.modules.auth.service import AuthService
from app.modules.auth.schemas import LoginRequest
from app.core.exceptions import InvalidCredentialsException


class TestAuthService:
    """Test AuthService."""
    
    @pytest.mark.asyncio
    async def test_login_success(self, db_session, sample_client):
        """Test successful login."""
        auth_service = AuthService(db_session)
        
        login_request = LoginRequest(
            email=sample_client.email,
            password="testpassword123"
        )
        
        user, token_response = await auth_service.login(login_request)
        
        assert user.id == sample_client.id
        assert user.email == sample_client.email
        assert token_response.access_token is not None
        assert token_response.refresh_token is not None
        assert token_response.requires_2fa is False
    
    @pytest.mark.asyncio
    async def test_login_invalid_email(self, db_session):
        """Test login with invalid email."""
        auth_service = AuthService(db_session)
        
        login_request = LoginRequest(
            email="nonexistent@test.com",
            password="testpassword123"
        )
        
        with pytest.raises(InvalidCredentialsException):
            await auth_service.login(login_request)
    
    @pytest.mark.asyncio
    async def test_login_invalid_password(self, db_session, sample_client):
        """Test login with invalid password."""
        auth_service = AuthService(db_session)
        
        login_request = LoginRequest(
            email=sample_client.email,
            password="wrongpassword"
        )
        
        with pytest.raises(InvalidCredentialsException):
            await auth_service.login(login_request)
    
    @pytest.mark.asyncio
    async def test_login_with_2fa_enabled(self, db_session, sample_client):
        """Test login when 2FA is enabled."""
        # Enable 2FA for the user
        sample_client.two_factor_enabled = True
        await db_session.commit()
        
        auth_service = AuthService(db_session)
        
        login_request = LoginRequest(
            email=sample_client.email,
            password="testpassword123"
        )
        
        user, token_response = await auth_service.login(login_request)
        
        assert user.id == sample_client.id
        assert token_response.requires_2fa is True
        assert token_response.access_token == ""
        assert token_response.refresh_token == ""
    
    @pytest.mark.asyncio
    async def test_logout(self, db_session, sample_client):
        """Test user logout."""
        auth_service = AuthService(db_session)
        
        # Mock the token service
        with patch.object(auth_service.token_repo, 'revoke_all_user_tokens') as mock_revoke:
            mock_revoke.return_value = 2  # Simulate 2 tokens revoked
            
            await auth_service.logout(sample_client.id)
            
            mock_revoke.assert_called_once_with(sample_client.id)