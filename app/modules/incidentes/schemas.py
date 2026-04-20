"""
Schemas para gestión de incidentes.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class EvidenciaBase(BaseModel):
    """Base para evidencias."""
    tipo: str = Field(..., description="Tipo de evidencia: TEXT, IMAGE, AUDIO")
    descripcion: Optional[str] = Field(None, max_length=500)


class EvidenciaImagenRequest(BaseModel):
    """Request para evidencia de imagen."""
    file_url: str = Field(..., max_length=500, description="URL de la imagen en storage")


class EvidenciaAudioRequest(BaseModel):
    """Request para evidencia de audio."""
    file_url: str = Field(..., max_length=500, description="URL del audio en storage")


class IncidenteCreateRequest(BaseModel):
    """Request para crear un incidente."""
    vehiculo_id: int = Field(..., description="ID del vehículo afectado")
    latitude: float = Field(..., ge=-90, le=90, description="Latitud de la ubicación")
    longitude: float = Field(..., ge=-180, le=180, description="Longitud de la ubicación")
    direccion_referencia: Optional[str] = Field(None, max_length=255, description="Dirección de referencia")
    descripcion: str = Field(..., min_length=10, max_length=2000, description="Descripción del problema")
    
    # Evidencias (URLs de archivos ya subidos)
    imagenes: List[str] = Field(default_factory=list, description="URLs de imágenes ya subidas")
    audios: List[str] = Field(default_factory=list, description="URLs de audios ya subidos")


class EvidenciaResponse(BaseModel):
    """Response de evidencia."""
    id: int
    tipo: str
    descripcion: Optional[str]
    created_at: datetime
    
    model_config = {"from_attributes": True}


class EvidenciaImagenResponse(BaseModel):
    """Response de evidencia imagen."""
    id: int
    evidencia_id: int
    file_url: str
    file_name: Optional[str] = None
    file_type: Optional[str] = None
    mime_type: Optional[str] = None
    size: Optional[int] = None
    uploaded_by: Optional[int] = None
    created_at: Optional[datetime] = None
    
    model_config = {"from_attributes": True}


class EvidenciaAudioResponse(BaseModel):
    """Response de evidencia audio."""
    id: int
    evidencia_id: int
    file_url: str
    file_name: Optional[str] = None
    file_type: Optional[str] = None
    mime_type: Optional[str] = None
    size: Optional[int] = None
    duration: Optional[int] = None
    uploaded_by: Optional[int] = None
    created_at: Optional[datetime] = None
    
    model_config = {"from_attributes": True}


class TechnicianBasicInfo(BaseModel):
    """Información básica del técnico asignado."""
    id: int
    first_name: str
    last_name: str
    phone: Optional[str] = None
    current_latitude: Optional[float] = None
    current_longitude: Optional[float] = None
    is_online: bool = False
    
    model_config = {"from_attributes": True}


class WorkshopBasicInfo(BaseModel):
    """Información básica del taller asignado."""
    id: int
    workshop_name: str
    phone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: Optional[str] = None
    
    model_config = {"from_attributes": True}


class SuggestedTechnicianInfo(BaseModel):
    """Información del técnico sugerido por la IA."""
    technician_id: int
    first_name: str
    last_name: str
    phone: Optional[str] = None
    final_score: float
    distance_km: float
    ai_reasoning: Optional[str] = None
    assignment_strategy: str


class IncidenteResponse(BaseModel):
    """Response con datos de un incidente."""
    id: int
    client_id: int
    vehiculo_id: int
    taller_id: Optional[int]
    tecnico_id: Optional[int]
    latitude: float
    longitude: float
    direccion_referencia: Optional[str]
    descripcion: str
    categoria_ia: Optional[str]
    prioridad_ia: Optional[str]
    resumen_ia: Optional[str]
    es_ambiguo: bool
    estado_actual: str
    created_at: datetime
    updated_at: datetime
    assigned_at: Optional[datetime]
    resolved_at: Optional[datetime]
    
    # Información del técnico y taller asignados
    technician: Optional[TechnicianBasicInfo] = None
    workshop: Optional[WorkshopBasicInfo] = None
    
    # Información del técnico sugerido por la IA (si existe)
    suggested_technician: Optional[SuggestedTechnicianInfo] = None
    
    model_config = {"from_attributes": True}


class IncidenteDetailResponse(IncidenteResponse):
    """Response detallado de incidente con evidencias."""
    evidencias: List[EvidenciaResponse] = []
    imagenes: List[EvidenciaImagenResponse] = []
    audios: List[EvidenciaAudioResponse] = []


class IncidenteUpdateStatusRequest(BaseModel):
    """Request para actualizar estado de incidente."""
    estado: str = Field(..., description="Nuevo estado: pendiente, asignado, en_proceso, resuelto, cancelado")
