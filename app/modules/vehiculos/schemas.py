"""
Schemas para gestión de vehículos.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class VehiculoCreateRequest(BaseModel):
    """Request para crear un vehículo."""
    
    matricula: str = Field(..., min_length=3, max_length=20, description="Placa del vehículo")
    marca: Optional[str] = Field(None, max_length=60, description="Marca del vehículo")
    modelo: str = Field(..., min_length=1, max_length=100, description="Modelo del vehículo")
    anio: int = Field(..., ge=1900, le=2100, description="Año de fabricación")
    color: Optional[str] = Field(None, max_length=50, description="Color del vehículo")
    imagen: Optional[str] = Field(None, max_length=500, description="URL de la imagen del vehículo")
    
    @field_validator("matricula")
    @classmethod
    def validate_matricula(cls, v: str) -> str:
        """Validar y normalizar matrícula."""
        return v.strip().upper()
    
    @field_validator("marca", "modelo", "color")
    @classmethod
    def validate_text_fields(cls, v: Optional[str]) -> Optional[str]:
        """Validar y normalizar campos de texto."""
        if v is None:
            return None
        return v.strip()


class VehiculoUpdateRequest(BaseModel):
    """Request para actualizar un vehículo."""
    
    marca: Optional[str] = Field(None, max_length=60)
    modelo: Optional[str] = Field(None, max_length=100)
    anio: Optional[int] = Field(None, ge=1900, le=2100)
    color: Optional[str] = Field(None, max_length=50)
    imagen: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None


class VehiculoResponse(BaseModel):
    """Response con datos de un vehículo."""
    
    id: int
    client_id: int
    matricula: str
    marca: Optional[str]
    modelo: str
    anio: int
    color: Optional[str]
    imagen: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}
