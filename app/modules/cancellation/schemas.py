"""
Schemas para cancelaciones mutuas.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class CancellationRequestCreate(BaseModel):
    """Schema para crear solicitud de cancelación."""
    reason: str = Field(..., min_length=10, max_length=500, description="Motivo de la cancelación")


class CancellationResponseRequest(BaseModel):
    """Schema para responder a solicitud de cancelación."""
    accept: bool = Field(..., description="True para aceptar, False para rechazar")
    response_message: Optional[str] = Field(None, max_length=500, description="Mensaje opcional de respuesta")


class CancellationRequestResponse(BaseModel):
    """Schema para respuesta de solicitud de cancelación."""
    id: int
    incident_id: int
    requested_by: str
    requested_by_user_id: int
    reason: str
    status: str
    response_by_user_id: Optional[int]
    response_message: Optional[str]
    responded_at: Optional[datetime]
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True
