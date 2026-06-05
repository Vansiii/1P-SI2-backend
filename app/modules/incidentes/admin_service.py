"""
Service para funcionalidades administrativas de incidentes.
"""
import json
from datetime import datetime, timezone

from sqlalchemy import select, or_
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
from ...models.outbox_event import OutboxEvent
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


def _sortable_datetime(value: datetime | None) -> datetime:
    """Normaliza datetimes aware/naive para ordenarlos sin errores."""
    if value is None:
        return datetime.min
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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
            IncidentDetailAdminResponse con toda la informaciÃƒÂ³n
            
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
        
        # Obtener intentos de asignaciÃƒÂ³n
        assignment_attempts = await self._get_assignment_attempts(incident_id)
        
        # Obtener rechazos
        rejections = await self._get_rejections(incident_id)
        
        # Obtener historial de estados
        state_history = await self._get_state_history(incident_id)
        
        # Obtener informaciÃƒÂ³n del taller actual
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
        
        # Preparar informaciÃƒÂ³n del cliente
        # Client hereda de User, por lo que tiene directamente los campos first_name, last_name, etc.
        client_info = ClientInfo(
            id=incident.client.id,
            first_name=incident.client.first_name,
            last_name=incident.client.last_name,
            email=incident.client.email,
            phone=incident.client.phone
        )
        
        # Preparar informaciÃƒÂ³n del vehÃƒÂ­culo
        vehicle_info = VehicleInfo(
            id=incident.vehiculo.id,
            marca=incident.vehiculo.marca,
            modelo=incident.vehiculo.modelo,
            anio=incident.vehiculo.anio,
            matricula=incident.vehiculo.matricula,
            color=incident.vehiculo.color
        )
        
        # Calcular estadÃƒÂ­sticas
        total_attempts = len(assignment_attempts)
        total_rejections = len(rejections)
        total_no_responses = len([
            a for a in assignment_attempts if a.response_status in {'no_response', 'timeout'}
        ])
        
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
        """Obtener timeline de intentos y respuestas de asignación del incidente."""
        attempts_result = await self.session.scalars(
            select(AssignmentAttempt)
            .where(AssignmentAttempt.incident_id == incident_id)
            .order_by(AssignmentAttempt.created_at.asc())
        )
        attempts = attempts_result.all()
        attempt_by_workshop = {attempt.workshop_id: attempt for attempt in attempts}

        event_result = await self.session.scalars(
            select(OutboxEvent)
            .where(
                OutboxEvent.event_type.in_(
                    [
                        "incident.assigned",
                        "incident.assignment_timeout",
                        "incident.assignment_accepted",
                        "incident.assignment_rejected",
                        "incident.status_changed",
                    ]
                ),
                or_(
                    OutboxEvent.payload.contains(f'"incident_id": {incident_id}'),
                    OutboxEvent.payload.contains(f'"incident_id":{incident_id}'),
                ),
            )
            .order_by(OutboxEvent.created_at.asc())
        )
        events = event_result.all()

        timeline: list[AssignmentAttemptInfo] = []
        synthetic_id = 2_000_000

        for event in events:
            try:
                payload = json.loads(event.payload)
            except json.JSONDecodeError:
                continue

            if payload.get("incident_id") != incident_id:
                continue

            workshop_id = payload.get("workshop_id")
            if not workshop_id:
                continue

            workshop = await self.session.get(Workshop, workshop_id)
            workshop_name = workshop.workshop_name if workshop else payload.get("workshop_name", "Desconocido")
            attempt = attempt_by_workshop.get(workshop_id)

            if event.event_type == "incident.assigned":
                timeline.append(AssignmentAttemptInfo(
                    id=synthetic_id,
                    workshop_id=workshop_id,
                    workshop_name=workshop_name,
                    attempted_at=event.created_at,
                    response_status="pending",
                    rejection_reason=None,
                    responded_at=None,
                ))
                synthetic_id += 1
            elif event.event_type == "incident.assignment_timeout":
                timeline.append(AssignmentAttemptInfo(
                    id=synthetic_id,
                    workshop_id=workshop_id,
                    workshop_name=workshop_name,
                    attempted_at=attempt.attempted_at if attempt else event.created_at,
                    response_status="timeout",
                    rejection_reason=None,
                    responded_at=payload.get("timed_out_at") or event.created_at,
                ))
                synthetic_id += 1
            elif event.event_type == "incident.assignment_accepted":
                timeline.append(AssignmentAttemptInfo(
                    id=synthetic_id,
                    workshop_id=workshop_id,
                    workshop_name=workshop_name,
                    attempted_at=attempt.attempted_at if attempt else event.created_at,
                    response_status="accepted",
                    rejection_reason=None,
                    responded_at=payload.get("accepted_at") or event.created_at,
                ))
                synthetic_id += 1
            elif event.event_type == "incident.assignment_rejected":
                timeline.append(AssignmentAttemptInfo(
                    id=synthetic_id,
                    workshop_id=workshop_id,
                    workshop_name=workshop_name,
                    attempted_at=attempt.attempted_at if attempt else event.created_at,
                    response_status="rejected",
                    rejection_reason=payload.get("reason"),
                    responded_at=payload.get("rejected_at") or event.created_at,
                ))
                synthetic_id += 1
            elif event.event_type == "incident.status_changed":
                reason = (payload.get("reason") or "").lower()
                if reason in {
                    "mutual_cancellation",
                    "ambiguous_case_cancelled",
                    "ambiguous_case_cancelled_manual",
                }:
                    timeline.append(AssignmentAttemptInfo(
                        id=synthetic_id,
                        workshop_id=workshop_id,
                        workshop_name=workshop_name,
                        attempted_at=attempt.attempted_at if attempt else event.created_at,
                        response_status="cancelled",
                        rejection_reason=(
                            "Cancelación mutua"
                            if reason == "mutual_cancellation"
                            else "Caso ambiguo anulado"
                        ),
                        responded_at=event.created_at,
                    ))
                    synthetic_id += 1

        if timeline:
            timeline.sort(
                key=lambda item: _sortable_datetime(item.responded_at or item.attempted_at),
                reverse=True,
            )
            return timeline

        fallback: list[AssignmentAttemptInfo] = []
        for attempt in attempts:
            workshop = await self.session.get(Workshop, attempt.workshop_id)
            workshop_name = workshop.workshop_name if workshop else "Desconocido"
            rejection_reason = None
            if attempt.status == "rejected":
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

            fallback.append(AssignmentAttemptInfo(
                id=attempt.id,
                workshop_id=attempt.workshop_id,
                workshop_name=workshop_name,
                attempted_at=attempt.attempted_at,
                response_status=attempt.status,
                rejection_reason=rejection_reason,
                responded_at=attempt.responded_at
            ))

        fallback.sort(
            key=lambda item: _sortable_datetime(item.responded_at or item.attempted_at),
            reverse=True,
        )
        return fallback
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

        history: list[StateHistoryInfo] = []
        seen_keys: set[tuple[str, str]] = set()
        for historial, estado, user in result.all():
            user_name = None
            if user:
                user_name = f"{user.first_name} {user.last_name}"

            item = StateHistoryInfo(
                id=historial.id,
                estado_nombre=estado.nombre,
                estado_descripcion=estado.descripcion,
                changed_by_user_name=user_name,
                comentario=historial.comentario,
                fecha=historial.fecha
            )
            history.append(item)
            seen_keys.add((estado.nombre, historial.fecha.isoformat()))

        event_result = await self.session.scalars(
            select(OutboxEvent)
            .where(
                OutboxEvent.event_type.in_(
                    [
                        "incident.created",
                        "incident.assigned",
                        "incident.assignment_timeout",
                        "incident.assignment_accepted",
                        "incident.assignment_rejected",
                        "incident.reassigned",
                        "incident.no_workshop_available",
                        "incident.status_changed",
                        "incident.work_started",
                        "incident.work_completed",
                    ]
                ),
                or_(
                    OutboxEvent.payload.contains(f'"incident_id": {incident_id}'),
                    OutboxEvent.payload.contains(f'"incident_id":{incident_id}'),
                ),
            )
            .order_by(OutboxEvent.created_at.desc())
        )

        synthetic_id = 3_000_000
        for event in event_result.all():
            try:
                payload = json.loads(event.payload)
            except json.JSONDecodeError:
                continue

            if payload.get("incident_id") != incident_id:
                continue

            state_name = None
            comment = None

            if event.event_type == "incident.created":
                state_name = "pendiente"
                comment = "Incidente creado"
            elif event.event_type == "incident.assigned":
                state_name = "pendiente"
                comment = f"Solicitud enviada al taller {payload.get('workshop_name', 'desconocido')}"
            elif event.event_type == "incident.assignment_timeout":
                state_name = "pendiente"
                comment = f"El taller {payload.get('workshop_name', 'desconocido')} no respondiÃ³ a tiempo"
            elif event.event_type == "incident.assignment_rejected":
                state_name = "pendiente"
                rejection_reason = payload.get("reason")
                comment = (
                    f"El taller {payload.get('workshop_name', 'desconocido')} rechazÃ³ la solicitud"
                    if not rejection_reason
                    else f"El taller {payload.get('workshop_name', 'desconocido')} rechazÃ³ la solicitud: {rejection_reason}"
                )
            elif event.event_type == "incident.reassigned":
                state_name = payload.get("new_status") or "pendiente"
                comment = f"Incidente reasignado al taller {payload.get('new_workshop_name', 'desconocido')}"
            elif event.event_type == "incident.no_workshop_available":
                state_name = "sin_taller_disponible"
                comment = payload.get("reason") or payload.get("message")
            elif event.event_type == "incident.status_changed":
                state_name = payload.get("new_status")
                comment = payload.get("reason") or f"Cambio de estado desde {payload.get('old_status')}"
            elif event.event_type == "incident.assignment_accepted":
                state_name = payload.get("new_status") or "asignado"
                comment = f"Solicitud aceptada por {payload.get('workshop_name', 'taller')}"
            elif event.event_type == "incident.work_started":
                state_name = "en_proceso"
                comment = f"Trabajo iniciado por {payload.get('technician_name', 'técnico')}"
            elif event.event_type == "incident.work_completed":
                state_name = "resuelto"
                comment = f"Trabajo completado por {payload.get('technician_name', 'técnico')}"

            if not state_name:
                continue

            key = (state_name, event.created_at.isoformat())
            if key in seen_keys:
                continue

            history.append(StateHistoryInfo(
                id=synthetic_id,
                estado_nombre=state_name,
                estado_descripcion=None,
                changed_by_user_name=None,
                comentario=comment,
                fecha=event.created_at,
            ))
            seen_keys.add(key)
            synthetic_id += 1

        history.sort(key=lambda item: _sortable_datetime(item.fecha), reverse=True)
        return history
