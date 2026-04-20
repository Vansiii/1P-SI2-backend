"""
Service for managing incident state transitions and workflows.
"""
from datetime import datetime
from typing import Optional, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from ...core.logging import get_logger
from ...core.exceptions import NotFoundError, ValidationError
from ...models.incidente import Incidente
from ...models.historial_servicio import HistorialServicio
from ...models.estados_servicio import EstadosServicio
from ...core.websocket import manager
from ..push_notifications.services import PushNotificationService

logger = get_logger(__name__)


class IncidentStateService:
    """
    Service for managing incident state transitions with validation.
    """

    # Valid state transitions
    STATE_TRANSITIONS = {
        "pendiente": ["asignado", "cancelado"],
        "asignado": ["en_proceso", "en_camino", "cancelado"],
        "en_proceso": ["resuelto", "cancelado"],
        "en_camino": ["en_sitio", "cancelado"],
        "en_sitio": ["resuelto", "cancelado"],
        "resuelto": [],  # Terminal state
        "cancelado": []  # Terminal state
    }

    # State descriptions in Spanish
    STATE_DESCRIPTIONS = {
        "pendiente": "Incidente reportado, esperando asignación",
        "asignado": "Taller/técnico asignado al incidente",
        "en_proceso": "Técnico trabajando en el incidente",
        "en_camino": "Técnico en camino al lugar del incidente",
        "en_sitio": "Técnico ha llegado y está atendiendo el incidente",
        "resuelto": "Incidente resuelto exitosamente",
        "cancelado": "Incidente cancelado"
    }

    def __init__(self, session: AsyncSession):
        self.session = session
        self.push_service = PushNotificationService(session)

    async def transition_state(
        self,
        incident_id: int,
        new_state: str,
        changed_by: int,
        notes: Optional[str] = None,
        force: bool = False
    ) -> Incidente:
        """
        Transition incident to a new state with validation.
        
        Args:
            incident_id: ID of the incident
            new_state: Target state
            changed_by: ID of user making the change
            notes: Optional notes about the transition
            force: Skip validation (admin only)
            
        Returns:
            Updated incident
            
        Raises:
            NotFoundError: If incident not found
            ValidationError: If transition is invalid
        """
        # Get incident
        incident = await self.session.scalar(
            select(Incidente).where(Incidente.id == incident_id)
        )

        if not incident:
            raise NotFoundError(f"Incident {incident_id} not found")

        current_state = incident.estado_actual

        # Validate transition
        if not force:
            self._validate_transition(current_state, new_state)

        # Perform state-specific actions
        await self._perform_state_actions(incident, new_state)

        # Update incident state
        incident.estado_actual = new_state
        incident.updated_at = datetime.utcnow()

        # Get estado_id from estados_servicio
        estado = await self.session.scalar(
            select(EstadosServicio).where(EstadosServicio.nombre == new_state)
        )
        
        if not estado:
            logger.error(f"Estado '{new_state}' no encontrado en estados_servicio")
            raise ValidationError(f"Estado '{new_state}' no es válido")

        # Create history record
        history = HistorialServicio(
            incidente_id=incident_id,
            estado_id=estado.id,
            changed_by_user_id=changed_by,
            comentario=f"Cambio de estado: {current_state} → {new_state}. {notes or self.STATE_DESCRIPTIONS.get(new_state, '')}"
        )
        self.session.add(history)

        await self.session.commit()
        await self.session.refresh(incident)

        # Broadcast state change
        await manager.send_incident_status_change(
            incident_id=incident_id,
            new_status=new_state,
            changed_by=changed_by
        )

        # Emit standardized service status WebSocket events (Task 16)
        from ...core.websocket_events import emit_to_incident_room, EventTypes
        
        service_event_map = {
            "en_proceso": EventTypes.SERVICE_STARTED,
            "resuelto": EventTypes.SERVICE_COMPLETED,
            "cancelado": EventTypes.SERVICE_PAUSED,
        }
        
        service_event_type = service_event_map.get(new_state)
        
        if service_event_type:
            service_payload = {
                "service_id": incident_id,  # Use incident_id as service_id
                "incident_id": incident_id,
                "status": new_state,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await emit_to_incident_room(
                incident_id=incident_id,
                event_type=service_event_type,
                data=service_payload
            )
            
            logger.info(
                f"WebSocket event '{service_event_type}' emitted for incident {incident_id} "
                f"(state: {new_state})"
            )

        # Send push notification
        if self.push_service.is_enabled():
            await self._send_state_notification(incident, new_state)

        logger.info(
            f"Incident {incident_id} transitioned from {current_state} to {new_state} "
            f"by user {changed_by}"
        )

        return incident

    def _validate_transition(self, current_state: str, new_state: str) -> None:
        """
        Validate if state transition is allowed.
        
        Args:
            current_state: Current state
            new_state: Target state
            
        Raises:
            ValidationError: If transition is invalid
        """
        if current_state not in self.STATE_TRANSITIONS:
            raise ValidationError(f"Invalid current state: {current_state}")

        if new_state not in self.STATE_TRANSITIONS:
            raise ValidationError(f"Invalid target state: {new_state}")

        allowed_transitions = self.STATE_TRANSITIONS[current_state]

        if new_state not in allowed_transitions:
            raise ValidationError(
                f"Cannot transition from '{current_state}' to '{new_state}'. "
                f"Allowed transitions: {', '.join(allowed_transitions) if allowed_transitions else 'none (terminal state)'}"
            )

    async def _perform_state_actions(
        self,
        incident: Incidente,
        new_state: str
    ) -> None:
        """
        Perform state-specific actions when transitioning.
        
        Args:
            incident: Incident being transitioned
            new_state: Target state
        """
        if new_state == "asignado":
            # Set assigned timestamp
            incident.assigned_at = datetime.utcnow()

        elif new_state == "en_camino":
            # Ensure tracking session is started
            # This is handled by tracking service
            pass

        elif new_state == "en_sitio":
            # Mark arrival time
            # This is handled by tracking service
            pass

        elif new_state == "resuelto":
            # Set resolution timestamp
            incident.resolved_at = datetime.utcnow()

        elif new_state == "cancelado":
            # Set cancellation timestamp
            incident.cancelled_at = datetime.utcnow()

    async def _send_state_notification(
        self,
        incident: Incidente,
        new_state: str
    ) -> None:
        """
        Send push notification about state change.
        
        Args:
            incident: Incident that changed state
            new_state: New state
        """
        notification_messages = {
            "asignado": "Tu incidente ha sido asignado a un taller",
            "en_camino": "El técnico está en camino",
            "en_sitio": "El técnico ha llegado al lugar",
            "resuelto": "Tu incidente ha sido resuelto",
            "cancelado": "Tu incidente ha sido cancelado"
        }

        message = notification_messages.get(
            new_state,
            f"Estado del incidente actualizado a: {new_state}"
        )

        await self.push_service.send_incident_notification(
            user_id=incident.client_id,
            incident_id=incident.id,
            notification_type="incident_status_change",
            title="Estado del incidente actualizado",
            body=message,
            additional_data={"new_state": new_state}
        )

    async def get_state_history(
        self,
        incident_id: int
    ) -> List[HistorialServicio]:
        """
        Get state transition history for an incident.
        
        Args:
            incident_id: ID of the incident
            
        Returns:
            List of history records ordered by date
        """
        result = await self.session.scalars(
            select(HistorialServicio)
            .where(HistorialServicio.incidente_id == incident_id)
            .order_by(HistorialServicio.fecha.desc())
        )

        return list(result.all())

    async def get_allowed_transitions(
        self,
        incident_id: int
    ) -> List[str]:
        """
        Get allowed state transitions for an incident.
        
        Args:
            incident_id: ID of the incident
            
        Returns:
            List of allowed target states
            
        Raises:
            NotFoundError: If incident not found
        """
        incident = await self.session.scalar(
            select(Incidente).where(Incidente.id == incident_id)
        )

        if not incident:
            raise NotFoundError(f"Incident {incident_id} not found")

        current_state = incident.estado_actual
        return self.STATE_TRANSITIONS.get(current_state, [])

    async def can_transition(
        self,
        incident_id: int,
        new_state: str
    ) -> bool:
        """
        Check if incident can transition to a new state.
        
        Args:
            incident_id: ID of the incident
            new_state: Target state
            
        Returns:
            True if transition is allowed
        """
        try:
            allowed = await self.get_allowed_transitions(incident_id)
            return new_state in allowed
        except NotFoundError:
            return False

    async def cancel_incident(
        self,
        incident_id: int,
        cancelled_by: int,
        reason: str
    ) -> Incidente:
        """
        Cancel an incident with reason.
        
        Args:
            incident_id: ID of the incident
            cancelled_by: ID of user cancelling
            reason: Reason for cancellation
            
        Returns:
            Updated incident
        """
        return await self.transition_state(
            incident_id=incident_id,
            new_state="cancelado",
            changed_by=cancelled_by,
            notes=f"Cancelado: {reason}"
        )

    async def resolve_incident(
        self,
        incident_id: int,
        resolved_by: int,
        resolution_notes: Optional[str] = None
    ) -> Incidente:
        """
        Mark incident as resolved.
        
        Args:
            incident_id: ID of the incident
            resolved_by: ID of user resolving
            resolution_notes: Optional resolution notes
            
        Returns:
            Updated incident
        """
        return await self.transition_state(
            incident_id=incident_id,
            new_state="resuelto",
            changed_by=resolved_by,
            notes=resolution_notes or "Incidente resuelto exitosamente"
        )

    def get_state_info(self, state: str) -> Dict[str, any]:
        """
        Get information about a state.
        
        Args:
            state: State name
            
        Returns:
            Dictionary with state information
        """
        return {
            "state": state,
            "description": self.STATE_DESCRIPTIONS.get(state, "Unknown state"),
            "allowed_transitions": self.STATE_TRANSITIONS.get(state, []),
            "is_terminal": len(self.STATE_TRANSITIONS.get(state, [])) == 0
        }

    def get_all_states(self) -> List[Dict[str, any]]:
        """
        Get information about all states.
        
        Returns:
            List of state information dictionaries
        """
        return [
            self.get_state_info(state)
            for state in self.STATE_TRANSITIONS.keys()
        ]
