"""
Schemas para gestión de archivos.
"""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


EntityType = Literal["user", "incident", "vehicle"]


class FileUploadResponse(BaseModel):
    """Response de archivo subido."""
    
    id: int
    file_name: str
    file_path: str
    file_url: str
    mime_type: str
    size: int
    entity_type: str
    entity_id: str
    created_at: datetime
    
    model_config = {"from_attributes": True}


class FileMetadata(BaseModel):
    """Metadata de archivo."""
    
    file_name: str
    file_path: str
    mime_type: str
    size: int


class SignedUrlResponse(BaseModel):
    """Response de URL firmada."""
    
    signed_url: str
    expires_in: int = Field(default=3600, description="Segundos hasta expiración")
