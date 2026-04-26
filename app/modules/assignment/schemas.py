"""
Assignment and Reassignment Schemas

Schemas para operaciones de asignación y reasignación de incidentes.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ============================================================================
# SCHEMAS DE ASIGNACIÓN
# ============================================================================

class AssignmentRequest(BaseModel):
    """Request para asignar un incidente manualmente."""
    incident_id: int = Field(..., description="ID del incidente a asignar")
    workshop_id: Optional[int] = Field(
        default=None,
        description="ID del taller (opcional, si no se especifica usa IA)"
    )
    technician_id: Optional[int] = Field(
        default=None,
        description="ID del técnico (opcional)"
    )
    force_ai_analysis: bool = Field(
        default=False,
        description="Forzar análisis IA incluso para casos simples"
    )


class AssignmentResponse(BaseModel):
    """Response de operación de asignación."""
    success: bool
    incident_id: int
    assigned_workshop_id: Optional[int] = None
    assigned_workshop_name: Optional[str] = None
    assigned_technician_id: Optional[int] = None
    assigned_technician_name: Optional[str] = None
    strategy_used: Optional[str] = None
    candidates_evaluated: int = 0
    reasoning: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# SCHEMAS DE REASIGNACIÓN
# ============================================================================

class ReassignmentRequest(BaseModel):
    """Request para reasignar un incidente manualmente."""
    force_ai_analysis: bool = Field(
        default=False,
        description="Forzar análisis IA incluso para casos simples"
    )
    reason: Optional[str] = Field(
        default=None,
        description="Razón de la reasignación manual"
    )


class ReassignmentResponse(BaseModel):
    """Response de operación de reasignación."""
    success: bool
    incident_id: int
    assigned_workshop_id: Optional[int] = None
    assigned_workshop_name: Optional[str] = None
    assigned_technician_id: Optional[int] = None
    assigned_technician_name: Optional[str] = None
    strategy_used: Optional[str] = None
    candidates_evaluated: int = 0
    excluded_workshops_count: int = 0
    reasoning: Optional[str] = None
    error_message: Optional[str] = None
    requires_manual_intervention: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TimeoutCheckResponse(BaseModel):
    """Response de verificación de timeouts."""
    timed_out_incidents: list[int]
    count: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# SCHEMAS DE HISTORIAL
# ============================================================================

class AssignmentHistoryItem(BaseModel):
    """Item individual en el historial de intentos de asignación."""
    id: int
    workshop_id: int
    workshop_name: str
    technician_id: Optional[int]
    technician_name: Optional[str]
    algorithmic_score: float
    ai_score: Optional[float]
    final_score: float
    assignment_strategy: str
    distance_km: float
    status: str
    response_message: Optional[str]
    attempted_at: datetime
    responded_at: Optional[datetime]
    timeout_at: Optional[datetime]


class AssignmentHistoryResponse(BaseModel):
    """Historial completo de intentos de asignación para un incidente."""
    incident_id: int
    total_attempts: int
    successful_attempts: int
    rejected_attempts: int
    timeout_attempts: int
    pending_attempts: int
    attempts: list[AssignmentHistoryItem]


# ============================================================================
# SCHEMAS DE ACEPTACIÓN/RECHAZO
# ============================================================================

class AssignmentAcceptRequest(BaseModel):
    """Request para aceptar una asignación."""
    technician_id: int = Field(..., description="ID del técnico que atenderá")
    eta: Optional[int] = Field(
        default=None,
        description="Tiempo estimado de llegada en minutos"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Notas adicionales"
    )


class AssignmentRejectRequest(BaseModel):
    """Request para rechazar una asignación."""
    reason: str = Field(..., description="Razón del rechazo")
    notes: Optional[str] = Field(
        default=None,
        description="Notas adicionales"
    )


class AssignmentActionResponse(BaseModel):
    """Response de acción sobre asignación (aceptar/rechazar)."""
    success: bool
    incident_id: int
    action: str  # "accepted" o "rejected"
    message: str
    will_reassign: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)
