"""
Password reset token repository.
"""
from datetime import datetime, UTC
from typing import Any

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logging import get_logger
from ...models.password_reset_token import PasswordResetToken
from ...shared.repositories.base import BaseRepository

logger = get_logger(__name__)


class PasswordResetRepository(BaseRepository[PasswordResetToken]):
    """Repository for PasswordResetToken operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, PasswordResetToken)
    
    async def find_valid_token(self, token: str) -> PasswordResetToken | None:
        """
        Find valid (unused, non-expired) password reset token.
        
        Args:
            token: Reset token
            
        Returns:
            PasswordResetToken or None if not found/invalid
        """
        try:
            query = select(PasswordResetToken).where(
                PasswordResetToken.token == token,
                PasswordResetToken.used == False,
                PasswordResetToken.expires_at > datetime.now(UTC),
            )
            result = await self.session.execute(query)
            reset_token = result.scalar_one_or_none()
            
            if reset_token:
                logger.debug(
                    "Found valid password reset token",
                    token_id=reset_token.id,
                    user_id=reset_token.user_id,
                )
            
            return reset_token
            
        except Exception as exc:
            logger.error(
                "Error finding valid password reset token",
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def find_recent_unused_token(
        self, user_id: int, created_after: datetime
    ) -> PasswordResetToken | None:
        """
        Find recent unused password reset token for a user.
        
        Args:
            user_id: User ID
            created_after: Only find tokens created after this time
            
        Returns:
            PasswordResetToken or None if not found
        """
        try:
            query = select(PasswordResetToken).where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used == False,
                PasswordResetToken.created_at >= created_after,
            )
            result = await self.session.execute(query)
            reset_token = result.scalar_one_or_none()
            
            if reset_token:
                logger.debug(
                    "Found recent unused password reset token",
                    token_id=reset_token.id,
                    user_id=user_id,
                )
            
            return reset_token
            
        except Exception as exc:
            logger.error(
                "Error finding recent unused password reset token",
                user_id=user_id,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def find_by_token_hash(self, token_hash: str) -> PasswordResetToken | None:
        """
        Find password reset token by token hash.
        
        Args:
            token_hash: Hashed token
            
        Returns:
            PasswordResetToken or None if not found
        """
        try:
            query = select(PasswordResetToken).where(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.used == False,
                PasswordResetToken.expires_at > datetime.now(UTC),
            )
            result = await self.session.execute(query)
            reset_token = result.scalar_one_or_none()
            
            if reset_token:
                logger.debug(
                    "Found password reset token by hash",
                    token_id=reset_token.id,
                    user_id=reset_token.user_id,
                )
            
            return reset_token
            
        except Exception as exc:
            logger.error(
                "Error finding password reset token by hash",
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def mark_token_as_used(self, token_id: int) -> PasswordResetToken:
        """
        Mark password reset token as used.
        
        Args:
            token_id: Token ID
            
        Returns:
            Updated token
        """
        try:
            token = await self.find_by_id_or_raise(token_id)
            token.used = True
            token.used_at = datetime.now(UTC)
            
            await self.session.commit()
            await self.session.refresh(token)
            
            logger.info(
                "Marked password reset token as used",
                token_id=token_id,
                user_id=token.user_id,
            )
            
            return token
            
        except Exception as exc:
            await self.session.rollback()
            logger.error(
                "Error marking password reset token as used",
                token_id=token_id,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def invalidate_user_tokens(self, user_id: int) -> int:
        """
        Invalidate all password reset tokens for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Number of invalidated tokens
        """
        try:
            query = (
                PasswordResetToken.__table__.update()
                .where(
                    PasswordResetToken.user_id == user_id,
                    PasswordResetToken.used == False,
                )
                .values(used=True, used_at=datetime.now(UTC))
            )
            
            result = await self.session.execute(query)
            await self.session.commit()
            
            invalidated_count = result.rowcount or 0
            
            logger.info(
                "Invalidated user password reset tokens",
                user_id=user_id,
                count=invalidated_count,
            )
            
            return invalidated_count
            
        except Exception as exc:
            await self.session.rollback()
            logger.error(
                "Error invalidating user password reset tokens",
                user_id=user_id,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def cleanup_expired_tokens(self) -> int:
        """
        Delete expired password reset tokens.
        
        Returns:
            Number of deleted tokens
        """
        try:
            query = delete(PasswordResetToken).where(
                PasswordResetToken.expires_at <= datetime.now(UTC)
            )
            
            result = await self.session.execute(query)
            await self.session.commit()
            
            deleted_count = result.rowcount or 0
            
            logger.info("Cleaned up expired password reset tokens", count=deleted_count)
            
            return deleted_count
            
        except Exception as exc:
            await self.session.rollback()
            logger.error(
                "Error cleaning up expired password reset tokens",
                error=str(exc),
                exc_info=True,
            )
            raise