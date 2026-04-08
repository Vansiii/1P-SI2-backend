"""
Token repositories for refresh and revoked tokens.
"""
from datetime import datetime, UTC
from typing import Any, Sequence

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logging import get_logger
from ...models.refresh_token import RefreshToken
from ...models.revoked_token import RevokedToken
from ...shared.repositories.base import BaseRepository

logger = get_logger(__name__)


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    """Repository for RefreshToken operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, RefreshToken)
    
    async def find_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        """
        Find refresh token by hash.
        
        Args:
            token_hash: Token hash
            
        Returns:
            RefreshToken or None if not found
        """
        try:
            query = select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > datetime.now(UTC),
            )
            result = await self.session.execute(query)
            token = result.scalar_one_or_none()
            
            if token:
                logger.debug("Found valid refresh token", token_id=token.id, user_id=token.user_id)
            
            return token
            
        except Exception as exc:
            logger.error(
                "Error finding refresh token by hash",
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def find_by_user_id(
        self,
        user_id: int,
        active_only: bool = True,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[RefreshToken]:
        """
        Find refresh tokens by user ID.
        
        Args:
            user_id: User ID
            active_only: Only return non-revoked, non-expired tokens
            skip: Number of records to skip
            limit: Maximum number of records
            
        Returns:
            List of refresh tokens
        """
        try:
            query = select(RefreshToken).where(RefreshToken.user_id == user_id)
            
            if active_only:
                query = query.where(
                    RefreshToken.revoked_at.is_(None),
                    RefreshToken.expires_at > datetime.now(UTC),
                )
            
            query = query.order_by(RefreshToken.created_at.desc())
            query = query.offset(skip).limit(limit)
            
            result = await self.session.execute(query)
            tokens = result.scalars().all()
            
            logger.debug(
                "Found refresh tokens by user",
                user_id=user_id,
                count=len(tokens),
                active_only=active_only,
            )
            
            return tokens
            
        except Exception as exc:
            logger.error(
                "Error finding refresh tokens by user",
                user_id=user_id,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def revoke_token(self, token_id: int) -> RefreshToken:
        """
        Revoke refresh token.
        
        Args:
            token_id: Token ID
            
        Returns:
            Revoked token
        """
        try:
            from datetime import datetime, timezone
            
            token = await self.find_by_id_or_raise(token_id)
            token.revoked_at = datetime.now(timezone.utc)
            
            await self.session.commit()
            await self.session.refresh(token)
            
            logger.info("Revoked refresh token", token_id=token_id, user_id=token.user_id)
            
            return token
            
        except Exception as exc:
            await self.session.rollback()
            logger.error(
                "Error revoking refresh token",
                token_id=token_id,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def revoke_all_user_tokens(self, user_id: int) -> int:
        """
        Revoke all refresh tokens for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Number of revoked tokens
        """
        try:
            from datetime import datetime, timezone
            
            # Update all non-revoked tokens for the user
            query = (
                RefreshToken.__table__.update()
                .where(
                    RefreshToken.user_id == user_id,
                    RefreshToken.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(timezone.utc))
            )
            
            result = await self.session.execute(query)
            await self.session.commit()
            
            revoked_count = result.rowcount or 0
            
            logger.info(
                "Revoked all user refresh tokens",
                user_id=user_id,
                count=revoked_count,
            )
            
            return revoked_count
            
        except Exception as exc:
            await self.session.rollback()
            logger.error(
                "Error revoking all user refresh tokens",
                user_id=user_id,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def cleanup_expired_tokens(self) -> int:
        """
        Delete expired refresh tokens.
        
        Returns:
            Number of deleted tokens
        """
        try:
            query = delete(RefreshToken).where(
                RefreshToken.expires_at <= datetime.now(UTC)
            )
            
            result = await self.session.execute(query)
            await self.session.commit()
            
            deleted_count = result.rowcount or 0
            
            logger.info("Cleaned up expired refresh tokens", count=deleted_count)
            
            return deleted_count
            
        except Exception as exc:
            await self.session.rollback()
            logger.error(
                "Error cleaning up expired refresh tokens",
                error=str(exc),
                exc_info=True,
            )
            raise


class RevokedTokenRepository(BaseRepository[RevokedToken]):
    """Repository for RevokedToken operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, RevokedToken)
    
    async def is_token_revoked(self, jti: str) -> bool:
        """
        Check if token is revoked.
        
        Args:
            jti: JWT ID
            
        Returns:
            True if token is revoked, False otherwise
        """
        try:
            query = select(RevokedToken).where(
                RevokedToken.jti == jti,
                RevokedToken.expires_at > datetime.now(UTC),
            )
            result = await self.session.execute(query)
            token = result.scalar_one_or_none()
            
            is_revoked = token is not None
            
            if is_revoked:
                logger.debug("Token is revoked", jti=jti)
            
            return is_revoked
            
        except Exception as exc:
            logger.error(
                "Error checking token revocation",
                jti=jti,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def revoke_token(self, jti: str, expires_at: datetime) -> RevokedToken:
        """
        Add token to revocation list.
        
        Args:
            jti: JWT ID
            expires_at: Token expiration time
            
        Returns:
            Created revoked token record
        """
        try:
            # Check if already revoked
            existing = await self.session.scalar(
                select(RevokedToken).where(RevokedToken.jti == jti)
            )
            
            if existing:
                logger.debug("Token already revoked", jti=jti)
                return existing
            
            revoked_token = RevokedToken(
                jti=jti,
                expires_at=expires_at,
            )
            
            self.session.add(revoked_token)
            await self.session.commit()
            await self.session.refresh(revoked_token)
            
            logger.info("Revoked token", jti=jti)
            
            return revoked_token
            
        except Exception as exc:
            await self.session.rollback()
            logger.error(
                "Error revoking token",
                jti=jti,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def cleanup_expired_tokens(self) -> int:
        """
        Delete expired revoked tokens.
        
        Returns:
            Number of deleted tokens
        """
        try:
            query = delete(RevokedToken).where(
                RevokedToken.expires_at <= datetime.now(UTC)
            )
            
            result = await self.session.execute(query)
            await self.session.commit()
            
            deleted_count = result.rowcount or 0
            
            logger.info("Cleaned up expired revoked tokens", count=deleted_count)
            
            return deleted_count
            
        except Exception as exc:
            await self.session.rollback()
            logger.error(
                "Error cleaning up expired revoked tokens",
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def get_revoked_count(self) -> int:
        """
        Get count of currently revoked tokens.
        
        Returns:
            Number of revoked tokens
        """
        try:
            query = select(RevokedToken).where(
                RevokedToken.expires_at > datetime.now(UTC)
            )
            result = await self.session.execute(query)
            tokens = result.scalars().all()
            
            count = len(tokens)
            logger.debug("Current revoked tokens count", count=count)
            
            return count
            
        except Exception as exc:
            logger.error(
                "Error getting revoked tokens count",
                error=str(exc),
                exc_info=True,
            )
            raise