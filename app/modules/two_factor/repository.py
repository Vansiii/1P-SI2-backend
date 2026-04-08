"""
Two-factor authentication repository.
"""
from datetime import datetime, UTC
from typing import Any

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logging import get_logger
from ...models.two_factor_auth import TwoFactorAuth
from ...shared.repositories.base import BaseRepository

logger = get_logger(__name__)


class TwoFactorRepository(BaseRepository[TwoFactorAuth]):
    """Repository for TwoFactorAuth operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, TwoFactorAuth)
    
    async def find_valid_otp(self, user_id: int) -> TwoFactorAuth | None:
        """
        Find valid (non-expired) OTP for user.
        
        Args:
            user_id: User ID
            
        Returns:
            TwoFactorAuth or None if not found/invalid
        """
        try:
            query = select(TwoFactorAuth).where(
                TwoFactorAuth.user_id == user_id,
                TwoFactorAuth.otp_code_hash.isnot(None),
                TwoFactorAuth.otp_expires_at > datetime.now(UTC),
            ).order_by(TwoFactorAuth.created_at.desc())
            
            result = await self.session.execute(query)
            otp_record = result.scalar_one_or_none()
            
            if otp_record:
                logger.debug(
                    "Found valid OTP",
                    otp_id=otp_record.id,
                    user_id=user_id,
                )
            
            return otp_record
            
        except Exception as exc:
            logger.error(
                "Error finding valid OTP",
                user_id=user_id,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def find_by_user_id(self, user_id: int) -> TwoFactorAuth | None:
        """
        Find 2FA record by user ID.
        
        Args:
            user_id: User ID
            
        Returns:
            TwoFactorAuth or None if not found
        """
        try:
            query = select(TwoFactorAuth).where(
                TwoFactorAuth.user_id == user_id
            ).order_by(TwoFactorAuth.created_at.desc())
            
            result = await self.session.execute(query)
            two_factor = result.scalar_one_or_none()
            
            if two_factor:
                logger.debug(
                    "Found 2FA record",
                    two_factor_id=two_factor.id,
                    user_id=user_id,
                )
            
            return two_factor
            
        except Exception as exc:
            logger.error(
                "Error finding 2FA record by user ID",
                user_id=user_id,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def increment_attempts(self, two_factor_id: int) -> TwoFactorAuth:
        """
        Increment OTP verification attempts.
        
        Args:
            two_factor_id: 2FA record ID
            
        Returns:
            Updated 2FA record
        """
        try:
            two_factor = await self.find_by_id_or_raise(two_factor_id)
            two_factor.otp_attempts = (two_factor.otp_attempts or 0) + 1
            
            await self.session.commit()
            await self.session.refresh(two_factor)
            
            logger.info(
                "Incremented OTP attempts",
                two_factor_id=two_factor_id,
                attempts=two_factor.otp_attempts,
            )
            
            return two_factor
            
        except Exception as exc:
            await self.session.rollback()
            logger.error(
                "Error incrementing OTP attempts",
                two_factor_id=two_factor_id,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def mark_otp_as_verified(self, otp_id: int) -> TwoFactorAuth:
        """
        Clear OTP after successful verification.
        
        Args:
            otp_id: OTP record ID
            
        Returns:
            Updated OTP record
        """
        try:
            otp_record = await self.find_by_id_or_raise(otp_id)
            otp_record.otp_code_hash = None
            otp_record.otp_expires_at = None
            otp_record.otp_attempts = 0
            
            await self.session.commit()
            await self.session.refresh(otp_record)
            
            logger.info(
                "Cleared OTP after verification",
                otp_id=otp_id,
                user_id=otp_record.user_id,
            )
            
            return otp_record
            
        except Exception as exc:
            await self.session.rollback()
            logger.error(
                "Error clearing OTP",
                otp_id=otp_id,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def invalidate_user_otps(self, user_id: int) -> int:
        """
        Invalidate all OTPs for a user by clearing them.
        
        Args:
            user_id: User ID
            
        Returns:
            Number of invalidated OTPs
        """
        try:
            query = (
                TwoFactorAuth.__table__.update()
                .where(
                    TwoFactorAuth.user_id == user_id,
                    TwoFactorAuth.otp_code_hash.isnot(None),
                )
                .values(otp_code_hash=None, otp_expires_at=None, otp_attempts=0)
            )
            
            result = await self.session.execute(query)
            await self.session.commit()
            
            invalidated_count = result.rowcount or 0
            
            logger.info(
                "Invalidated user OTPs",
                user_id=user_id,
                count=invalidated_count,
            )
            
            return invalidated_count
            
        except Exception as exc:
            await self.session.rollback()
            logger.error(
                "Error invalidating user OTPs",
                user_id=user_id,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def cleanup_expired_otps(self) -> int:
        """
        Clear expired OTP codes.
        
        Returns:
            Number of cleared OTPs
        """
        try:
            query = (
                TwoFactorAuth.__table__.update()
                .where(
                    TwoFactorAuth.otp_expires_at <= datetime.now(UTC)
                )
                .values(otp_code_hash=None, otp_expires_at=None, otp_attempts=0)
            )
            
            result = await self.session.execute(query)
            await self.session.commit()
            
            cleared_count = result.rowcount or 0
            
            logger.info("Cleaned up expired OTPs", count=cleared_count)
            
            return cleared_count
            
        except Exception as exc:
            await self.session.rollback()
            logger.error(
                "Error cleaning up expired OTPs",
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def get_recent_otp_count(self, user_id: int, minutes: int = 5) -> int:
        """
        Get count of recent OTPs for rate limiting.
        
        Args:
            user_id: User ID
            minutes: Time window in minutes
            
        Returns:
            Number of recent OTPs
        """
        try:
            from datetime import timedelta
            
            since = datetime.now(UTC) - timedelta(minutes=minutes)
            
            query = select(TwoFactorAuth).where(
                TwoFactorAuth.user_id == user_id,
                TwoFactorAuth.created_at >= since,
            )
            
            result = await self.session.execute(query)
            otps = result.scalars().all()
            
            count = len(otps)
            
            logger.debug(
                "Recent OTP count",
                user_id=user_id,
                minutes=minutes,
                count=count,
            )
            
            return count
            
        except Exception as exc:
            logger.error(
                "Error getting recent OTP count",
                user_id=user_id,
                error=str(exc),
                exc_info=True,
            )
            raise