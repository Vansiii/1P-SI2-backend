"""
Schemas for especialidades module.
"""
from pydantic import BaseModel, Field
from typing import Optional


class EspecialidadResponse(BaseModel):
    """Response schema for specialty."""
    id: int
    nombre: str
    descripcion: Optional[str] = None

    class Config:
        from_attributes = True
