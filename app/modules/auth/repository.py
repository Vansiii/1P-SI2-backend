"""
User repository for authentication operations.
"""
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logging import get_logger
from ...models.administrator import Administrator
from ...models.client import Client
from ...models.technician import Technician
from ...models.user import User
from ...models.workshop import Workshop
from ...shared.repositories.base import BaseRepository

logger = get_logger(__name__)


class UserRepository(BaseRepository[User]):
    """Repository for User operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, User)
    
    async def find_by_email(self, email: str) -> User | None:
        """
        Find user by email address.
        
        Args:
            email: Email address
            
        Returns:
            User or None if not found
        """
        try:
            query = select(User).where(User.email == email.lower())
            result = await self.session.execute(query)
            user = result.scalar_one_or_none()
            
            if user:
                logger.debug("Found user by email", email=email, user_id=user.id)
            
            return user
            
        except Exception as exc:
            logger.error(
                "Error finding user by email",
                email=email,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def find_active_by_email(self, email: str) -> User | None:
        """
        Find active user by email address.
        
        Args:
            email: Email address
            
        Returns:
            Active user or None if not found
        """
        try:
            query = select(User).where(
                User.email == email.lower(),
                User.is_active == True
            )
            result = await self.session.execute(query)
            user = result.scalar_one_or_none()
            
            if user:
                logger.debug("Found active user by email", email=email, user_id=user.id)
            
            return user
            
        except Exception as exc:
            logger.error(
                "Error finding active user by email",
                email=email,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def email_exists(self, email: str, exclude_id: int | None = None) -> bool:
        """
        Check if email already exists.
        
        Args:
            email: Email address to check
            exclude_id: User ID to exclude from check (for updates)
            
        Returns:
            True if email exists, False otherwise
        """
        try:
            query = select(User).where(User.email == email.lower())
            
            if exclude_id:
                query = query.where(User.id != exclude_id)
            
            result = await self.session.execute(query)
            user = result.scalar_one_or_none()
            
            exists = user is not None
            logger.debug("Email existence check", email=email, exists=exists)
            
            return exists
            
        except Exception as exc:
            logger.error(
                "Error checking email existence",
                email=email,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def find_by_user_type(
        self,
        user_type: str,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = True,
    ) -> Sequence[User]:
        """
        Find users by type.
        
        Args:
            user_type: Type of user
            skip: Number of records to skip
            limit: Maximum number of records
            active_only: Only return active users
            
        Returns:
            List of users
        """
        try:
            query = select(User).where(User.user_type == user_type)
            
            if active_only:
                query = query.where(User.is_active == True)
            
            query = query.offset(skip).limit(limit)
            
            result = await self.session.execute(query)
            users = result.scalars().all()
            
            logger.debug(
                "Found users by type",
                user_type=user_type,
                count=len(users),
                active_only=active_only,
            )
            
            return users
            
        except Exception as exc:
            logger.error(
                "Error finding users by type",
                user_type=user_type,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def update_last_login(self, user_id: int) -> None:
        """
        Update user's last login timestamp.
        
        Args:
            user_id: User ID
        """
        try:
            from datetime import datetime, UTC
            
            user = await self.find_by_id_or_raise(user_id)
            user.updated_at = datetime.now(UTC)
            
            await self.session.commit()
            
            logger.debug("Updated last login", user_id=user_id)
            
        except Exception as exc:
            await self.session.rollback()
            logger.error(
                "Error updating last login",
                user_id=user_id,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def deactivate_user(self, user_id: int) -> User:
        """
        Deactivate user account.
        
        Args:
            user_id: User ID
            
        Returns:
            Updated user
        """
        try:
            user = await self.find_by_id_or_raise(user_id)
            user.is_active = False
            
            await self.session.commit()
            await self.session.refresh(user)
            
            logger.info("Deactivated user", user_id=user_id, email=user.email)
            
            return user
            
        except Exception as exc:
            await self.session.rollback()
            logger.error(
                "Error deactivating user",
                user_id=user_id,
                error=str(exc),
                exc_info=True,
            )
            raise
    
    async def activate_user(self, user_id: int) -> User:
        """
        Activate user account.
        
        Args:
            user_id: User ID
            
        Returns:
            Updated user
        """
        try:
            user = await self.find_by_id_or_raise(user_id)
            user.is_active = True
            user.blocked_until = None  # Clear any blocks
            
            await self.session.commit()
            await self.session.refresh(user)
            
            logger.info("Activated user", user_id=user_id, email=user.email)
            
            return user
            
        except Exception as exc:
            await self.session.rollback()
            logger.error(
                "Error activating user",
                user_id=user_id,
                error=str(exc),
                exc_info=True,
            )
            raise


class ClientRepository(BaseRepository[Client]):
    """Repository for Client operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, Client)


class WorkshopRepository(BaseRepository[Workshop]):
    """Repository for Workshop operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, Workshop)
    
    async def find_by_location(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 10.0,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Workshop]:
        """
        Find workshops by location within radius.
        
        Args:
            latitude: Latitude
            longitude: Longitude
            radius_km: Search radius in kilometers
            skip: Number of records to skip
            limit: Maximum number of records
            
        Returns:
            List of workshops within radius
        """
        try:
            # This is a simplified version - in production you'd use PostGIS or similar
            # For now, we'll just return active workshops
            query = select(Workshop).where(
                Workshop.is_active == True
            ).offset(skip).limit(limit)
            
            result = await self.session.execute(query)
            workshops = result.scalars().all()
            
            logger.debug(
                "Found workshops by location",
                latitude=latitude,
                longitude=longitude,
                radius_km=radius_km,
                count=len(workshops),
            )
            
            return workshops
            
        except Exception as exc:
            logger.error(
                "Error finding workshops by location",
                latitude=latitude,
                longitude=longitude,
                error=str(exc),
                exc_info=True,
            )
            raise


class TechnicianRepository(BaseRepository[Technician]):
    """Repository for Technician operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, Technician)
    
    async def find_by_workshop(
        self,
        workshop_id: int,
        available_only: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Technician]:
        """
        Find technicians by workshop.
        
        Args:
            workshop_id: Workshop ID
            available_only: Only return available technicians
            skip: Number of records to skip
            limit: Maximum number of records
            
        Returns:
            List of technicians
        """
        try:
            query = select(Technician).where(
                Technician.workshop_id == workshop_id,
                Technician.is_active == True,
            )
            
            if available_only:
                query = query.where(Technician.is_available == True)
            
            query = query.offset(skip).limit(limit)
            
            result = await self.session.execute(query)
            technicians = result.scalars().all()
            
            logger.debug(
                "Found technicians by workshop",
                workshop_id=workshop_id,
                available_only=available_only,
                count=len(technicians),
            )
            
            return technicians
            
        except Exception as exc:
            logger.error(
                "Error finding technicians by workshop",
                workshop_id=workshop_id,
                error=str(exc),
                exc_info=True,
            )
            raise


class AdministratorRepository(BaseRepository[Administrator]):
    """Repository for Administrator operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, Administrator)