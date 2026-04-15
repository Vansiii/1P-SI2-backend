"""
Repository para gestión de incidentes.
"""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.incidente import Incidente
from ...models.evidencia import Evidencia
from ...models.evidencia_imagen import EvidenciaImagen
from ...models.evidencia_audio import EvidenciaAudio
from ...shared.repositories.base import BaseRepository
from ...core.logging import get_logger

logger = get_logger(__name__)


class IncidenteRepository(BaseRepository[Incidente]):
    """Repository para operaciones de incidentes."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, Incidente)
    
    async def find_by_client(
        self,
        client_id: int,
        estado: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Incidente]:
        """
        Buscar incidentes de un cliente.
        
        Args:
            client_id: ID del cliente
            estado: Filtrar por estado (opcional)
            skip: Número de registros a saltar
            limit: Máximo número de registros a retornar
            
        Returns:
            Lista de incidentes del cliente
        """
        filters = {'client_id': client_id}
        if estado:
            filters['estado_actual'] = estado
        
        return list(await self.find_all(
            skip=skip,
            limit=limit,
            order_by='created_at',
            **filters
        ))
    
    async def find_by_taller(
        self,
        taller_id: int,
        estado: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Incidente]:
        """
        Buscar incidentes asignados a un taller.
        
        Args:
            taller_id: ID del taller
            estado: Filtrar por estado (opcional)
            skip: Número de registros a saltar
            limit: Máximo número de registros a retornar
            
        Returns:
            Lista de incidentes del taller
        """
        filters = {'taller_id': taller_id}
        if estado:
            filters['estado_actual'] = estado
        
        return list(await self.find_all(
            skip=skip,
            limit=limit,
            order_by='created_at',
            **filters
        ))
    
    async def find_by_estado(
        self,
        estado: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Incidente]:
        """
        Buscar incidentes por estado.
        
        Args:
            estado: Estado del incidente
            skip: Número de registros a saltar
            limit: Máximo número de registros a retornar
            
        Returns:
            Lista de incidentes con el estado especificado
        """
        return list(await self.find_all(
            skip=skip,
            limit=limit,
            order_by='created_at',
            estado_actual=estado
        ))
    
    async def find_pending_not_rejected_by_taller(
        self,
        taller_id: int,
        skip: int = 0,
        limit: int = 100
    ) -> List[Incidente]:
        """
        Buscar incidentes pendientes que no han sido rechazados por un taller.
        
        Args:
            taller_id: ID del taller
            skip: Número de registros a saltar
            limit: Máximo número de registros a retornar
            
        Returns:
            Lista de incidentes pendientes no rechazados
        """
        from ...models.rechazo_taller import RechazoTaller
        
        # Obtener IDs de incidentes rechazados por este taller
        rechazados_result = await self.session.execute(
            select(RechazoTaller.incidente_id)
            .where(RechazoTaller.taller_id == taller_id)
        )
        rechazados_ids = [row[0] for row in rechazados_result.all()]
        
        logger.debug(
            "Buscando pendientes no rechazados",
            taller_id=taller_id,
            rechazados_count=len(rechazados_ids)
        )
        
        # Buscar pendientes excluyendo rechazados
        query = select(Incidente).where(
            Incidente.estado_actual == "pendiente"
        )
        
        if rechazados_ids:
            query = query.where(Incidente.id.not_in(rechazados_ids))
        
        query = query.order_by(Incidente.created_at.asc()).offset(skip).limit(limit)
        
        result = await self.session.execute(query)
        incidentes = list(result.scalars().all())
        
        logger.debug(
            "Pendientes encontrados",
            taller_id=taller_id,
            count=len(incidentes)
        )
        
        return incidentes
    
    async def find_pending_incidents(
        self,
        taller_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Incidente]:
        """
        Buscar incidentes pendientes, opcionalmente excluyendo rechazados por un taller.
        
        Args:
            taller_id: ID del taller (opcional, para excluir rechazados)
            skip: Número de registros a saltar
            limit: Máximo número de registros a retornar
            
        Returns:
            Lista de incidentes pendientes
        """
        if taller_id:
            return await self.find_pending_not_rejected_by_taller(taller_id, skip, limit)
        else:
            return await self.find_by_estado("pendiente", skip, limit)
    
    # Métodos para evidencias
    async def create_evidencia(self, evidencia: Evidencia) -> Evidencia:
        """
        Crear una evidencia.
        
        Args:
            evidencia: Objeto Evidencia a crear
            
        Returns:
            Evidencia creada
        """
        self.session.add(evidencia)
        await self.session.flush()
        await self.session.refresh(evidencia)
        return evidencia
    
    async def create_evidencia_imagen(self, evidencia_imagen: EvidenciaImagen) -> EvidenciaImagen:
        """
        Crear una evidencia de imagen.
        
        Args:
            evidencia_imagen: Objeto EvidenciaImagen a crear
            
        Returns:
            EvidenciaImagen creada
        """
        self.session.add(evidencia_imagen)
        await self.session.flush()
        await self.session.refresh(evidencia_imagen)
        return evidencia_imagen
    
    async def create_evidencia_audio(self, evidencia_audio: EvidenciaAudio) -> EvidenciaAudio:
        """
        Crear una evidencia de audio.
        
        Args:
            evidencia_audio: Objeto EvidenciaAudio a crear
            
        Returns:
            EvidenciaAudio creada
        """
        self.session.add(evidencia_audio)
        await self.session.flush()
        await self.session.refresh(evidencia_audio)
        return evidencia_audio
    
    async def find_evidencias_by_incidente(self, incidente_id: int) -> List[Evidencia]:
        """
        Buscar evidencias de un incidente.
        
        Args:
            incidente_id: ID del incidente
            
        Returns:
            Lista de evidencias del incidente
        """
        result = await self.session.execute(
            select(Evidencia)
            .where(Evidencia.incidente_id == incidente_id)
            .order_by(Evidencia.created_at.asc())
        )
        return list(result.scalars().all())
    
    async def find_imagenes_by_evidencia(self, evidencia_id: int) -> List[EvidenciaImagen]:
        """
        Buscar imágenes de una evidencia.
        
        Args:
            evidencia_id: ID de la evidencia
            
        Returns:
            Lista de imágenes de la evidencia
        """
        result = await self.session.execute(
            select(EvidenciaImagen).where(EvidenciaImagen.evidencia_id == evidencia_id)
        )
        return list(result.scalars().all())
    
    async def find_audios_by_evidencia(self, evidencia_id: int) -> List[EvidenciaAudio]:
        """
        Buscar audios de una evidencia.
        
        Args:
            evidencia_id: ID de la evidencia
            
        Returns:
            Lista de audios de la evidencia
        """
        result = await self.session.execute(
            select(EvidenciaAudio).where(EvidenciaAudio.evidencia_id == evidencia_id)
        )
        return list(result.scalars().all())
