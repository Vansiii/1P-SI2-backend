"""
Custom validators for state transitions.

These validators implement business rules that must be checked
before allowing certain state transitions.
"""

from typing import Tuple

from .logging import get_logger
from .state_machine import UserRole

logger = get_logger(__name__)


class StateValidators:
    """
    Collection of validation functions for state transitions.
    
    Each validator takes (incident, user_role) and returns (is_valid, error_message).
    """
    
    @staticmethod
    def validate_assignment(incident: any, user_role: UserRole) -> Tuple[bool, str]:
        """
        Validate that incident can be assigned.
        
        Requirements:
        - Incident must have location data
        - Incident must have description
        
        Args:
            incident: Incident object
            user_role: Role of user attempting transition
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not incident.latitude or not incident.longitude:
            return False, "Cannot assign incident without location data"
        
        if not incident.descripcion or len(incident.descripcion.strip()) < 10:
            return False, "Cannot assign incident without proper description (min 10 characters)"
        
        return True, ""
    
    @staticmethod
    def validate_acceptance(incident: any, user_role: UserRole) -> Tuple[bool, str]:
        """
        Validate that workshop can accept incident.
        
        Requirements:
        - Incident must be assigned to a workshop
        - Workshop must have available technicians (if checking)
        
        Args:
            incident: Incident object
            user_role: Role of user attempting transition
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not incident.taller_id:
            return False, "Cannot accept incident that is not assigned to a workshop"
        
        # Additional validation: check if workshop has capacity
        # This could query technician availability
        # For now, we allow acceptance if assigned
        
        return True, ""
    
    @staticmethod
    def validate_start_tracking(incident: any, user_role: UserRole) -> Tuple[bool, str]:
        """
        Validate that technician can start traveling (EN_CAMINO).
        
        Requirements:
        - Incident must have assigned technician
        - Technician must be available
        
        Args:
            incident: Incident object
            user_role: Role of user attempting transition
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not incident.tecnico_id:
            return False, "Cannot start tracking without assigned technician"
        
        # Check if technician is available
        if hasattr(incident, 'technician') and incident.technician:
            if not incident.technician.is_available:
                logger.warning(
                    f"Technician {incident.tecnico_id} is not available but starting tracking anyway"
                )
                # Allow but log warning - technician might have just been assigned
        
        return True, ""
    
    @staticmethod
    def validate_completion(incident: any, user_role: UserRole) -> Tuple[bool, str]:
        """
        Validate that incident can be marked as completed.
        
        Requirements:
        - Incident must have been in EN_PROCESO state
        - Technician must have spent minimum time on site (optional)
        
        Args:
            incident: Incident object
            user_role: Role of user attempting transition
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not incident.tecnico_id:
            return False, "Cannot complete incident without assigned technician"
        
        # Optional: Check minimum time on site
        # This would require tracking when EN_PROCESO started
        # For now, we allow completion if technician is assigned
        
        return True, ""
    
    @staticmethod
    async def validate_cancellation(
        session: any,
        incident: any,
        user: any
    ) -> Tuple[bool, str]:
        """
        Validate that incident can be cancelled.
        
        Requirements:
        - Client can cancel before EN_PROCESO
        - Workshop/Technician can cancel with reason
        - Admin can always cancel
        
        Args:
            session: Database session
            incident: Incident object
            user: User object attempting cancellation
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        user_role = user.user_type if hasattr(user, 'user_type') else None
        
        # Admin can always cancel
        if user_role == "admin":
            return True, ""
        
        # Client can cancel before work starts
        if user_role == "client":
            if incident.estado_actual in ["pendiente", "asignado", "aceptado"]:
                return True, ""
            else:
                return False, "Client cannot cancel incident after work has started"
        
        # Workshop/Technician can cancel with proper reason
        if user_role in ["workshop", "technician"]:
            # Would check if cancellation_reason is provided
            # This is typically handled at the service layer
            return True, ""
        
        return False, f"Role '{user_role}' is not authorized to cancel this incident"
    
    @staticmethod
    def validate_resolution(incident: any, user_role: UserRole) -> Tuple[bool, str]:
        """
        Validate that incident can be marked as resolved.
        
        Requirements:
        - Incident must have been completed by technician
        - Client must confirm resolution (for COMPLETADO -> RESUELTO)
        
        Args:
            incident: Incident object
            user_role: Role of user attempting transition
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # If technician is marking as resolved directly from EN_PROCESO
        if user_role == UserRole.TECNICO:
            if not incident.tecnico_id:
                return False, "Cannot resolve incident without assigned technician"
            return True, ""
        
        # If client is confirming resolution from COMPLETADO
        if user_role == UserRole.CLIENTE:
            if incident.estado_actual != "completado":
                return False, "Client can only confirm resolution after technician completes work"
            return True, ""
        
        # Admin can always resolve
        if user_role == UserRole.ADMIN:
            return True, ""
        
        return False, "Invalid role for resolution"
    
    @staticmethod
    def validate_rejection(incident: any, user_role: UserRole) -> Tuple[bool, str]:
        """
        Validate that workshop can reject incident.
        
        Requirements:
        - Workshop must provide rejection reason
        - Incident must be in ASIGNADO state
        
        Args:
            incident: Incident object
            user_role: Role of user attempting transition
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if incident.estado_actual != "asignado":
            return False, "Can only reject incidents in 'asignado' state"
        
        # Rejection reason validation would be done at service layer
        return True, ""
