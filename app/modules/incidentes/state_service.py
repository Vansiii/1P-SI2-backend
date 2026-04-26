"""
Service for managing incident state transitions using the State Machine.

This service integrates the IncidentStateMachine with the incident business logic,
providing validated state transitions with role-based access control.
"""

from datetime import datetime, UTC
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...core import (
    get_logger,
    NotFoundException,
    ValidationException,
    IncidentStateMachine,
    UserRole
)
from ...core.event_publisher import EventPublisher
from ...shared.schemas.events.incident import IncidentStatusChangedEvent
from ...models.incidente import Incidente
from ...models.historial_servicio import HistorialServicio
from ...models.estados_servicio import EstadosServicio

logger = get_logger(__name__)


class IncidentStateTransitionService:
    """
    Service for managing incident state transitions with State Machine validation.
    
    This service provides:
    - Role-based access control for state transitions
    - Automatic validation using IncidentStateMachine
    - Event publishing for state changes
    - History tracking
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def transition_state(
        self,
        incident_id: int,
        new_state: str,
        user_id: int,
        user_role: str,
        reason: Optional[str] = None,
        force: bool = False
    ) -> Incidente:
        """
        Transition incident to a new state with validation.
        
        Args:
            incident_id: ID of the incident
            new_state: Target state
            user_id: ID of user making the change
            user_role: Role of the user (client, workshop, technician, admin)
            reason: Optional reason for the transition
            force: Skip validation (admin only)
            
        Returns:
            Updated incident
            
        Raises:
            NotFoundException: If incident not found
            ValidationException: If transition is invalid
        """
        # Get incident
        from sqlalchemy import select
        result = await self.session.execute(
            select(Incidente).where(Incidente.id == incident_id)
        )
        incident = result.scalar_one_or_none()
        
        if not incident:
            raise NotFoundException(f"Incident {incident_id} not found")
        
        current_state = incident.estado_actual
        
        # Validate transition using State Machine
        if not force:
            is_valid, error_message = IncidentStateMachine.can_transition(
                from_state=current_state,
                to_state=new_state,
                user_role=user_role,
                incident=incident
            )
            
            if not is_valid:
                logger.warning(
                    f"Invalid state transition attempt: {current_state} -> {new_state} "
                    f"by user {user_id} ({user_role}): {error_message}"
                )
                raise ValidationException(error_message)
        
        # Perform state-specific actions
        await self._perform_state_actions(incident, new_state)
        
        # Update incident state
        old_state = incident.estado_actual
        incident.estado_actual = new_state
        incident.updated_at = datetime.now(UTC)
        
        # Create history record
        await self._create_history_record(
            incident_id=incident_id,
            new_state=new_state,
            changed_by=user_id,
            reason=reason or f"Transition from {old_state} to {new_state}"
        )
        
        # Commit changes
        await self.session.commit()
        await self.session.refresh(incident)
        
        # Publish state change event
        try:
            event = IncidentStatusChangedEvent(
                incident_id=incident_id,
                old_status=old_state,
                new_status=new_state,
                changed_by=user_id,
                changed_by_role=user_role,
                reason=reason
            )
            await EventPublisher.publish(self.session, event)
            await self.session.commit()
            
            logger.info(
                f"✅ State transition event published: incident {incident_id} "
                f"({old_state} -> {new_state}) by user {user_id} ({user_role})"
            )
        except Exception as e:
            logger.error(
                f"❌ Error publishing state change event: {str(e)}",
                exc_info=True
            )
        
        logger.info(
            f"Incident {incident_id} transitioned from {old_state} to {new_state} "
            f"by user {user_id} ({user_role})"
        )
        
        return incident
    
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
            if not incident.assigned_at:
                incident.assigned_at = datetime.now(UTC)
        
        elif new_state == "aceptado":
            # Workshop accepted, ready for technician assignment
            pass
        
        elif new_state == "en_camino":
            # Technician is on the way
            # Tracking session should be started by tracking service
            pass
        
        elif new_state == "en_proceso":
            # Work has started
            pass
        
        elif new_state in ["completado", "resuelto"]:
            # Set resolution timestamp
            if not incident.resolved_at:
                incident.resolved_at = datetime.now(UTC)
        
        elif new_state == "cancelado":
            # Set cancellation timestamp
            if not hasattr(incident, 'cancelled_at'):
                # Add cancelled_at field if it doesn't exist
                pass
    
    async def _create_history_record(
        self,
        incident_id: int,
        new_state: str,
        changed_by: int,
        reason: str
    ) -> None:
        """
        Create history record for state transition.
        
        Args:
            incident_id: ID of the incident
            new_state: New state
            changed_by: User ID who made the change
            reason: Reason for the change
        """
        from sqlalchemy import select
        
        # Get estado_id from estados_servicio
        result = await self.session.execute(
            select(EstadosServicio).where(EstadosServicio.nombre == new_state)
        )
        estado = result.scalar_one_or_none()
        
        if not estado:
            logger.warning(f"Estado '{new_state}' not found in estados_servicio, skipping history")
            return
        
        # Create history record
        history = HistorialServicio(
            incidente_id=incident_id,
            estado_id=estado.id,
            changed_by_user_id=changed_by,
            comentario=reason
        )
        self.session.add(history)
    
    async def get_allowed_transitions(
        self,
        incident_id: int,
        user_role: str
    ) -> list[str]:
        """
        Get allowed state transitions for an incident and user role.
        
        Args:
            incident_id: ID of the incident
            user_role: Role of the user
            
        Returns:
            List of allowed target states
            
        Raises:
            NotFoundException: If incident not found
        """
        from sqlalchemy import select
        
        result = await self.session.execute(
            select(Incidente).where(Incidente.id == incident_id)
        )
        incident = result.scalar_one_or_none()
        
        if not incident:
            raise NotFoundException(f"Incident {incident_id} not found")
        
        return IncidentStateMachine.get_allowed_transitions(
            from_state=incident.estado_actual,
            user_role=user_role
        )
    
    async def can_transition(
        self,
        incident_id: int,
        new_state: str,
        user_role: str
    ) -> tuple[bool, Optional[str]]:
        """
        Check if a state transition is allowed.
        
        Args:
            incident_id: ID of the incident
            new_state: Target state
            user_role: Role of the user
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        from sqlalchemy import select
        
        result = await self.session.execute(
            select(Incidente).where(Incidente.id == incident_id)
        )
        incident = result.scalar_one_or_none()
        
        if not incident:
            return False, f"Incident {incident_id} not found"
        
        return IncidentStateMachine.can_transition(
            from_state=incident.estado_actual,
            to_state=new_state,
            user_role=user_role,
            incident=incident
        )
    
    def get_state_info(self, state: str) -> dict:
        """
        Get information about a state.
        
        Args:
            state: State name
            
        Returns:
            Dictionary with state information
        """
        is_terminal = IncidentStateMachine.is_terminal_state(state)
        
        return {
            "state": state,
            "is_terminal": is_terminal,
            "all_possible_transitions": [
                t.to_state.value
                for t in IncidentStateMachine.TRANSITIONS
                if t.from_state.value == state
            ]
        }
