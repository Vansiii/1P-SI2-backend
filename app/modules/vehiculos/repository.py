"""
Repository para gestión de vehículos.
"""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.vehiculo import Vehiculo


class VehiculoRepository:
    """Repository para operaciones de vehículos."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, vehiculo: Vehiculo) -> Vehiculo:
        """Crear un nuevo vehículo."""
        self.session.add(vehiculo)
        await self.session.commit()
        await self.session.refresh(vehiculo)
        return vehiculo
    
    async def find_by_id(self, vehiculo_id: int) -> Optional[Vehiculo]:
        """Buscar vehículo por ID."""
        result = await self.session.execute(
            select(Vehiculo).where(Vehiculo.id == vehiculo_id)
        )
        return result.scalar_one_or_none()
    
    async def find_by_matricula(self, matricula: str) -> Optional[Vehiculo]:
        """Buscar vehículo por matrícula."""
        result = await self.session.execute(
            select(Vehiculo).where(Vehiculo.matricula == matricula.upper())
        )
        return result.scalar_one_or_none()
    
    async def find_by_client(self, client_id: int, active_only: bool = True) -> List[Vehiculo]:
        """Buscar vehículos de un cliente."""
        query = select(Vehiculo).where(Vehiculo.client_id == client_id)
        
        if active_only:
            query = query.where(Vehiculo.is_active == True)
        
        query = query.order_by(Vehiculo.created_at.desc())
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def find_all(self, active_only: bool = True) -> List[Vehiculo]:
        """Buscar todos los vehículos del sistema."""
        query = select(Vehiculo)
        
        if active_only:
            query = query.where(Vehiculo.is_active == True)
        
        query = query.order_by(Vehiculo.created_at.desc())
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def update(self, vehiculo: Vehiculo) -> Vehiculo:
        """Actualizar un vehículo."""
        await self.session.commit()
        await self.session.refresh(vehiculo)
        return vehiculo
    
    async def delete(self, vehiculo: Vehiculo) -> None:
        """Eliminar un vehículo (soft delete)."""
        vehiculo.is_active = False
        await self.session.commit()
