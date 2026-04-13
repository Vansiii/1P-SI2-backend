"""
Repository para gestión de incidentes.
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...models.incidente import Incidente
from ...models.evidencia import Evidencia
from ...models.evidencia_imagen import EvidenciaImagen
from ...models.evidencia_audio import EvidenciaAudio


class IncidenteRepository:
    """Repository para operaciones de incidentes."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, incidente: Incidente) -> Incidente:
        """Crear un nuevo incidente."""
        self.session.add(incidente)
        await self.session.commit()
        await self.session.refresh(incidente)
        return incidente
    
    async def find_by_id(self, incidente_id: int) -> Optional[Incidente]:
        """Buscar incidente por ID."""
        result = await self.session.execute(
            select(Incidente).where(Incidente.id == incidente_id)
        )
        return result.scalar_one_or_none()
    
    async def find_by_client(
        self,
        client_id: int,
        estado: Optional[str] = None
    ) -> List[Incidente]:
        """Buscar incidentes de un cliente."""
        query = select(Incidente).where(Incidente.client_id == client_id)
        
        if estado:
            query = query.where(Incidente.estado_actual == estado)
        
        query = query.order_by(Incidente.created_at.desc())
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def find_by_taller(
        self,
        taller_id: int,
        estado: Optional[str] = None
    ) -> List[Incidente]:
        """Buscar incidentes asignados a un taller o pendientes que no ha rechazado."""
        from ...models.rechazo_taller import RechazoTaller
        from ...core import get_logger
        
        logger = get_logger(__name__)
        
        # Primero obtener los IDs rechazados
        rechazados_result = await self.session.execute(
            select(RechazoTaller.incidente_id)
            .where(RechazoTaller.taller_id == taller_id)
        )
        rechazados_ids = [row[0] for row in rechazados_result.all()]
        
        logger.info(
            "Buscando incidentes para taller",
            taller_id=taller_id,
            estado=estado,
            rechazados_ids=rechazados_ids
        )
        
        # Construir condiciones según el filtro de estado
        if estado == "pendiente":
            # Solo pendientes que no ha rechazado
            if rechazados_ids:
                query = select(Incidente).where(
                    and_(
                        Incidente.estado_actual == "pendiente",
                        Incidente.id.not_in(rechazados_ids)
                    )
                )
            else:
                query = select(Incidente).where(
                    Incidente.estado_actual == "pendiente"
                )
        elif estado:
            # Otros estados: solo los asignados a este taller
            query = select(Incidente).where(
                and_(
                    Incidente.taller_id == taller_id,
                    Incidente.estado_actual == estado
                )
            )
        else:
            # Sin filtro: asignados al taller O pendientes que no ha rechazado
            if rechazados_ids:
                query = select(Incidente).where(
                    or_(
                        Incidente.taller_id == taller_id,
                        and_(
                            Incidente.estado_actual == "pendiente",
                            Incidente.id.not_in(rechazados_ids)
                        )
                    )
                )
            else:
                query = select(Incidente).where(
                    or_(
                        Incidente.taller_id == taller_id,
                        Incidente.estado_actual == "pendiente"
                    )
                )
        
        query = query.order_by(Incidente.created_at.desc())
        
        result = await self.session.execute(query)
        incidentes = list(result.scalars().all())
        
        logger.info(
            "Incidentes encontrados",
            taller_id=taller_id,
            count=len(incidentes),
            incidente_ids=[i.id for i in incidentes]
        )
        
        return incidentes
    
    async def find_pending_incidents(self, taller_id: Optional[int] = None) -> List[Incidente]:
        """Buscar incidentes pendientes de asignación, opcionalmente excluyendo rechazados por un taller."""
        query = select(Incidente).where(Incidente.estado_actual == "pendiente")
        
        # Si se proporciona taller_id, excluir los que ese taller ha rechazado
        if taller_id:
            from ...models.rechazo_taller import RechazoTaller
            from ...core import get_logger
            
            logger = get_logger(__name__)
            
            rechazados_result = await self.session.execute(
                select(RechazoTaller.incidente_id)
                .where(RechazoTaller.taller_id == taller_id)
            )
            rechazados_ids = [row[0] for row in rechazados_result.all()]
            
            logger.info(
                "Filtrando pendientes para taller",
                taller_id=taller_id,
                rechazados_ids=rechazados_ids
            )
            
            if rechazados_ids:
                query = query.where(Incidente.id.not_in(rechazados_ids))
        
        query = query.order_by(Incidente.created_at.asc())
        
        result = await self.session.execute(query)
        incidentes = list(result.scalars().all())
        
        if taller_id:
            logger.info(
                "Pendientes encontrados para taller",
                taller_id=taller_id,
                count=len(incidentes),
                incidente_ids=[i.id for i in incidentes]
            )
        
        return incidentes
    
    async def find_all(self) -> List[Incidente]:
        """Buscar todos los incidentes del sistema."""
        result = await self.session.execute(
            select(Incidente).order_by(Incidente.created_at.desc())
        )
        return list(result.scalars().all())
    
    async def find_all_by_estado(self, estado: str) -> List[Incidente]:
        """Buscar todos los incidentes por estado."""
        result = await self.session.execute(
            select(Incidente)
            .where(Incidente.estado_actual == estado)
            .order_by(Incidente.created_at.desc())
        )
        return list(result.scalars().all())
    
    async def update(self, incidente: Incidente) -> Incidente:
        """Actualizar un incidente."""
        await self.session.commit()
        await self.session.refresh(incidente)
        return incidente
    
    async def create_evidencia(self, evidencia: Evidencia) -> Evidencia:
        """Crear una evidencia."""
        self.session.add(evidencia)
        await self.session.commit()
        await self.session.refresh(evidencia)
        return evidencia
    
    async def create_evidencia_imagen(self, evidencia_imagen: EvidenciaImagen) -> EvidenciaImagen:
        """Crear una evidencia de imagen."""
        self.session.add(evidencia_imagen)
        await self.session.commit()
        await self.session.refresh(evidencia_imagen)
        return evidencia_imagen
    
    async def create_evidencia_audio(self, evidencia_audio: EvidenciaAudio) -> EvidenciaAudio:
        """Crear una evidencia de audio."""
        self.session.add(evidencia_audio)
        await self.session.commit()
        await self.session.refresh(evidencia_audio)
        return evidencia_audio
    
    async def find_evidencias_by_incidente(self, incidente_id: int) -> List[Evidencia]:
        """Buscar evidencias de un incidente."""
        result = await self.session.execute(
            select(Evidencia)
            .where(Evidencia.incidente_id == incidente_id)
            .order_by(Evidencia.created_at.asc())
        )
        return list(result.scalars().all())
    
    async def find_imagenes_by_evidencia(self, evidencia_id: int) -> List[EvidenciaImagen]:
        """Buscar imágenes de una evidencia."""
        result = await self.session.execute(
            select(EvidenciaImagen).where(EvidenciaImagen.evidencia_id == evidencia_id)
        )
        return list(result.scalars().all())
    
    async def find_audios_by_evidencia(self, evidencia_id: int) -> List[EvidenciaAudio]:
        """Buscar audios de una evidencia."""
        result = await self.session.execute(
            select(EvidenciaAudio).where(EvidenciaAudio.evidencia_id == evidencia_id)
        )
        return list(result.scalars().all())
