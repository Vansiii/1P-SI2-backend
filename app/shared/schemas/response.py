"""
Standard response schemas for consistent API responses.
"""
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class MessageResponse(BaseModel):
    """Simple message response."""
    
    message: str = Field(..., description="Mensaje de respuesta")


class SuccessResponse(BaseModel, Generic[T]):
    """Generic success response with data."""
    
    data: T = Field(..., description="Datos de respuesta")
    message: str | None = Field(None, description="Mensaje opcional")


class ErrorDetail(BaseModel):
    """Error detail information."""
    
    code: str = Field(..., description="Código de error")
    message: str = Field(..., description="Mensaje de error")
    field: str | None = Field(None, description="Campo relacionado con el error")
    details: dict[str, Any] | None = Field(None, description="Detalles adicionales")


class ErrorResponse(BaseModel):
    """Standard error response."""
    
    error: ErrorDetail = Field(..., description="Información del error")
    timestamp: datetime = Field(..., description="Timestamp del error")
    request_id: str | None = Field(None, description="ID de la petición")


class ValidationErrorResponse(BaseModel):
    """Validation error response with field details."""
    
    error: dict[str, Any] = Field(..., description="Información del error")
    validation_errors: list[dict[str, Any]] = Field(..., description="Errores de validación")
    timestamp: datetime = Field(..., description="Timestamp del error")
    request_id: str | None = Field(None, description="ID de la petición")