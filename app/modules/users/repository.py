"""
Repository for user management operations.
"""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.constants import UserType
from ...models.administrator import Administrator
from ...models.client import Client
from ...models.technician import Technician
from ...models.user import User
from ...models.workshop import Workshop
from ...shared.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for user management operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, User)
    
    async def find_by_user_type(self, user_type: str) -> List[User]:
        """Find all users by type."""
        stmt = select(self.model).where(self.model.user_type == user_type)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def find_active_by_user_type(self, user_type: str) -> List[User]:
        """Find all active users by type."""
        stmt = select(self.model).where(
            self.model.user_type == user_type,
            self.model.is_active == True
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ClientRepository(BaseRepository[Client]):
    """Repository for client-specific operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, Client)
    
    async def find_by_ci(self, ci: str) -> Optional[Client]:
        """Find client by CI."""
        stmt = select(self.model).where(self.model.ci == ci)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class WorkshopRepository(BaseRepository[Workshop]):
    """Repository for workshop-specific operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, Workshop)
    
    async def find_by_location(
        self, 
        latitude: float, 
        longitude: float, 
        radius_km: float
    ) -> List[Workshop]:
        """Find workshops within a radius of a location."""
        # This would need PostGIS for proper geographic queries
        # For now, we'll use a simple bounding box approximation
        lat_delta = radius_km / 111.0  # Rough conversion: 1 degree ≈ 111 km
        lon_delta = radius_km / (111.0 * abs(latitude))
        
        stmt = select(self.model).where(
            self.model.latitude.between(latitude - lat_delta, latitude + lat_delta),
            self.model.longitude.between(longitude - lon_delta, longitude + lon_delta),
            self.model.is_active == True
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class TechnicianRepository(BaseRepository[Technician]):
    """Repository for technician-specific operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, Technician)
    
    async def find_by_workshop(self, workshop_id: int) -> List[Technician]:
        """Find all technicians for a workshop."""
        stmt = select(self.model).where(
            self.model.workshop_id == workshop_id,
            self.model.is_active == True
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def find_available_by_workshop(self, workshop_id: int) -> List[Technician]:
        """Find available technicians for a workshop."""
        stmt = select(self.model).where(
            self.model.workshop_id == workshop_id,
            self.model.is_available == True,
            self.model.is_active == True
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class AdministratorRepository(BaseRepository[Administrator]):
    """Repository for administrator-specific operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, Administrator)
    
    async def find_by_role_level(self, role_level: int) -> List[Administrator]:
        """Find administrators by role level."""
        stmt = select(self.model).where(
            self.model.role_level == role_level,
            self.model.is_active == True
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())