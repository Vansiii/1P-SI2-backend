"""
Service para funcionalidades administrativas de incidentes.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...core import get_logger, NotFoundException
from ...models.incidente import Incidente
from ...models.assignment_attempt import AssignmentAttempt
from ...models.rechazo_taller import RechazoTaller
from ...models.historial_servicio import HistorialServicio
from ...models.estados_servicio import EstadosServicio
from ...models.workshop import Workshop
from ...models.client import Client
from ...models.vehiculo import Vehiculo
from ...models.user import User
from .admin_schemas import (
    IncidentDetailAdminResponse,
    AssignmentAttemptInfo,
    RejectionInfo,
    StateHistoryInfo,
    WorkshopInfo,
    ClientInfo,
    VehicleInfo
)

logger = get_logger(__name__)


class IncidentAdminService:
    """Service para operaciones administrativas de incidentes."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_incident_admin_detail(self, incident_id: int) -> IncidentDetailAdminResponse:
        """
        Obtener detalles completos de un incidente para administradores.
        
        Args:
            incident_id: ID del incidente
            
        Returns:
            IncidentDetailAdminResponse con toda la información
            
        Raises:
            NotFoundException: Si el incidente no existe
        """
        # Obtener incidente con relaciones
        incident = await self.session.scalar(
            select(Incidente)
            .where(Incidente.id == incident_id)
            .options(
                selectinload(Incidente.client),
                selectinload(Incidente.vehiculo),
                selectinload(Incidente.workshop)
            )
        )
        
        if not incident:
            raise NotFoundException(resource_type="Incidente", resource_id=incident_id)
        
        # Obtener intentos de asignación
        assignment_attempts = await self._get_assignment_attempts(incident_id)
        
        # Obtener rechazos
        rejections = await self._get_rejections(incident_id)
        
        # Obtener historial de estados
        state_history = await self._get_state_history(incident_id)
        
        # Obtener información del taller actual
        current_workshop = None
        if incident.taller_id:
            workshop = await self.session.get(Workshop, incident.taller_id)
            if workshop:
                current_workshop = WorkshopInfo(
                    id=workshop.id,
                    workshop_name=workshop.workshop_name,
                    workshop_phone=workshop.workshop_phone,
                    address=workshop.address
                )
        
        # Preparar información del cliente
        # Client hereda de User, por lo que tiene directamente los campos first_name, last_name, etc.
        client_info = ClientInfo(
            id=incident.client.id,
            first_name=incident.client.first_name,
            last_name=incident.client.last_name,
            email=incident.client.email,
            phone=incident.client.phone
        )
        
        # Preparar información del vehículo
        vehicle_info = VehicleInfo(
            id=incident.vehiculo.id,
            marca=incident.vehiculo.marca,
            modelo=incident.vehiculo.modelo,
            anio=incident.vehiculo.anio,
            matricula=incident.vehiculo.matricula,
            color=incident.vehiculo.color
        )
        
        # Calcular estadísticas
        total_attempts = len(assignment_attempts)
        total_rejections = len(rejections)
        total_no_responses = len([a for a in assignment_attempts if a.response_status == 'no_response'])
        
        return IncidentDetailAdminResponse(
            id=incident.id,
            estado_actual=incident.estado_actual,
            descripcion=incident.descripcion,
            latitude=float(incident.latitude),
            longitude=float(incident.longitude),
            direccion_referencia=incident.direccion_referencia,
            categoria_ia=incident.categoria_ia,
            prioridad_ia=incident.prioridad_ia,
            resumen_ia=incident.resumen_ia,
            es_ambiguo=incident.es_ambiguo,
            created_at=incident.created_at,
            updated_at=incident.updated_at,
            assigned_at=incident.assigned_at,
            resolved_at=incident.resolved_at,
            client=client_info,
            vehiculo=vehicle_info,
            current_workshop=current_workshop,
            assignment_attempts=assignment_attempts,
            rejections=rejections,
            state_history=state_history,
            total_attempts=total_attempts,
            total_rejections=total_rejections,
            total_no_responses=total_no_responses
        )
    
    async def _get_assignment_attempts(self, incident_id: int) -> list[AssignmentAttemptInfo]:
        """Obtener intentos de asignación del incidente."""
        result = await self.session.scalars(
            select(AssignmentAttempt)
            .where(AssignmentAttempt.incident_id == incident_id)
            .order_by(AssignmentAttempt.attempted_at.desc())
        )
        
        attempts = []
        for attempt in result.all():
            # Obtener nombre del taller
            workshop = await self.session.get(Workshop, attempt.workshop_id)
            workshop_name = workshop.workshop_name if workshop else "Desconocido"
            
            # El estado ya viene del campo status
            response_status = attempt.status
            
            # Obtener motivo de rechazo si existe
            rejection_reason = None
            if response_status == "rejected":
                rejection = await self.session.scalar(
                    select(RechazoTaller)
                    .where(
                        RechazoTaller.incidente_id == incident_id,
                        RechazoTaller.taller_id == attempt.workshop_id
                    )
                    .order_by(RechazoTaller.created_at.desc())
                )
                if rejection:
                    rejection_reason = rejection.motivo
            
            attempts.append(AssignmentAttemptInfo(
                id=attempt.id,
                workshop_id=attempt.workshop_id,
                workshop_name=workshop_name,
                attempted_at=attempt.attempted_at,
                response_status=response_status,
                rejection_reason=rejection_reason,
                responded_at=attempt.responded_at
            ))
        
        return attempts
    
    async def _get_rejections(self, incident_id: int) -> list[RejectionInfo]:
        """Obtener rechazos del incidente."""
        result = await self.session.scalars(
            select(RechazoTaller)
            .where(RechazoTaller.incidente_id == incident_id)
            .order_by(RechazoTaller.created_at.desc())
        )
        
        rejections = []
        for rejection in result.all():
            # Obtener nombre del taller
            workshop = await self.session.get(Workshop, rejection.taller_id)
            workshop_name = workshop.workshop_name if workshop else "Desconocido"
            
            rejections.append(RejectionInfo(
                id=rejection.id,
                taller_id=rejection.taller_id,
                workshop_name=workshop_name,
                motivo=rejection.motivo,
                created_at=rejection.created_at
            ))
        
        return rejections
    
    async def _get_state_history(self, incident_id: int) -> list[StateHistoryInfo]:
        """Obtener historial de estados del incidente."""
        result = await self.session.execute(
            select(HistorialServicio, EstadosServicio, User)
            .join(EstadosServicio, HistorialServicio.estado_id == EstadosServicio.id)
            .outerjoin(User, HistorialServicio.changed_by_user_id == User.id)
            .where(HistorialServicio.incidente_id == incident_id)
            .order_by(HistorialServicio.fecha.desc())
        )
        
        history = []
        for historial, estado, user in result.all():
            user_name = None
            if user:
                user_name = f"{user.first_name} {user.last_name}"
            
            history.append(StateHistoryInfo(
                id=historial.id,
                estado_nombre=estado.nombre,
                estado_descripcion=estado.descripcion,
                changed_by_user_name=user_name,
                comentario=historial.comentario,
                fecha=historial.fecha
            ))
        
        return history
