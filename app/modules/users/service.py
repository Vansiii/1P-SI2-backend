"""
Service for user management operations.
"""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_logger, UserNotFoundException
from ...core.constants import UserType
from ...models.administrator import Administrator
from ...models.client import Client
from ...models.technician import Technician
from ...models.user import User
from ...models.workshop import Workshop
from .repository import (
    AdministratorRepository,
    ClientRepository,
    TechnicianRepository,
    UserRepository,
    WorkshopRepository,
)

logger = get_logger(__name__)


class UserService:
    """Service for user management operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.client_repo = ClientRepository(session)
        self.workshop_repo = WorkshopRepository(session)
        self.technician_repo = TechnicianRepository(session)
        self.admin_repo = AdministratorRepository(session)
    
    async def get_user_by_id(self, user_id: int) -> User:
        """Get user by ID."""
        user = await self.user_repo.find_by_id(user_id)
        if not user:
            raise UserNotFoundException(f"User {user_id}")
        return user
    
    async def get_users_by_type(self, user_type: str, active_only: bool = True) -> List[User]:
        """Get all users by type with proper model loading."""
        if user_type == "workshop":
            stmt = select(Workshop)
            if active_only:
                stmt = stmt.where(Workshop.is_active == True)
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        elif user_type == "client":
            stmt = select(Client)
            if active_only:
                stmt = stmt.where(Client.is_active == True)
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        elif user_type == "technician":
            stmt = select(Technician)
            if active_only:
                stmt = stmt.where(Technician.is_active == True)
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        elif user_type == "administrator":
            stmt = select(Administrator)
            if active_only:
                stmt = stmt.where(Administrator.is_active == True)
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        else:
            if active_only:
                return await self.user_repo.find_active_by_user_type(user_type)
            return await self.user_repo.find_by_user_type(user_type)
    
    async def deactivate_user(self, user_id: int) -> None:
        """Deactivate a user account."""
        user = await self.user_repo.find_by_id(user_id)
        if not user:
            raise UserNotFoundException(f"User {user_id}")
        
        await self.user_repo.update(user_id, {"is_active": False})
        logger.info("User deactivated", user_id=user_id, email=user.email)
    
    async def activate_user(self, user_id: int) -> None:
        """Activate a user account."""
        user = await self.user_repo.find_by_id(user_id)
        if not user:
            raise UserNotFoundException(f"User {user_id}")
        
        await self.user_repo.update(user_id, {"is_active": True})
        logger.info("User activated", user_id=user_id, email=user.email)


class ClientService:
    """Service for client-specific operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.client_repo = ClientRepository(session)
    
    async def get_client_by_id(self, client_id: int) -> Client:
        """Get client by ID."""
        client = await self.client_repo.find_by_id(client_id)
        if not client:
            raise UserNotFoundException(f"Client {client_id}")
        return client
    
    async def get_client_by_ci(self, ci: str) -> Optional[Client]:
        """Get client by CI."""
        return await self.client_repo.find_by_ci(ci)
    
    async def update_client_address(self, client_id: int, direccion: str) -> Client:
        """Update client address."""
        client = await self.get_client_by_id(client_id)
        updated_client = await self.client_repo.update(client_id, {"direccion": direccion})
        logger.info("Client address updated", client_id=client_id)
        return updated_client


class WorkshopService:
    """Service for workshop-specific operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.workshop_repo = WorkshopRepository(session)
    
    async def get_workshop_by_id(self, workshop_id: int) -> Workshop:
        """Get workshop by ID."""
        workshop = await self.workshop_repo.find_by_id(workshop_id)
        if not workshop:
            raise UserNotFoundException(f"Workshop {workshop_id}")
        return workshop
    
    async def find_nearby_workshops(
        self, 
        latitude: float, 
        longitude: float, 
        radius_km: float = 10.0
    ) -> List[Workshop]:
        """Find workshops near a location."""
        return await self.workshop_repo.find_by_location(latitude, longitude, radius_km)
    
    async def update_workshop_location(
        self, 
        workshop_id: int, 
        latitude: float, 
        longitude: float
    ) -> Workshop:
        """Update workshop location."""
        workshop = await self.get_workshop_by_id(workshop_id)
        updated_workshop = await self.workshop_repo.update(
            workshop_id, 
            {"latitude": latitude, "longitude": longitude}
        )
        logger.info("Workshop location updated", workshop_id=workshop_id)
        return updated_workshop


class TechnicianService:
    """Service for technician-specific operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.technician_repo = TechnicianRepository(session)
    
    async def get_technician_by_id(self, technician_id: int) -> Technician:
        """Get technician by ID."""
        technician = await self.technician_repo.find_by_id(technician_id)
        if not technician:
            raise UserNotFoundException(f"Technician {technician_id}")
        return technician
    
    async def get_workshop_technicians(self, workshop_id: int) -> List[Technician]:
        """Get all technicians for a workshop."""
        return await self.technician_repo.find_by_workshop(workshop_id)
    
    async def get_available_technicians(self, workshop_id: int) -> List[Technician]:
        """Get available technicians for a workshop."""
        return await self.technician_repo.find_available_by_workshop(workshop_id)
    
    async def update_technician_availability(
        self, 
        technician_id: int, 
        is_available: bool
    ) -> Technician:
        """Update technician availability."""
        technician = await self.get_technician_by_id(technician_id)
        updated_technician = await self.technician_repo.update(
            technician_id, 
            {"is_available": is_available}
        )
        logger.info(
            "Technician availability updated", 
            technician_id=technician_id, 
            is_available=is_available
        )
        return updated_technician
    
    async def update_technician_location(
        self, 
        technician_id: int, 
        latitude: float, 
        longitude: float
    ) -> Technician:
        """Update technician current location."""
        technician = await self.get_technician_by_id(technician_id)
        updated_technician = await self.technician_repo.update(
            technician_id, 
            {
                "current_latitude": latitude, 
                "current_longitude": longitude
            }
        )
        logger.info("Technician location updated", technician_id=technician_id)
        return updated_technician


class AdministratorService:
    """Service for administrator-specific operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.admin_repo = AdministratorRepository(session)
    
    async def get_administrator_by_id(self, admin_id: int) -> Administrator:
        """Get administrator by ID."""
        admin = await self.admin_repo.find_by_id(admin_id)
        if not admin:
            raise UserNotFoundException(f"Administrator {admin_id}")
        return admin
    
    async def get_administrators_by_role(self, role_level: int) -> List[Administrator]:
        """Get administrators by role level."""
        return await self.admin_repo.find_by_role_level(role_level)