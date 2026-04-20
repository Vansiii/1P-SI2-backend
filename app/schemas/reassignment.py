"""
Schemas for reassignment operations.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ReassignmentRequest(BaseModel):
    """Request to manually reassign an incident."""
    force_ai_analysis: bool = Field(
        default=False,
        description="Force AI analysis even for simple cases"
    )
    reason: Optional[str] = Field(
        default=None,
        description="Reason for manual reassignment"
    )


class ReassignmentResponse(BaseModel):
    """Response from reassignment operation."""
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
    """Response from timeout check operation."""
    timed_out_incidents: list[int]
    count: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AssignmentHistoryItem(BaseModel):
    """Single assignment attempt in history."""
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
    """Complete assignment history for an incident."""
    incident_id: int
    total_attempts: int
    successful_attempts: int
    rejected_attempts: int
    timeout_attempts: int
    pending_attempts: int
    attempts: list[AssignmentHistoryItem]
