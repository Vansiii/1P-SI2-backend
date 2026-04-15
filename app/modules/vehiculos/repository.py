"""
Repository para gestión de vehículos.
"""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.vehiculo import Vehiculo
from ...shared.repositories.base import BaseRepository


class VehiculoRepository(BaseRepository[Vehiculo]):
    """Repository para operaciones de vehículos."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, Vehiculo)
    
    async def find_by_matricula(self, matricula: str) -> Optional[Vehiculo]:
        """
        Buscar vehículo por matrícula.
        
        Args:
            matricula: Matrícula del vehículo
            
        Returns:
            Vehículo o None si no existe
        """
        return await self.find_by_field('matricula', matricula.upper())
    
    async def find_by_client(
        self, 
        client_id: int, 
        active_only: bool = True,
        skip: int = 0,
        limit: int = 100
    ) -> List[Vehiculo]:
        """
        Buscar vehículos de un cliente.
        
        Args:
            client_id: ID del cliente
            active_only: Si True, solo retorna vehículos activos
            skip: Número de registros a saltar
            limit: Máximo número de registros a retornar
            
        Returns:
            Lista de vehículos del cliente
        """
        if active_only:
            return list(await self.find_active(
                skip=skip,
                limit=limit,
                client_id=client_id
            ))
        else:
            return list(await self.find_all(
                skip=skip,
                limit=limit,
                client_id=client_id
            ))
    
    async def find_all_vehicles(
        self, 
        active_only: bool = True,
        skip: int = 0,
        limit: int = 100
    ) -> List[Vehiculo]:
        """
        Buscar todos los vehículos del sistema.
        
        Args:
            active_only: Si True, solo retorna vehículos activos
            skip: Número de registros a saltar
            limit: Máximo número de registros a retornar
            
        Returns:
            Lista de todos los vehículos
        """
        if active_only:
            return list(await self.find_active(skip=skip, limit=limit))
        else:
            return list(await self.find_all(skip=skip, limit=limit))
