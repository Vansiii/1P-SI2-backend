"""
Schemas for incident state management.
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class StateTransitionRequest(BaseModel):
    """Schema for state transition request."""
    new_state: str = Field(..., description="Target state")
    notes: Optional[str] = Field(None, max_length=500, description="Optional notes about the transition")
    force: bool = Field(False, description="Force transition (admin only)")


class CancelIncidentRequest(BaseModel):
    """Schema for cancelling an incident."""
    reason: str = Field(..., min_length=10, max_length=500, description="Reason for cancellation")


class ResolveIncidentRequest(BaseModel):
    """Schema for resolving an incident."""
    resolution_notes: Optional[str] = Field(None, max_length=1000, description="Resolution notes")


class StateHistoryResponse(BaseModel):
    """Schema for state history response."""
    id: int
    incidente_id: int
    estado_id: int
    changed_by_user_id: Optional[int]
    comentario: Optional[str]
    fecha: datetime

    class Config:
        from_attributes = True


class StateInfoResponse(BaseModel):
    """Schema for state information."""
    state: str
    description: str
    allowed_transitions: List[str]
    is_terminal: bool


class AllowedTransitionsResponse(BaseModel):
    """Schema for allowed transitions response."""
    current_state: str
    allowed_transitions: List[str]
    state_info: StateInfoResponse
