"""
Repository para gestión de incidentes.
"""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    
    async def find_all(
        self,
        skip: int = 0,
        limit: int = 100,
        order_by: str | None = None,
        **filters
    ) -> List[Incidente]:
        """
        Buscar todos los incidentes con relaciones cargadas.
        
        Args:
            skip: Número de registros a saltar
            limit: Máximo número de registros a retornar
            order_by: Campo para ordenar
            **filters: Filtros adicionales
            
        Returns:
            Lista de incidentes
        """
        query = (
            select(Incidente)
            .options(
                selectinload(Incidente.technician),
                selectinload(Incidente.workshop)
            )
            .offset(skip)
            .limit(limit)
        )
        
        # Apply filters
        for field, value in filters.items():
            if hasattr(Incidente, field) and value is not None:
                query = query.where(getattr(Incidente, field) == value)
        
        # Apply ordering
        if order_by and hasattr(Incidente, order_by):
            query = query.order_by(getattr(Incidente, order_by))
        else:
            query = query.order_by(Incidente.created_at.desc())
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def find_by_id(self, id: int) -> Incidente | None:
        """
        Buscar incidente por ID con relaciones cargadas.
        
        Args:
            id: ID del incidente
            
        Returns:
            Incidente o None si no se encuentra
        """
        query = (
            select(Incidente)
            .where(Incidente.id == id)
            .options(
                selectinload(Incidente.technician),
                selectinload(Incidente.workshop)
            )
        )
        
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
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
        query = (
            select(Incidente)
            .where(Incidente.client_id == client_id)
            .options(
                selectinload(Incidente.technician),
                selectinload(Incidente.workshop)
            )
            .order_by(Incidente.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        
        if estado:
            query = query.where(Incidente.estado_actual == estado)
        # Clientes ven TODAS sus incidencias sin importar el estado
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
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
        query = (
            select(Incidente)
            .where(Incidente.taller_id == taller_id)
            .options(
                selectinload(Incidente.technician),
                selectinload(Incidente.workshop)
            )
            .order_by(Incidente.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        
        if estado:
            query = query.where(Incidente.estado_actual == estado)
        else:
            # Si no se especifica estado, excluir cancelados y sin_taller_disponible
            query = query.where(
                Incidente.estado_actual.not_in(['cancelado', 'sin_taller_disponible'])
            )
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def find_by_technician(
        self,
        technician_id: int,
        estado: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Incidente]:
        """
        Buscar incidentes asignados a un técnico.
        
        Args:
            technician_id: ID del técnico
            estado: Filtrar por estado (opcional)
            skip: Número de registros a saltar
            limit: Máximo número de registros a retornar
            
        Returns:
            Lista de incidentes del técnico
        """
        query = (
            select(Incidente)
            .where(Incidente.tecnico_id == technician_id)
            .options(
                selectinload(Incidente.technician),
                selectinload(Incidente.workshop)
            )
            .order_by(Incidente.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        
        if estado:
            query = query.where(Incidente.estado_actual == estado)
        else:
            # Si no se especifica estado, excluir cancelados y sin_taller_disponible
            query = query.where(
                Incidente.estado_actual.not_in(['cancelado', 'sin_taller_disponible'])
            )
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
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
        query = (
            select(Incidente)
            .where(Incidente.estado_actual == estado)
            .options(
                selectinload(Incidente.technician),
                selectinload(Incidente.workshop)
            )
            .order_by(Incidente.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
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
        query = (
            select(Incidente)
            .where(Incidente.estado_actual == "pendiente")
            .options(
                selectinload(Incidente.technician),
                selectinload(Incidente.workshop)
            )
            .order_by(Incidente.created_at.asc())
            .offset(skip)
            .limit(limit)
        )
        
        if rechazados_ids:
            query = query.where(Incidente.id.not_in(rechazados_ids))
        
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
        Buscar incidentes pendientes.
        
        Para talleres: muestra incidentes con intentos de asignación pendientes O con timeout
        (para que el taller pueda ver las solicitudes que no respondió a tiempo).
        Para admin: muestra todos los incidentes pendientes.
        
        Args:
            taller_id: ID del taller (opcional, para filtrar por taller)
            skip: Número de registros a saltar
            limit: Máximo número de registros a retornar
            
        Returns:
            Lista de incidentes pendientes
        """
        if taller_id:
            # Para talleres: mostrar incidentes con intentos pendientes O timeout
            # Esto permite que el taller vea las solicitudes que no respondió a tiempo
            from ...models.assignment_attempt import AssignmentAttempt
            from sqlalchemy import and_, or_
            
            query = (
                select(Incidente)
                .join(
                    AssignmentAttempt,
                    and_(
                        AssignmentAttempt.incident_id == Incidente.id,
                        AssignmentAttempt.workshop_id == taller_id,
                        AssignmentAttempt.status.in_(['pending', 'timeout'])
                    )
                )
                .where(
                    and_(
                        Incidente.estado_actual == "pendiente",
                        # ✅ CRÍTICO: Excluir incidentes ya asignados a OTRO taller
                        or_(
                            Incidente.taller_id.is_(None),  # No asignado a nadie
                            Incidente.taller_id == taller_id  # O asignado a este taller
                        )
                    )
                )
                .options(
                    selectinload(Incidente.client),
                    selectinload(Incidente.vehiculo),
                    selectinload(Incidente.technician),
                    selectinload(Incidente.workshop)
                )
                .order_by(Incidente.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
            
            result = await self.session.execute(query)
            return list(result.scalars().all())
        else:
            # Para admin: mostrar todos los pendientes
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
