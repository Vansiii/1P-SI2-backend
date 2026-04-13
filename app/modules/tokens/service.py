"""
Service for token management operations.
"""
from datetime import UTC, datetime, timedelta
from typing import Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from ...core import (
    InvalidTokenException,
    TokenExpiredException,
    UserNotFoundException,
    create_access_token,
    create_refresh_token,
    get_logger,
    get_settings,
)
from ...models.refresh_token import RefreshToken
from ...models.user import User
from ...modules.auth.repository import UserRepository
from .repository import RefreshTokenRepository

logger = get_logger(__name__)


class TokenService:
    """Service for token management operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.token_repo = RefreshTokenRepository(session)
        self.user_repo = UserRepository(session)
        self.settings = get_settings()
    
    async def create_token_pair(self, user: User) -> Tuple[str, str, datetime, datetime]:
        """
        Create a pair of tokens (access + refresh) for a user.
        
        Args:
            user: User to create tokens for
            
        Returns:
            Tuple of (access_token, refresh_token, access_expires_at, refresh_expires_at)
        """
        # Get user_type (for WorkshopUser use 'role')
        user_type = getattr(user, 'user_type', None) or getattr(user, 'role', 'user')
        
        # Create access token
        access_token, access_expires_at, jti = create_access_token(
            subject=str(user.id),
            email=user.email,
            user_type=user_type,
        )
        
        # Create refresh token
        refresh_token_str, refresh_token_hash = create_refresh_token()
        refresh_expires_at = datetime.now(UTC) + timedelta(
            days=self.settings.refresh_token_expire_days
        )
        
        # Save refresh token in database
        refresh_token = RefreshToken(
            user_id=user.id,
            token_hash=refresh_token_hash,
            jti=jti,
            expires_at=refresh_expires_at,
        )
        
        self.session.add(refresh_token)
        await self.session.commit()
        
        logger.info(
            "Token pair created",
            user_id=user.id,
            expires_at=access_expires_at.isoformat(),
        )
        
        return access_token, refresh_token_str, access_expires_at, refresh_expires_at
    
    async def rotate_refresh_token(
        self, 
        refresh_token_str: str
    ) -> Tuple[str, str, datetime, datetime]:
        """
        Rotate a refresh token: validate current, revoke it, and create new one.
        Implements token rotation for enhanced security.
        
        Args:
            refresh_token_str: Current refresh token
            
        Returns:
            Tuple of (access_token, refresh_token, access_expires_at, refresh_expires_at)
            
        Raises:
            InvalidTokenException: If token is invalid or revoked
            TokenExpiredException: If token is expired
            UserNotFoundException: If user doesn't exist
        """
        current_time = datetime.now(UTC)
        
        # Find and validate refresh token
        matching_token = await self.token_repo.find_active_by_token(refresh_token_str)
        
        if not matching_token:
            logger.warning("Invalid refresh token used")
            raise InvalidTokenException("Refresh token inválido o expirado")
        
        # Check if revoked (double verification)
        if matching_token.revoked_at is not None:
            logger.warning("Revoked refresh token used", token_id=matching_token.id)
            raise InvalidTokenException("Refresh token ya fue revocado. Inicia sesión nuevamente")
        
        # Check if expired (double verification)
        if matching_token.expires_at < current_time:
            logger.warning("Expired refresh token used", token_id=matching_token.id)
            raise TokenExpiredException("Refresh token expirado. Inicia sesión nuevamente")
        
        # Get user
        user = await self.user_repo.find_by_id(matching_token.user_id)
        if not user:
            logger.error("User not found for valid token", user_id=matching_token.user_id)
            raise UserNotFoundException(f"Usuario {matching_token.user_id}")
        
        if not user.is_active:
            logger.warning("Inactive user tried to refresh token", user_id=user.id)
            raise InvalidTokenException("Usuario inactivo")
        
        # Revoke current refresh token
        await self.token_repo.revoke_token(matching_token.id)
        
        # Create new token pair
        access_token, refresh_token, access_expires_at, refresh_expires_at = (
            await self.create_token_pair(user)
        )
        
        logger.info("Refresh token rotated", user_id=user.id, old_token_id=matching_token.id)
        
        return access_token, refresh_token, access_expires_at, refresh_expires_at
    
    async def revoke_refresh_token(self, refresh_token_str: str) -> bool:
        """
        Revoke a specific refresh token.
        
        Args:
            refresh_token_str: Refresh token to revoke
            
        Returns:
            True if revoked successfully, False if not found
        """
        matching_token = await self.token_repo.find_active_by_token(refresh_token_str)
        
        if matching_token:
            await self.token_repo.revoke_token(matching_token.id)
            logger.info("Refresh token revoked", token_id=matching_token.id)
            return True
        
        return False
    
    async def revoke_all_user_tokens(self, user_id: int) -> int:
        """
        Revoke all refresh tokens for a user.
        Useful when changing password or closing all sessions.
        
        Args:
            user_id: User ID
            
        Returns:
            Number of tokens revoked
        """
        count = await self.token_repo.revoke_all_user_tokens(user_id)
        logger.info("All user tokens revoked", user_id=user_id, count=count)
        return count
    
    async def cleanup_expired_tokens(self) -> int:
        """
        Clean up expired tokens from database.
        Should be run periodically (e.g., scheduled task).
        
        Returns:
            Number of tokens deleted
        """
        # Delete tokens expired more than 30 days ago
        cutoff_date = datetime.now(UTC) - timedelta(days=30)
        count = await self.token_repo.delete_expired_tokens(cutoff_date)
        
        logger.info("Expired tokens cleaned up", count=count)
        return count