"""
State Machine for Incident State Transitions.

This module provides a robust state machine for managing incident state transitions
with role-based validation and custom validators.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional, Tuple

from .logging import get_logger

logger = get_logger(__name__)


class IncidentState(str, Enum):
    """Valid incident states."""
    
    PENDIENTE = "pendiente"
    ASIGNADO = "asignado"
    RECHAZADO = "rechazado"
    ACEPTADO = "aceptado"
    EN_CAMINO = "en_camino"
    EN_PROCESO = "en_proceso"
    COMPLETADO = "completado"
    RESUELTO = "resuelto"
    CANCELADO = "cancelado"
    SIN_TALLER_DISPONIBLE = "sin_taller_disponible"


class UserRole(str, Enum):
    """User roles for permission checking."""
    
    CLIENTE = "client"
    TALLER = "workshop"
    TECNICO = "technician"
    ADMIN = "admin"


@dataclass
class Transition:
    """
    Represents a valid state transition.
    
    Attributes:
        from_state: Source state
        to_state: Target state
        allowed_roles: List of roles that can perform this transition
        validation_fn: Optional validation function that takes (incident, user) and returns (is_valid, error_message)
    """
    
    from_state: IncidentState
    to_state: IncidentState
    allowed_roles: List[UserRole]
    validation_fn: Optional[Callable] = None
    description: str = ""


class IncidentStateMachine:
    """
    State machine for managing incident state transitions.
    
    This class provides:
    - Role-based access control for state transitions
    - Custom validation functions for complex business rules
    - Clear error messages for invalid transitions
    - Audit trail support
    """
    
    # Define all valid transitions
    TRANSITIONS: List[Transition] = [
        # From PENDIENTE
        Transition(
            from_state=IncidentState.PENDIENTE,
            to_state=IncidentState.ACEPTADO,
            allowed_roles=[UserRole.TALLER, UserRole.ADMIN],
            description="Taller acepta solicitud con técnico asignado (opción 1: con técnico sugerido)"
        ),
        Transition(
            from_state=IncidentState.PENDIENTE,
            to_state=IncidentState.ASIGNADO,
            allowed_roles=[UserRole.TALLER, UserRole.ADMIN],
            description="Taller acepta solicitud sin técnico asignado aún (opción 2: asignar manualmente)"
        ),
        Transition(
            from_state=IncidentState.PENDIENTE,
            to_state=IncidentState.RECHAZADO,
            allowed_roles=[UserRole.TALLER, UserRole.ADMIN],
            description="Taller rechaza la solicitud"
        ),
        Transition(
            from_state=IncidentState.PENDIENTE,
            to_state=IncidentState.SIN_TALLER_DISPONIBLE,
            allowed_roles=[UserRole.ADMIN],
            description="No hay talleres disponibles"
        ),
        Transition(
            from_state=IncidentState.PENDIENTE,
            to_state=IncidentState.CANCELADO,
            allowed_roles=[UserRole.CLIENTE, UserRole.ADMIN],
            description="Cliente cancela el incidente"
        ),
        
        # From SIN_TALLER_DISPONIBLE
        Transition(
            from_state=IncidentState.SIN_TALLER_DISPONIBLE,
            to_state=IncidentState.PENDIENTE,
            allowed_roles=[UserRole.ADMIN],
            description="Reintentar asignación después de no encontrar taller"
        ),
        Transition(
            from_state=IncidentState.SIN_TALLER_DISPONIBLE,
            to_state=IncidentState.ASIGNADO,
            allowed_roles=[UserRole.ADMIN],
            description="Asignación manual después de no encontrar taller"
        ),
        Transition(
            from_state=IncidentState.SIN_TALLER_DISPONIBLE,
            to_state=IncidentState.CANCELADO,
            allowed_roles=[UserRole.CLIENTE, UserRole.ADMIN],
            description="Cliente cancela después de no encontrar taller"
        ),
        
        # From ASIGNADO
        Transition(
            from_state=IncidentState.ASIGNADO,
            to_state=IncidentState.ACEPTADO,
            allowed_roles=[UserRole.TALLER, UserRole.ADMIN],
            description="Taller acepta el incidente"
        ),
        Transition(
            from_state=IncidentState.ASIGNADO,
            to_state=IncidentState.RECHAZADO,
            allowed_roles=[UserRole.TALLER, UserRole.ADMIN],
            description="Taller rechaza el incidente"
        ),
        Transition(
            from_state=IncidentState.ASIGNADO,
            to_state=IncidentState.CANCELADO,
            allowed_roles=[UserRole.CLIENTE, UserRole.ADMIN],
            description="Cliente cancela después de asignación"
        ),
        
        # From RECHAZADO
        Transition(
            from_state=IncidentState.RECHAZADO,
            to_state=IncidentState.ASIGNADO,
            allowed_roles=[UserRole.ADMIN],
            description="Sistema reasigna a otro taller"
        ),
        Transition(
            from_state=IncidentState.RECHAZADO,
            to_state=IncidentState.SIN_TALLER_DISPONIBLE,
            allowed_roles=[UserRole.ADMIN],
            description="No hay más talleres disponibles"
        ),
        Transition(
            from_state=IncidentState.RECHAZADO,
            to_state=IncidentState.CANCELADO,
            allowed_roles=[UserRole.CLIENTE, UserRole.ADMIN],
            description="Cliente cancela después de rechazo"
        ),
        
        # From ACEPTADO
        Transition(
            from_state=IncidentState.ACEPTADO,
            to_state=IncidentState.EN_CAMINO,
            allowed_roles=[UserRole.TECNICO, UserRole.ADMIN],
            description="Técnico inicia viaje al lugar"
        ),
        Transition(
            from_state=IncidentState.ACEPTADO,
            to_state=IncidentState.EN_PROCESO,
            allowed_roles=[UserRole.TECNICO, UserRole.ADMIN],
            description="Técnico comienza trabajo directamente"
        ),
        Transition(
            from_state=IncidentState.ACEPTADO,
            to_state=IncidentState.CANCELADO,
            allowed_roles=[UserRole.CLIENTE, UserRole.TALLER, UserRole.ADMIN],
            description="Cancelación después de aceptación"
        ),
        
        # From EN_CAMINO
        Transition(
            from_state=IncidentState.EN_CAMINO,
            to_state=IncidentState.EN_PROCESO,
            allowed_roles=[UserRole.TECNICO, UserRole.ADMIN],
            description="Técnico llega y comienza trabajo"
        ),
        Transition(
            from_state=IncidentState.EN_CAMINO,
            to_state=IncidentState.CANCELADO,
            allowed_roles=[UserRole.CLIENTE, UserRole.TALLER, UserRole.ADMIN],
            description="Cancelación mientras técnico está en camino"
        ),
        
        # From EN_PROCESO
        Transition(
            from_state=IncidentState.EN_PROCESO,
            to_state=IncidentState.COMPLETADO,
            allowed_roles=[UserRole.TECNICO, UserRole.ADMIN],
            description="Técnico completa el trabajo"
        ),
        Transition(
            from_state=IncidentState.EN_PROCESO,
            to_state=IncidentState.RESUELTO,
            allowed_roles=[UserRole.TECNICO, UserRole.ADMIN],
            description="Técnico marca como resuelto directamente"
        ),
        Transition(
            from_state=IncidentState.EN_PROCESO,
            to_state=IncidentState.CANCELADO,
            allowed_roles=[UserRole.TALLER, UserRole.ADMIN],
            description="Cancelación durante el trabajo (requiere aprobación)"
        ),
        
        # From COMPLETADO
        Transition(
            from_state=IncidentState.COMPLETADO,
            to_state=IncidentState.RESUELTO,
            allowed_roles=[UserRole.CLIENTE, UserRole.ADMIN],
            description="Cliente confirma resolución"
        ),
        
        # Terminal states (no transitions out)
        # RESUELTO - no transitions
        # CANCELADO - no transitions
        # SIN_TALLER_DISPONIBLE - could be reopened by admin
        Transition(
            from_state=IncidentState.SIN_TALLER_DISPONIBLE,
            to_state=IncidentState.PENDIENTE,
            allowed_roles=[UserRole.ADMIN],
            description="Admin reabre incidente sin taller"
        ),
    ]
    
    @classmethod
    def can_transition(
        cls,
        from_state: str,
        to_state: str,
        user_role: str,
        incident: Optional[any] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a state transition is valid.
        
        Args:
            from_state: Current state (string)
            to_state: Target state (string)
            user_role: Role of the user attempting the transition (string)
            incident: Optional incident object for custom validation
            
        Returns:
            Tuple of (is_valid, error_message)
            - is_valid: True if transition is allowed
            - error_message: None if valid, error description if invalid
        """
        try:
            # Convert strings to enums
            from_state_enum = IncidentState(from_state)
            to_state_enum = IncidentState(to_state)
            user_role_enum = UserRole(user_role)
        except ValueError as e:
            return False, f"Invalid state or role: {str(e)}"
        
        # Find matching transition
        transition = None
        for t in cls.TRANSITIONS:
            if t.from_state == from_state_enum and t.to_state == to_state_enum:
                transition = t
                break
        
        if not transition:
            return False, (
                f"Transition from '{from_state}' to '{to_state}' is not allowed. "
                f"Valid transitions from '{from_state}': {cls._get_valid_transitions_str(from_state_enum)}"
            )
        
        # Check role permission
        if user_role_enum not in transition.allowed_roles:
            return False, (
                f"Role '{user_role}' is not authorized to transition from '{from_state}' to '{to_state}'. "
                f"Allowed roles: {', '.join([r.value for r in transition.allowed_roles])}"
            )
        
        # Run custom validation if provided
        if transition.validation_fn and incident:
            try:
                is_valid, error_msg = transition.validation_fn(incident, user_role_enum)
                if not is_valid:
                    return False, error_msg
            except Exception as e:
                logger.error(f"Validation function error: {str(e)}", exc_info=True)
                return False, f"Validation error: {str(e)}"
        
        return True, None
    
    @classmethod
    def get_allowed_transitions(
        cls,
        from_state: str,
        user_role: str
    ) -> List[str]:
        """
        Get list of allowed target states for a given state and role.
        
        Args:
            from_state: Current state (string)
            user_role: Role of the user (string)
            
        Returns:
            List of allowed target states (strings)
        """
        try:
            from_state_enum = IncidentState(from_state)
            user_role_enum = UserRole(user_role)
        except ValueError:
            return []
        
        allowed = []
        for t in cls.TRANSITIONS:
            if t.from_state == from_state_enum and user_role_enum in t.allowed_roles:
                allowed.append(t.to_state.value)
        
        return allowed
    
    @classmethod
    def _get_valid_transitions_str(cls, from_state: IncidentState) -> str:
        """Get comma-separated string of valid transitions from a state."""
        transitions = [
            t.to_state.value
            for t in cls.TRANSITIONS
            if t.from_state == from_state
        ]
        return ", ".join(transitions) if transitions else "none (terminal state)"
    
    @classmethod
    def get_transition_info(
        cls,
        from_state: str,
        to_state: str
    ) -> Optional[dict]:
        """
        Get information about a specific transition.
        
        Args:
            from_state: Source state
            to_state: Target state
            
        Returns:
            Dictionary with transition info or None if not found
        """
        try:
            from_state_enum = IncidentState(from_state)
            to_state_enum = IncidentState(to_state)
        except ValueError:
            return None
        
        for t in cls.TRANSITIONS:
            if t.from_state == from_state_enum and t.to_state == to_state_enum:
                return {
                    "from_state": t.from_state.value,
                    "to_state": t.to_state.value,
                    "allowed_roles": [r.value for r in t.allowed_roles],
                    "description": t.description,
                    "has_validation": t.validation_fn is not None
                }
        
        return None
    
    @classmethod
    def get_all_states(cls) -> List[str]:
        """Get list of all valid states."""
        return [state.value for state in IncidentState]
    
    @classmethod
    def is_terminal_state(cls, state: str) -> bool:
        """Check if a state is terminal (no transitions out)."""
        try:
            state_enum = IncidentState(state)
        except ValueError:
            return False
        
        for t in cls.TRANSITIONS:
            if t.from_state == state_enum:
                return False
        
        return True
