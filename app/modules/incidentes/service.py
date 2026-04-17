"""
Service para gestión de incidentes.
"""
from datetime import datetime, UTC
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_logger, NotFoundException, ForbiddenException
from ...models.incidente import Incidente
from ...models.evidencia import Evidencia
from ...models.evidencia_imagen import EvidenciaImagen
from ...models.evidencia_audio import EvidenciaAudio
from ...models.vehiculo import Vehiculo
from .repository import IncidenteRepository
from .schemas import IncidenteCreateRequest

logger = get_logger(__name__)


class IncidenteService:
    """Service para lógica de negocio de incidentes."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = IncidenteRepository(session)
    
    async def create_incidente(
        self,
        client_id: int,
        request: IncidenteCreateRequest
    ) -> Incidente:
        """Crear un nuevo incidente/emergencia vehicular."""
        # Verificar que el vehículo existe y pertenece al cliente
        from sqlalchemy import select
        result = await self.session.execute(
            select(Vehiculo).where(
                Vehiculo.id == request.vehiculo_id,
                Vehiculo.client_id == client_id,
                Vehiculo.is_active == True
            )
        )
        vehiculo = result.scalar_one_or_none()
        
        if not vehiculo:
            raise NotFoundException(
                f"Vehículo con ID {request.vehiculo_id} no encontrado o no pertenece al cliente"
            )
        
        # Crear el incidente
        incidente = Incidente(
            client_id=client_id,
            vehiculo_id=request.vehiculo_id,
            latitude=request.latitude,
            longitude=request.longitude,
            direccion_referencia=request.direccion_referencia,
            descripcion=request.descripcion,
            estado_actual="pendiente",
            es_ambiguo=False,  # Se actualizará cuando se procese con IA
        )
        
        # Agregar a la sesión y hacer flush
        self.session.add(incidente)
        await self.session.flush()
        await self.session.refresh(incidente)
        created_incidente = incidente
        
        # Crear evidencias de texto (descripción principal)
        evidencia_texto = Evidencia(
            incidente_id=created_incidente.id,
            uploaded_by_user_id=client_id,
            tipo="TEXT",
            descripcion=request.descripcion,
        )
        await self.repository.create_evidencia(evidencia_texto)
        
        # Crear evidencias de imágenes
        if request.imagenes:
            evidencia_imagenes = Evidencia(
                incidente_id=created_incidente.id,
                uploaded_by_user_id=client_id,
                tipo="IMAGE",
                descripcion="Imágenes del incidente",
            )
            evidencia_img_created = await self.repository.create_evidencia(evidencia_imagenes)
            
            for imagen_url in request.imagenes:
                evidencia_imagen = EvidenciaImagen(
                    evidencia_id=evidencia_img_created.id,
                    file_url=imagen_url,
                    file_name="incident_image.jpg",  # Nombre genérico por ahora
                    file_type="image",
                    mime_type="image/jpeg",
                    size=0,  # Se actualizará si se tiene la info
                    uploaded_by=client_id,
                )
                await self.repository.create_evidencia_imagen(evidencia_imagen)
        
        # Crear evidencias de audios
        if request.audios:
            evidencia_audios = Evidencia(
                incidente_id=created_incidente.id,
                uploaded_by_user_id=client_id,
                tipo="AUDIO",
                descripcion="Audios del incidente",
            )
            evidencia_audio_created = await self.repository.create_evidencia(evidencia_audios)
            
            for audio_url in request.audios:
                evidencia_audio = EvidenciaAudio(
                    evidencia_id=evidencia_audio_created.id,
                    file_url=audio_url,
                    file_name="incident_audio.mp3",  # Nombre genérico por ahora
                    file_type="audio",
                    mime_type="audio/mpeg",
                    size=0,  # Se actualizará si se tiene la info
                    uploaded_by=client_id,
                )
                await self.repository.create_evidencia_audio(evidencia_audio)
        
        # Commit all changes
        await self.session.commit()
        
        logger.info(
            "Incidente creado",
            incidente_id=created_incidente.id,
            client_id=client_id,
            vehiculo_id=request.vehiculo_id,
            estado="pendiente"
        )

        # Trigger asynchronous AI processing without delaying the incident response.
        try:
            from .ai_service import IncidentAIService

            IncidentAIService.schedule_incident_processing(created_incidente.id)
        except Exception as exc:
            logger.warning(
                "Failed to schedule incident AI processing",
                incidente_id=created_incidente.id,
                error=str(exc),
            )
        
        return created_incidente
    
    async def get_incidente(
        self,
        incidente_id: int,
        user_id: int,
        user_type: str
    ) -> Incidente:
        """Obtener un incidente por ID."""
        incidente = await self.repository.find_by_id(incidente_id)
        
        if not incidente:
            raise NotFoundException(f"Incidente con ID {incidente_id} no encontrado")
        
        # Verificar permisos según tipo de usuario
        if user_type == "client" and incidente.client_id != user_id:
            raise ForbiddenException("No tienes permiso para ver este incidente")
        elif user_type == "workshop":
            # Los talleres pueden ver:
            # 1. Incidentes asignados a ellos
            # 2. Incidentes pendientes (para poder aceptarlos)
            if incidente.taller_id is not None and incidente.taller_id != user_id:
                raise ForbiddenException("No tienes permiso para ver este incidente")
        elif user_type == "technician":
            # Verificar que el técnico pertenece al taller asignado
            from sqlalchemy import select
            from ...models.technician import Technician
            result = await self.session.execute(
                select(Technician).where(Technician.id == user_id)
            )
            technician = result.scalar_one_or_none()
            if not technician or technician.workshop_id != incidente.taller_id:
                raise ForbiddenException("No tienes permiso para ver este incidente")
        
        return incidente
    
    async def get_client_incidentes(
        self,
        client_id: int,
        estado: Optional[str] = None
    ) -> List[Incidente]:
        """Obtener incidentes de un cliente."""
        return await self.repository.find_by_client(client_id, estado)
    
    async def get_taller_incidentes(
        self,
        taller_id: int,
        estado: Optional[str] = None
    ) -> List[Incidente]:
        """Obtener incidentes asignados a un taller."""
        return await self.repository.find_by_taller(taller_id, estado)
    
    async def get_pending_incidentes(self, taller_id: Optional[int] = None) -> List[Incidente]:
        """Obtener incidentes pendientes de asignación."""
        return await self.repository.find_pending_incidents(taller_id)
    
    async def accept_incidente(
        self,
        incidente_id: int,
        taller_id: int
    ) -> Incidente:
        """Aceptar un incidente y asignarlo al taller."""
        # Obtener el incidente
        incidente = await self.repository.find_by_id(incidente_id)
        
        if not incidente:
            raise NotFoundException(f"Incidente con ID {incidente_id} no encontrado")
        
        # Verificar que el incidente esté pendiente
        if incidente.estado_actual != "pendiente":
            from ...core import ValidationException
            raise ValidationException(f"El incidente ya no está pendiente (estado actual: {incidente.estado_actual})")
        
        # Asignar el taller y cambiar estado
        incidente.taller_id = taller_id
        incidente.estado_actual = "asignado"
        incidente.assigned_at = datetime.now(UTC)
        
        # Commit changes
        await self.session.commit()
        await self.session.refresh(incidente)
        
        logger.info(
            "Incidente aceptado",
            incidente_id=incidente_id,
            taller_id=taller_id,
            estado="asignado"
        )
        
        # TODO: Notificar al cliente que su solicitud fue aceptada
        
        return incidente
    
    async def reject_incidente(
        self,
        incidente_id: int,
        taller_id: int,
        motivo: str
    ) -> Incidente:
        """Rechazar un incidente."""
        # Obtener el incidente
        incidente = await self.repository.find_by_id(incidente_id)
        
        if not incidente:
            raise NotFoundException(f"Incidente con ID {incidente_id} no encontrado")
        
        # Verificar que el incidente esté pendiente
        if incidente.estado_actual != "pendiente":
            from ...core import ValidationException
            raise ValidationException(f"El incidente ya no está pendiente (estado actual: {incidente.estado_actual})")
        
        # Guardar el rechazo en la base de datos
        from ...models.rechazo_taller import RechazoTaller
        rechazo = RechazoTaller(
            incidente_id=incidente_id,
            taller_id=taller_id,
            motivo=motivo
        )
        self.session.add(rechazo)
        await self.session.commit()
        
        logger.info(
            "Incidente rechazado y guardado en BD",
            incidente_id=incidente_id,
            taller_id=taller_id,
            motivo=motivo
        )
        
        # TODO: El motor de asignación debería buscar otro taller
        # TODO: Notificar al cliente que se está buscando otro proveedor
        
        # Por ahora, el incidente permanece pendiente para que otro taller lo tome
        return incidente
    
    async def get_all_incidentes(self) -> List[Incidente]:
        """Obtener todos los incidentes del sistema (solo admin)."""
        # Usar límite alto para obtener todos
        return list(await self.repository.find_all(skip=0, limit=10000))
    
    async def get_all_incidentes_by_estado(self, estado: str) -> List[Incidente]:
        """Obtener todos los incidentes por estado (solo admin)."""
        return await self.repository.find_by_estado(estado, skip=0, limit=10000)
    
    async def update_estado(
        self,
        incidente_id: int,
        nuevo_estado: str,
        user_id: int,
        user_type: str
    ) -> Incidente:
        """Actualizar el estado de un incidente."""
        incidente = await self.get_incidente(incidente_id, user_id, user_type)
        
        # Validar transición de estado
        estados_validos = ["pendiente", "asignado", "en_proceso", "resuelto", "cancelado"]
        if nuevo_estado not in estados_validos:
            from ...core import ValidationException
            raise ValidationException(f"Estado '{nuevo_estado}' no válido")
        
        incidente.estado_actual = nuevo_estado
        
        # Actualizar timestamps según el estado
        if nuevo_estado == "asignado" and not incidente.assigned_at:
            incidente.assigned_at = datetime.now(UTC)
        elif nuevo_estado == "resuelto" and not incidente.resolved_at:
            incidente.resolved_at = datetime.now(UTC)
        
        # Commit changes
        await self.session.commit()
        await self.session.refresh(incidente)
        
        logger.info(
            "Estado de incidente actualizado",
            incidente_id=incidente_id,
            nuevo_estado=nuevo_estado,
            user_id=user_id,
            user_type=user_type
        )
        
        return incidente
    
    async def get_incidente_with_evidencias(
        self,
        incidente_id: int,
        user_id: int,
        user_type: str
    ) -> Tuple[Incidente, List[Evidencia], List[EvidenciaImagen], List[EvidenciaAudio]]:
        """Obtener incidente con todas sus evidencias."""
        incidente = await self.get_incidente(incidente_id, user_id, user_type)
        
        evidencias = await self.repository.find_evidencias_by_incidente(incidente_id)
        
        # Obtener imágenes y audios de todas las evidencias
        imagenes = []
        audios = []
        
        for evidencia in evidencias:
            if evidencia.tipo == "IMAGE":
                imgs = await self.repository.find_imagenes_by_evidencia(evidencia.id)
                imagenes.extend(imgs)
            elif evidencia.tipo == "AUDIO":
                auds = await self.repository.find_audios_by_evidencia(evidencia.id)
                audios.extend(auds)
        
        return incidente, evidencias, imagenes, audios
